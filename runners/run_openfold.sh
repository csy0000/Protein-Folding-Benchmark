#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
set +u
conda activate openfold
set -u

TORCH_LIB_DIR="$(python -c "import torch, os; print(os.path.join(os.path.dirname(torch.__file__), 'lib'))")"
export CUDA_HOME="${CUDA_HOME:-$CONDA_PREFIX}"
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$TORCH_LIB_DIR:$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.9}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-${PWD}/.cache/triton}"
mkdir -p "$TRITON_CACHE_DIR"

OPENFOLD_PARAMS_DIR="${OPENFOLD_PARAMS_DIR:-${PWD}/weights/colabfold/params}"
OPENFOLD_PARAM_PATH="${OPENFOLD_PARAM_PATH:-${OPENFOLD_PARAMS_DIR}/params_model_1.npz}"
OPENFOLD_DATA_DIR="${OPENFOLD_DATA_DIR:-${PWD}/work/openfold_inputs}"
OPENFOLD_MODE="${OPENFOLD_MODE:-msa}"

EXTRA_ARGS=()
if [ "${OPENFOLD_MODE}" = "single_sequence" ]; then
  OPENFOLD_TEMPLATE_MMCIF_DIR="${OPENFOLD_TEMPLATE_MMCIF_DIR:-${PWD}/models/openfold/tests/test_data/mmcifs}"
  OPENFOLD_PRECOMPUTED_ALIGNMENTS="${OPENFOLD_PRECOMPUTED_ALIGNMENTS:-${PWD}/work/openfold_inputs/precomputed_empty}"
  EXTRA_ARGS+=(--use-precomputed-alignments "$OPENFOLD_PRECOMPUTED_ALIGNMENTS")
else
  OPENFOLD_TEMPLATE_MMCIF_DIR="${OPENFOLD_TEMPLATE_MMCIF_DIR:-${OPENFOLD_DATA_DIR}/pdb_mmcif/mmcif_files}"
fi

python scripts/run_openfold.py \
  --fasta-path "$INPUT_FASTA" \
  --output-dir "$OUTPUT_DIR" \
  --num-models "$TOP_K" \
  --openfold-repo "${OPENFOLD_REPO:-models/openfold}" \
  --params-dir "$OPENFOLD_PARAMS_DIR" \
  --param-path "$OPENFOLD_PARAM_PATH" \
  --data-dir "$OPENFOLD_DATA_DIR" \
  --template-mmcif-dir "$OPENFOLD_TEMPLATE_MMCIF_DIR" \
  --config-preset "${OPENFOLD_CONFIG_PRESET:-model_1}" \
  --device "${OPENFOLD_DEVICE:-cuda:0}" \
  --mode "$OPENFOLD_MODE" \
  --skip-relaxation \
  "${EXTRA_ARGS[@]}"
