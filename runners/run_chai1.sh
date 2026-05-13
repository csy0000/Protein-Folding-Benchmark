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
mkdir -p "$TMP_DIR"

# Replace this with the exact Chai-1 command after installation.
# Example pattern:
# chai-lab predict "$INPUT_FASTA" --output-dir "$TMP_DIR" --num-trunk-recycles 3 --num-diffn-samples "$TOP_K"

echo "This runner is not yet configured. See docs/model_installation_status.md." >&2
exit 2
