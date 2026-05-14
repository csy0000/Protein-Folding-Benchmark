#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate colabfold

TMP_DIR="${OUTPUT_DIR}/tmp_colabfold"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"

export MPLCONFIGDIR="${PWD}/.cache/matplotlib"
export XLA_PYTHON_CLIENT_PREALLOCATE=false
mkdir -p "$MPLCONFIGDIR"
mkdir -p "${PWD}/weights/colabfold"

colabfold_batch \
  --msa-mode single_sequence \
  --num-models "$TOP_K" \
  --num-recycle 3 \
  --model-type alphafold2_ptm \
  --data "${PWD}/weights/colabfold" \
  --overwrite-existing-results \
  "$INPUT_FASTA" \
  "$TMP_DIR" || {
    echo "ColabFold failed. Temporary output tree:" >&2
    find "$TMP_DIR" -maxdepth 5 -type f | sort >&2
    exit 1
  }

python scripts/standardize_structure_outputs.py \
  --input-dir "$TMP_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --top-k "$TOP_K" \
  --model-name colabfold \
  --environment colabfold \
  --top-k-policy "ColabFold ranked outputs; use genuine generated structures only; no artificial duplication"
