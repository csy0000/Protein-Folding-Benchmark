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
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

python - "$INPUT_FASTA" "$BOLTZ_FASTA" <<'PY'
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])
sequence_lines = []
for line in src.read_text().splitlines():
    if not line.strip() or line.startswith(">"):
        continue
    sequence_lines.append(line.strip())

sequence = "".join(sequence_lines)
if not sequence:
    raise SystemExit(f"No sequence found in {src}")

dst.write_text(f">A|protein|empty\n{sequence}\n")
PY

export BOLTZ_CACHE="${PWD}/weights/boltz"
export NUMBA_CACHE_DIR="${PWD}/.cache/numba"
mkdir -p "$BOLTZ_CACHE"
mkdir -p "$NUMBA_CACHE_DIR"

boltz predict "$BOLTZ_FASTA" \
  --out_dir "$TMP_DIR" \
  --diffusion_samples "$TOP_K" \
  --max_parallel_samples "$TOP_K" \
  --output_format pdb \
  --accelerator cpu \
  --no_kernels \
  --override

python scripts/standardize_structure_outputs.py \
  --input-dir "$TMP_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --top-k "$TOP_K" \
  --model-name boltz2 \
  --environment boltz \
  --top-k-policy "Boltz-2 diffusion sampling; use genuine generated samples only; no artificial duplication"
