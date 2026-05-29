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

python - <<'PY'
import numpy as np

major = int(np.__version__.split(".")[0])
if major >= 2:
    raise SystemExit(
        "OmegaFold requires numpy<2 because its PyTorch/OmegaFold binary stack "
        f"may segfault with NumPy {np.__version__}. Fix with: "
        'conda activate omegafold && pip install "numpy==1.26.4" --force-reinstall'
    )
print("OmegaFold NumPy check OK", np.__version__)
PY

OMEGAFOLD_ARGS=()
if [ -n "${OMEGAFOLD_SUBBATCH_SIZE:-}" ]; then
  OMEGAFOLD_ARGS+=(--subbatch_size "$OMEGAFOLD_SUBBATCH_SIZE")
fi
if [ -n "${OMEGAFOLD_DEVICE:-}" ]; then
  OMEGAFOLD_ARGS+=(--device "$OMEGAFOLD_DEVICE")
fi

omegafold "$INPUT_FASTA" "$TMP_DIR" "${OMEGAFOLD_ARGS[@]}"

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
