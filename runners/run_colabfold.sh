#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate colabfold

COLABFOLD_MSA_MODE="${COLABFOLD_MSA_MODE:-single_sequence}"
COLABFOLD_DB="${COLABFOLD_DB:-/data/chen/protein_folding_databases/colabfold}"
COLABFOLD_MMSEQS="${COLABFOLD_MMSEQS:-/data/chen/software/mmseqs/bin/mmseqs}"
COLABFOLD_SEARCH_GPU="${COLABFOLD_SEARCH_GPU:-1}"
COLABFOLD_SEARCH_THREADS="${COLABFOLD_SEARCH_THREADS:-64}"
COLABFOLD_MODEL_NAME="${COLABFOLD_MODEL_NAME:-colabfold}"

TMP_DIR="${OUTPUT_DIR}/tmp_colabfold"
SEARCH_DIR="${OUTPUT_DIR}/tmp_colabfold_msa_search"
rm -rf "$TMP_DIR" "$SEARCH_DIR"
mkdir -p "$TMP_DIR"

export MPLCONFIGDIR="${PWD}/.cache/matplotlib"
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export PATH="$(dirname "$COLABFOLD_MMSEQS"):$PATH"
mkdir -p "$MPLCONFIGDIR"
mkdir -p "${PWD}/weights/colabfold"

COLABFOLD_INPUT="$INPUT_FASTA"
COLABFOLD_BATCH_MSA_ARGS=(--msa-mode "$COLABFOLD_MSA_MODE")
if [ "$COLABFOLD_MSA_MODE" != "single_sequence" ]; then
  if [ ! -d "$COLABFOLD_DB" ]; then
    echo "COLABFOLD_DB does not exist: $COLABFOLD_DB" >&2
    exit 1
  fi
  if [ ! -x "$COLABFOLD_MMSEQS" ]; then
    echo "COLABFOLD_MMSEQS is not executable: $COLABFOLD_MMSEQS" >&2
    exit 1
  fi
  echo "Running ColabFold local MSA search inside timed benchmark run."
  echo "COLABFOLD_MSA_MODE=$COLABFOLD_MSA_MODE"
  echo "COLABFOLD_DB=$COLABFOLD_DB"
  echo "COLABFOLD_MMSEQS=$COLABFOLD_MMSEQS"
  mkdir -p "$SEARCH_DIR"
  colabfold_search \
    --mmseqs "$COLABFOLD_MMSEQS" \
    --gpu "$COLABFOLD_SEARCH_GPU" \
    --threads "$COLABFOLD_SEARCH_THREADS" \
    "$INPUT_FASTA" \
    "$COLABFOLD_DB" \
    "$SEARCH_DIR"
  COLABFOLD_INPUT="$SEARCH_DIR"
  COLABFOLD_BATCH_MSA_ARGS=()
fi

colabfold_batch \
  "${COLABFOLD_BATCH_MSA_ARGS[@]}" \
  --num-models "$TOP_K" \
  --num-recycle 3 \
  --model-type alphafold2_ptm \
  --data "${PWD}/weights/colabfold" \
  --overwrite-existing-results \
  "$COLABFOLD_INPUT" \
  "$TMP_DIR" || {
    echo "ColabFold failed. Temporary output tree:" >&2
    find "$TMP_DIR" -maxdepth 5 -type f | sort >&2
    exit 1
  }

python scripts/standardize_structure_outputs.py \
  --input-dir "$TMP_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --top-k "$TOP_K" \
  --model-name "$COLABFOLD_MODEL_NAME" \
  --environment colabfold \
  --top-k-policy "ColabFold ranked outputs; use genuine generated structures only; no artificial duplication"
