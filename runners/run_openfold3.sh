#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

echo "OpenFold3 runner is not yet configured. Install and validate models/openfold-3 first." >&2
echo "Input FASTA: $INPUT_FASTA" >&2
echo "Output dir: $OUTPUT_DIR" >&2
echo "Requested top_k: $TOP_K" >&2
exit 2
