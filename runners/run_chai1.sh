#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate chai1

TMP_DIR="${OUTPUT_DIR}/tmp_chai1"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
CHAI_FASTA="${OUTPUT_DIR}/input_chai1.fasta"

python - "$INPUT_FASTA" "$CHAI_FASTA" <<'PY'
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
PY

export MPLCONFIGDIR="${PWD}/.cache/matplotlib"
export CHAI_DOWNLOADS_DIR="${PWD}/weights/chai1"
CHAI1_DEVICE="${CHAI1_DEVICE:-cpu}"
mkdir -p "$MPLCONFIGDIR"
mkdir -p "$CHAI_DOWNLOADS_DIR"

chai-lab fold "$CHAI_FASTA" "$TMP_DIR" \
  --num-diffn-samples "$TOP_K" \
  --device "$CHAI1_DEVICE"

python scripts/standardize_structure_outputs.py \
  --input-dir "$TMP_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --top-k "$TOP_K" \
  --model-name chai1 \
  --environment chai1 \
  --top-k-policy "Chai-1 CLI fold; use genuine generated samples only; no artificial duplication"
