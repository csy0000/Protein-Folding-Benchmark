#!/usr/bin/env bash
set -euo pipefail

MANIFEST="${MANIFEST:-data/casp15_casp16_target_manifest_prefiltered_use.csv}"
RESULTS_DIR="${RESULTS_DIR:-results/$(date +%Y%m%d_%H%M%S)_casp15_casp16_unique_lt1000_all_default}"
INCLUDE_STATUS="${INCLUDE_STATUS:-All}"
MODELS="${MODELS:-af2}" # boltz,boltz2,chai1,colabfold,esmfold,omegafold,openfold,
RESUME_EXISTING="${RESUME_EXISTING:-1}"
DRY_RUN="${DRY_RUN:-0}"
MAX_TARGETS="${MAX_TARGETS:-}"
MAX_LENGTH="${MAX_LENGTH:-999}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    --results-dir|--out-root) RESULTS_DIR="$2"; shift 2 ;;
    --include-status) INCLUDE_STATUS="$2"; shift 2 ;;
    --models) MODELS="$2"; shift 2 ;;
    --max-targets) MAX_TARGETS="$2"; shift 2 ;;
    --max-length) MAX_LENGTH="$2"; shift 2 ;;
    --resume) RESUME_EXISTING="1"; shift ;;
    --no-resume) RESUME_EXISTING="0"; shift ;;
    --dry-run) DRY_RUN="1"; shift ;;
    -h|--help)
      cat <<'USAGE'
Usage:
  bash scripts/run_casp15_casp16_unique_lt1000_all_default_benchmark.sh [options]

Runs rank-1 predictions for all rows in the CASP15/CASP16 prefiltered manifest.
Default manifest: data/casp15_casp16_target_manifest_prefiltered.csv
Default models: af2,boltz,boltz2,chai1,colabfold,esmfold,omegafold,openfold

Options:
  --manifest CSV          Manifest CSV to run.
  --results-dir DIR       Output directory.
  --out-root DIR          Alias for --results-dir.
  --include-status LIST   All, Yes, Check, No, or comma-separated statuses.
  --models LIST           Comma-separated model labels.
  --max-targets N         Limit number of manifest rows for smoke testing.
  --max-length N          Maximum target_length to include. Default: 999.
  --resume                Skip existing rank_001.pdb outputs. Default.
  --no-resume             Re-run even when rank_001.pdb exists.
  --dry-run               Print runner commands and initialize metadata only.
USAGE
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

run_args=(
  --manifest "${MANIFEST}"
  --out-root "${RESULTS_DIR}"
  --include-status "${INCLUDE_STATUS}"
  --models "${MODELS}"
  --max-length "${MAX_LENGTH}"
)

if [[ -n "${MAX_TARGETS}" ]]; then
  run_args+=(--max-targets "${MAX_TARGETS}")
fi
if [[ "${RESUME_EXISTING}" == "1" ]]; then
  run_args+=(--resume)
fi
if [[ "${DRY_RUN}" == "1" ]]; then
  run_args+=(--dry-run)
fi

printf "Manifest: %s\n" "${MANIFEST}"
printf "Output:   %s\n" "${RESULTS_DIR}"
printf "Statuses: %s\n" "${INCLUDE_STATUS}"
printf "Models:   %s\n" "${MODELS}"
printf "Max len:  %s\n" "${MAX_LENGTH}"
printf "Rank:     1\n"

bash scripts/run_manifest_predictions.sh "${run_args[@]}"

printf "\nPrediction run finished. Metadata: %s\n" "${RESULTS_DIR}/metadata/prediction_manifest.csv"
