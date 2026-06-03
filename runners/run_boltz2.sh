#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate boltz

TMP_DIR="${OUTPUT_DIR}/tmp_boltz"
BOLTZ_FASTA="${OUTPUT_DIR}/input_boltz.fasta"
BOLTZ_INPUT_YAML="${OUTPUT_DIR}/input_boltz.yaml"
LOCAL_SHARED_A3M="${OUTPUT_DIR}/shared_input.a3m"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

SHARED_A3M="${SHARED_MSA_A3M_FILE:-}"
SHARED_MSA_DIR="${SHARED_MSA_DIR:-}"
SHARED_MSA_METADATA_FILE="${SHARED_MSA_METADATA_FILE:-}"

python - "$INPUT_FASTA" "$BOLTZ_FASTA" "$BOLTZ_INPUT_YAML" "$SHARED_A3M" "$LOCAL_SHARED_A3M" <<'PYINPUT'
import sys
from pathlib import Path

src = Path(sys.argv[1])
fasta_dst = Path(sys.argv[2])
yaml_dst = Path(sys.argv[3])
shared_a3m = sys.argv[4].strip()
local_shared_a3m = Path(sys.argv[5])
header = ""
sequence_lines = []
for raw_line in src.read_text().splitlines():
    line = raw_line.strip()
    if not line:
        continue
    if line.startswith(">"):
        if not header:
            header = line[1:].split()[0]
        continue
    sequence_lines.append(line)

sequence = "".join(sequence_lines)
if not sequence:
    raise SystemExit(f"No sequence found in {src}")

fasta_dst.write_text(f">A|protein|empty\n{sequence}\n")

if shared_a3m:
    shared_bytes = Path(shared_a3m).read_bytes()
    sanitized = shared_bytes.replace(b"\x00", b"")
    local_shared_a3m.write_bytes(sanitized)
    yaml_dst.write_text(
        "version: 1\n"
        "sequences:\n"
        "  - protein:\n"
        "      id: A\n"
        f"      sequence: {sequence}\n"
        f"      msa: {local_shared_a3m.resolve()}\n"
    )
PYINPUT

export BOLTZ_CACHE="${PWD}/weights/boltz"
export NUMBA_CACHE_DIR="${PWD}/.cache/numba"
BOLTZ_ACCELERATOR="${BOLTZ_ACCELERATOR:-cpu}"
mkdir -p "$BOLTZ_CACHE"
mkdir -p "$NUMBA_CACHE_DIR"

BOLTZ_INPUT="$BOLTZ_FASTA"
TOP_K_POLICY="Boltz-2 diffusion sampling; use genuine generated samples only; no artificial duplication"

if [ -n "$SHARED_A3M" ]; then
  if [ ! -s "$SHARED_A3M" ]; then
    echo "SHARED_MSA_A3M_FILE must point to an existing non-empty A3M file: ${SHARED_A3M}" >&2
    exit 1
  fi
  BOLTZ_INPUT="$BOLTZ_INPUT_YAML"
  TOP_K_POLICY="Boltz-2 diffusion sampling from shared precomputed ColabFold/MMseqs A3M; use genuine generated samples only; no artificial duplication"
  echo "Running Boltz-2 prediction from shared precomputed A3M."
  echo "SHARED_MSA_A3M_FILE=$SHARED_A3M"
  echo "SHARED_MSA_DIR=$SHARED_MSA_DIR"
  echo "SHARED_MSA_METADATA_FILE=$SHARED_MSA_METADATA_FILE"
fi

boltz predict "$BOLTZ_INPUT"   --out_dir "$TMP_DIR"   --diffusion_samples "$TOP_K"   --max_parallel_samples "$TOP_K"   --output_format pdb   --accelerator "$BOLTZ_ACCELERATOR"   --model boltz2   --no_kernels   --override

python scripts/standardize_structure_outputs.py   --input-dir "$TMP_DIR"   --output-dir "$OUTPUT_DIR"   --top-k "$TOP_K"   --model-name boltz2   --environment boltz   --top-k-policy "$TOP_K_POLICY"

if [ -n "$SHARED_A3M" ]; then
python - "$OUTPUT_DIR" "$SHARED_A3M" "$SHARED_MSA_DIR" "$SHARED_MSA_METADATA_FILE" "$BOLTZ_INPUT_YAML" "$LOCAL_SHARED_A3M" <<'PYMETA'
import json
import sys
from pathlib import Path

output_dir = Path(sys.argv[1])
metadata_path = output_dir / "metadata.json"
metadata = json.loads(metadata_path.read_text())
metadata.update(
    {
        "msa_used": True,
        "msa_source": "colabfold_mmseqs2",
        "msa_mode": "shared_precomputed_msa",
        "msa_generation_included_in_timing": False,
        "msa_generation_included_in_carbon": False,
        "msa_reused": True,
        "shared_msa_a3m_file": sys.argv[2],
        "shared_msa_dir": sys.argv[3],
        "shared_msa_metadata_file": sys.argv[4],
        "boltz_input_yaml": sys.argv[5],
        "local_msa_a3m_file": sys.argv[6],
        "msa_notes": "Shared ColabFold/MMseqs MSA generated once per target; MSA cost tracked separately",
    }
)
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
PYMETA
fi
