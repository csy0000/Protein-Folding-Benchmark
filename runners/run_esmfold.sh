#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate esmfold

export PYTHONPATH="${PWD}/models/esmfold${PYTHONPATH:+:${PYTHONPATH}}"

TMP_DIR="${OUTPUT_DIR}/tmp_esmfold"
mkdir -p "$TMP_DIR"

export TORCH_HOME="${PWD}/weights/torch"
mkdir -p "$TORCH_HOME"

ESMFOLD_ARGS=()
if [ "${ESMFOLD_CPU_ONLY:-1}" != "0" ]; then
  ESMFOLD_ARGS+=(--cpu-only)
fi

# ESMFold normally gives one structure per sequence.
python models/esmfold/scripts/fold.py \
  -i "$INPUT_FASTA" \
  -o "$TMP_DIR" \
  "${ESMFOLD_ARGS[@]}"

PDB_FILE="$(find "$TMP_DIR" -name '*.pdb' | head -n 1)"

if [ -z "$PDB_FILE" ]; then
  echo "No ESMFold PDB output found." >&2
  exit 1
fi

cp "$PDB_FILE" "$OUTPUT_DIR/rank_001.pdb"

cat > "$OUTPUT_DIR/metadata.json" << EOF
{
  "model": "esmfold",
  "top_k_requested": ${TOP_K},
  "top_k_generated": 1,
  "environment": "esmfold",
  "note": "ESMFold is usually deterministic here; only rank_001.pdb generated."
}
EOF
