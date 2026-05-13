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
mkdir -p "$TMP_DIR"

# Replace this with the exact Boltz command after installation.
# Example pattern:
# boltz predict "$INPUT_FASTA" --out_dir "$TMP_DIR" --num_samples "$TOP_K"

echo "This runner is not yet configured. See docs/model_installation_status.md." >&2
exit 2
