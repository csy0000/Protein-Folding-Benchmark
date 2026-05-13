#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate rosettafold

echo "This runner is not yet configured. See docs/model_installation_status.md." >&2
exit 2
