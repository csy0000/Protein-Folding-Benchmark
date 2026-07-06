#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate chai1

SHARED_A3M="${SHARED_MSA_A3M_FILE:-}"
SHARED_MSA_DIR="${SHARED_MSA_DIR:-}"
SHARED_MSA_METADATA_FILE="${SHARED_MSA_METADATA_FILE:-}"

if [ -z "$SHARED_A3M" ] || [ ! -s "$SHARED_A3M" ]; then
  echo "SHARED_MSA_A3M_FILE must point to an existing non-empty A3M file: ${SHARED_A3M:-<unset>}" >&2
  exit 1
fi

TMP_DIR="${OUTPUT_DIR}/tmp_chai1"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
CHAI_FASTA="${OUTPUT_DIR}/input_chai1.fasta"
MSA_DIR="${OUTPUT_DIR}/chai_msa"
rm -rf "$MSA_DIR"
mkdir -p "$MSA_DIR"

# Normalize the input FASTA into Chai's >protein|name=... form and capture the query sequence.
QUERY_SEQ="$(python - "$INPUT_FASTA" "$CHAI_FASTA" <<'PY'
from pathlib import Path
import re
import sys

src = Path(sys.argv[1])
dst = Path(sys.argv[2])

records = []
header = None
seq_parts = []
for raw_line in src.read_text().splitlines():
    line = raw_line.strip()
    if not line:
        continue
    if line.startswith(">"):
        if header is not None:
            records.append((header, "".join(seq_parts)))
        header = line[1:].strip() or "sequence"
        seq_parts = []
    else:
        seq_parts.append(line)
if header is not None:
    records.append((header, "".join(seq_parts)))

if not records:
    raise SystemExit(f"No FASTA records found in {src}")

with dst.open("w") as handle:
    for header, sequence in records:
        safe_name = re.sub(r"[^0-9A-Za-z_.-]+", "_", header).strip("_") or "sequence"
        if not safe_name.lower().startswith("protein|"):
            safe_name = f"protein|name={safe_name}"
        handle.write(f">{safe_name}\n{sequence}\n")

# Emit the (single) query sequence so the shell can verify the aligned.pqt hash.
print(records[0][1].strip().upper())
PY
)"

if [ -z "$QUERY_SEQ" ]; then
  echo "Could not extract query sequence from ${INPUT_FASTA}" >&2
  exit 1
fi

# Materialize the shared ColabFold A3M into the MSA dir (NUL-sanitized), tagged as uniref90 so
# chai's merge_a3m_in_directory records a recognized source_database instead of the default warning.
# ColabFold prepends a '#len\tcardinality' comment line that Biopython's FASTA parser rejects; drop
# any leading-'#' comment lines so chai's read_fasta accepts the alignment.
python - "$SHARED_A3M" "${MSA_DIR}/uniref90.a3m" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
lines = src.read_bytes().replace(b"\x00", b"").splitlines()
kept = [ln for ln in lines if not ln.lstrip().startswith(b"#")]
dst.write_bytes(b"\n".join(kept) + b"\n")
PY

export MPLCONFIGDIR="${PWD}/.cache/matplotlib"
export CHAI_DOWNLOADS_DIR="${PWD}/weights/chai1"
CHAI1_DEVICE="${CHAI1_DEVICE:-cuda:0}"
mkdir -p "$MPLCONFIGDIR"
mkdir -p "$CHAI_DOWNLOADS_DIR"

# Convert the a3m into Chai's <sha256(query.upper())>.aligned.pqt and VERIFY the hash matches the
# query sequence chai will derive from the FASTA. If it does not, chai silently folds
# single-sequence and mislabels the run as MSA-based, so fail loudly instead.
python - "$MSA_DIR" "$QUERY_SEQ" <<'PY'
import sys
from pathlib import Path

from chai_lab.data.parsing.msas.aligned_pqt import (
    expected_basename,
    merge_a3m_in_directory,
)

msa_dir = Path(sys.argv[1])
query_seq = sys.argv[2]

merge_a3m_in_directory(str(msa_dir))

expected = msa_dir / expected_basename(query_seq)
if not expected.is_file():
    produced = sorted(p.name for p in msa_dir.glob("*.aligned.pqt"))
    raise SystemExit(
        "Chai aligned.pqt hash mismatch: expected "
        f"{expected.name} for the FASTA query but found {produced}. "
        "Chai would silently fall back to single-sequence; aborting."
    )
print(f"Verified shared MSA -> {expected.name}")
PY

chai-lab fold "$CHAI_FASTA" "$TMP_DIR" \
  --num-diffn-samples "$TOP_K" \
  --device "$CHAI1_DEVICE" \
  --msa-directory "$MSA_DIR"

python scripts/standardize_structure_outputs.py \
  --input-dir "$TMP_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --top-k "$TOP_K" \
  --model-name chai1_msa \
  --environment chai1 \
  --top-k-policy "Chai-1 CLI fold from shared precomputed ColabFold/MMseqs A3M; use genuine generated samples only; no artificial duplication"

python - "$OUTPUT_DIR" "$SHARED_A3M" "$SHARED_MSA_DIR" "$SHARED_MSA_METADATA_FILE" "$MSA_DIR" <<'PY'
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
        "local_msa_dir": sys.argv[5],
        "msa_notes": "Shared ColabFold/MMseqs MSA converted to Chai .aligned.pqt; MSA cost tracked separately",
    }
)
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
PY
