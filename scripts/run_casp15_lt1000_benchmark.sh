#!/usr/bin/env bash
set -euo pipefail

INPUT_CSV="CASP_csv/casp15_casp16_prepare_targets_input.csv"
FILTERED_INPUT=""
OUTPUT_TARGETS="data/targets/targets_casp15_lt1000.csv"
RESULTS_DIR="results/casp15_lt1000_$(date +%Y%m%d)"
CONFIG="configs/models.yaml"
MODELS="esmfold,omegafold,boltz2,chai1,colabfold,openfold"
TOP_K="1"
CASP="CASP15"
MAX_RESIDUES="999"
REFERENCES_DIR="data/references"
SEQUENCES_DIR="data/sequences"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-csv) INPUT_CSV="$2"; shift 2 ;;
    --filtered-input) FILTERED_INPUT="$2"; shift 2 ;;
    --output-targets) OUTPUT_TARGETS="$2"; shift 2 ;;
    --results-dir) RESULTS_DIR="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --models) MODELS="$2"; shift 2 ;;
    --top-k) TOP_K="$2"; shift 2 ;;
    --casp) CASP="$2"; shift 2 ;;
    --max-residues) MAX_RESIDUES="$2"; shift 2 ;;
    --references-dir) REFERENCES_DIR="$2"; shift 2 ;;
    --sequences-dir) SEQUENCES_DIR="$2"; shift 2 ;;
    --include-experimental)
      MODELS="${MODELS},protenix,openfold3,af2"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${FILTERED_INPUT}" ]]; then
  FILTERED_INPUT="${RESULTS_DIR}/filtered_${CASP}_lt${MAX_RESIDUES}_prepare_targets_input.csv"
fi

mkdir -p "${RESULTS_DIR}"

python scripts/filter_targets.py \
  --input "${INPUT_CSV}" \
  --casp "${CASP}" \
  --max-residues "${MAX_RESIDUES}" \
  --enabled-only \
  --output "${FILTERED_INPUT}"

python scripts/prepare_targets_from_csv.py \
  --input-csv "${FILTERED_INPUT}" \
  --output-targets "${OUTPUT_TARGETS}" \
  --references-dir "${REFERENCES_DIR}" \
  --sequences-dir "${SEQUENCES_DIR}" \
  --overwrite

python scripts/run_benchmark_from_targets.py \
  --targets "${OUTPUT_TARGETS}" \
  --config "${CONFIG}" \
  --models "${MODELS}" \
  --output-dir "${RESULTS_DIR}" \
  --top-k "${TOP_K}" \
  --only-enabled-models

python protein_folding/evaluate.py \
  --predictions-dir "${RESULTS_DIR}/predictions" \
  --targets "${OUTPUT_TARGETS}" \
  --output-dir "${RESULTS_DIR}/scores" \
  --config "${CONFIG}" \
  --only-enabled-models
