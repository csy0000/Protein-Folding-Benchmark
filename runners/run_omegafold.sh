#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate omegafold

TMP_DIR="${OUTPUT_DIR}/tmp_omegafold"
mkdir -p "$TMP_DIR"

omegafold "$INPUT_FASTA" "$TMP_DIR"

PDB_FILE="$(find "$TMP_DIR" -name '*.pdb' | head -n 1)"

if [ -z "$PDB_FILE" ]; then
  echo "No OmegaFold PDB output found." >&2
  exit 1
fi

cp "$PDB_FILE" "$OUTPUT_DIR/rank_001.pdb"

cat > "$OUTPUT_DIR/metadata.json" << EOF
{
  "model": "omegafold",
  "top_k_requested": ${TOP_K},
  "top_k_generated": 1,
  "environment": "omegafold",
  "note": "OmegaFold normally generates one structure per sequence in this basic wrapper."
}
EOF
