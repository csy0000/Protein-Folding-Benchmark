#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

echo "AlphaFold3 runner is not yet configured." >&2
echo "AlphaFold3 model parameters are restricted-access and must be obtained under the applicable terms before local inference." >&2
echo "Input FASTA: $INPUT_FASTA" >&2
echo "Output dir: $OUTPUT_DIR" >&2
echo "Requested top_k: $TOP_K" >&2
exit 2
