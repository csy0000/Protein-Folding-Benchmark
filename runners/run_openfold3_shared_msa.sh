#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-1}"

if [[ "$TOP_K" != "1" ]]; then
  echo "OpenFold3 experimental shared-MSA runner only supports top_k=1 for smoke tests." >&2
  exit 2
fi

if [[ -z "${SHARED_MSA_DIR:-}" || -z "${SHARED_MSA_A3M_FILE:-}" ]]; then
  echo "SHARED_MSA_DIR and SHARED_MSA_A3M_FILE must be set by the benchmark driver." >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"

CHECKPOINT="${OPENFOLD3_CHECKPOINT:-${PWD}/weights/openfold3/of3-p2-155k.pt}"
if [[ ! -f "$CHECKPOINT" ]]; then
  echo "Missing OpenFold3 checkpoint: $CHECKPOINT" >&2
  echo "Run setup_openfold or set OPENFOLD3_CHECKPOINT to a valid .pt file." >&2
  exit 2
fi

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
export NVCC_PREPEND_FLAGS="${NVCC_PREPEND_FLAGS:-}"
conda activate openfold3

export CUDA_HOME="${CUDA_HOME:-${CONDA_PREFIX}}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"
export OPENFOLD_CACHE="${OPENFOLD_CACHE:-${PWD}/weights/openfold3}"

QUERY_JSON="${OUTPUT_DIR}/query_openfold3_shared_msa.json"
RUNNER_YAML="${OUTPUT_DIR}/runner_openfold3_shared_msa_low_mem.yml"
RAW_OUTPUT="${OUTPUT_DIR}/raw_openfold3"
OF3_MSA_DIR="${OUTPUT_DIR}/openfold3_msa/A"
mkdir -p "$OF3_MSA_DIR"

# OpenFold3's MSA settings key off filename stems. Use the documented cfdb_hits
# stem while preserving the canonical shared MSA file in metadata.
cp "$SHARED_MSA_A3M_FILE" "${OF3_MSA_DIR}/cfdb_hits.a3m"

python - "$INPUT_FASTA" "$QUERY_JSON" "${OF3_MSA_DIR}/cfdb_hits.a3m" <<'PYJSON'
import json
import sys
from pathlib import Path

fasta = Path(sys.argv[1])
out = Path(sys.argv[2])
msa_path = str(Path(sys.argv[3]).resolve())
header = ""
seq_parts = []
for line in fasta.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    if line.startswith(">"):
        header = line[1:].split()[0]
    else:
        seq_parts.append(line)
target_id = header or fasta.stem
sequence = "".join(seq_parts).upper()
if not sequence:
    raise SystemExit(f"No sequence found in {fasta}")
query = {
    "queries": {
        target_id: {
            "use_msas": True,
            "use_main_msas": True,
            "use_paired_msas": False,
            "chains": [
                {
                    "molecule_type": "protein",
                    "chain_ids": ["A"],
                    "sequence": sequence,
                    "main_msa_file_paths": [msa_path],
                }
            ],
        }
    }
}
out.write_text(json.dumps(query, indent=2) + "\n")
print(target_id)
PYJSON

cat > "$RUNNER_YAML" <<'YAML'
model_update:
  presets:
    - predict
    - low_mem
  custom:
    settings:
      memory:
        eval:
          use_deepspeed_evo_attention: false
          use_cueq_triangle_kernels: false
          use_triton_triangle_kernels: false
dataset_config_kwargs:
  msa:
    max_seq_counts:
      cfdb_hits: 100000000
    msas_to_pair: []
    aln_order:
      - cfdb_hits
output_writer_settings:
  structure_format: pdb
  write_full_confidence_scores: false
YAML

rm -rf "$RAW_OUTPUT"
mkdir -p "$RAW_OUTPUT"

run_openfold predict \
  --query-json "$QUERY_JSON" \
  --use-msa-server False \
  --use-templates False \
  --num-model-seeds 1 \
  --num-diffusion-samples 1 \
  --runner-yaml "$RUNNER_YAML" \
  --inference-ckpt-path "$CHECKPOINT" \
  --output-dir "$RAW_OUTPUT"

PREDICTED="$(find "$RAW_OUTPUT" -type f -name '*_model.pdb' | sort | head -1)"
if [[ -z "$PREDICTED" ]]; then
  echo "OpenFold3 finished but no *_model.pdb was found under $RAW_OUTPUT" >&2
  find "$RAW_OUTPUT" -maxdepth 5 -type f | sort >&2
  exit 1
fi

cp "$PREDICTED" "${OUTPUT_DIR}/rank_001.pdb"

python - "$OUTPUT_DIR" "$INPUT_FASTA" "$PREDICTED" "$CHECKPOINT" "$SHARED_MSA_A3M_FILE" "$SHARED_MSA_DIR" "${OF3_MSA_DIR}/cfdb_hits.a3m" <<'PYMETA'
import json
import sys
from pathlib import Path

output_dir = Path(sys.argv[1])
metadata = {
    "model": "openfold3",
    "environment": "openfold3",
    "input_fasta": sys.argv[2],
    "source_prediction": sys.argv[3],
    "checkpoint": sys.argv[4],
    "top_k_requested": 1,
    "top_k_generated": 1,
    "top_k_policy": "experimental OpenFold3 shared-MSA smoke; one seed and one diffusion sample",
    "msa_used": True,
    "msa_source": "colabfold_mmseqs2",
    "msa_mode": "shared_precomputed_msa",
    "msa_storage": "Shared cache A3M copied into runner-local OpenFold3 MSA directory",
    "shared_msa_a3m_file": sys.argv[5],
    "shared_msa_dir": sys.argv[6],
    "local_msa_dir": str(output_dir / "openfold3_msa" / "A"),
    "local_msa_a3m_file": sys.argv[7],
    "openfold3_main_msa_file_paths": [sys.argv[7]],
    "use_templates": False,
    "runner_yaml": str(output_dir / "runner_openfold3_shared_msa_low_mem.yml"),
}
(output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
PYMETA
