#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-1}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"

COLABFOLD_DB="${COLABFOLD_DB:-/data/chen/protein_folding_databases/colabfold}"
COLABFOLD_MMSEQS="${COLABFOLD_MMSEQS:-/data/chen/software/mmseqs/bin/mmseqs}"
COLABFOLD_SEARCH_GPU="${COLABFOLD_SEARCH_GPU:-1}"
COLABFOLD_SEARCH_THREADS="${COLABFOLD_SEARCH_THREADS:-64}"

TARGET_ID="$(awk '/^>/ { sub(/^>/, ""); print $1; exit }' "$INPUT_FASTA")"
if [ -z "$TARGET_ID" ]; then
  TARGET_ID="$(basename "$INPUT_FASTA")"
  TARGET_ID="${TARGET_ID%.*}"
fi

WORK_DIR="${OUTPUT_DIR}/tmp_openfold_colabfold_msa"
SEARCH_DIR="${WORK_DIR}/colabfold_search"
ALIGNMENT_ROOT="${WORK_DIR}/precomputed_alignments"
TARGET_ALIGNMENT_DIR="${ALIGNMENT_ROOT}/${TARGET_ID}"

rm -rf "$WORK_DIR"
mkdir -p "$SEARCH_DIR" "$TARGET_ALIGNMENT_DIR"

if [ ! -d "$COLABFOLD_DB" ]; then
  echo "COLABFOLD_DB does not exist: $COLABFOLD_DB" >&2
  exit 1
fi
if [ ! -x "$COLABFOLD_MMSEQS" ]; then
  echo "COLABFOLD_MMSEQS is not executable: $COLABFOLD_MMSEQS" >&2
  exit 1
fi

export PATH="$(dirname "$COLABFOLD_MMSEQS"):$PATH"

echo "Running ColabFold/MMseqs MSA search inside timed benchmark run."
echo "TARGET_ID=$TARGET_ID"
echo "COLABFOLD_DB=$COLABFOLD_DB"
echo "COLABFOLD_MMSEQS=$COLABFOLD_MMSEQS"
echo "SEARCH_DIR=$SEARCH_DIR"
echo "ALIGNMENT_ROOT=$ALIGNMENT_ROOT"

conda run -n colabfold colabfold_search \
  --mmseqs "$COLABFOLD_MMSEQS" \
  --gpu "$COLABFOLD_SEARCH_GPU" \
  --threads "$COLABFOLD_SEARCH_THREADS" \
  "$INPUT_FASTA" \
  "$COLABFOLD_DB" \
  "$SEARCH_DIR"

A3M_FILE="${SEARCH_DIR}/${TARGET_ID}.a3m"
if [ ! -s "$A3M_FILE" ]; then
  A3M_FILE="$(find "$SEARCH_DIR" -maxdepth 1 -type f -name '*.a3m' | sort | head -1)"
fi
if [ -z "${A3M_FILE:-}" ] || [ ! -s "$A3M_FILE" ]; then
  echo "No ColabFold A3M file found under $SEARCH_DIR" >&2
  find "$SEARCH_DIR" -maxdepth 4 -type f | sort >&2
  exit 1
fi

cp "$A3M_FILE" "${TARGET_ALIGNMENT_DIR}/colabfold.a3m"
echo "Prepared OpenFold precomputed alignment: ${TARGET_ALIGNMENT_DIR}/colabfold.a3m"

conda activate openfold

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
OPENFOLD_TEMPLATE_MMCIF_DIR="${OPENFOLD_TEMPLATE_MMCIF_DIR:-${PWD}/models/openfold/tests/test_data/mmcifs}"

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
  --mode single_sequence \
  --use-precomputed-alignments "$ALIGNMENT_ROOT" \
  --skip-relaxation
