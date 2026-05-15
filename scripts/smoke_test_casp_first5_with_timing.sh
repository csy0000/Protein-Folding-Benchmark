#!/usr/bin/env bash
set -euo pipefail

TARGETS_CSV="data/targets/targets_first5.csv"
RESULTS_DIR="results/timing_smoke"
RUN_METADATA="${RESULTS_DIR}/run_metadata.csv"
SCORES_DIR="${RESULTS_DIR}/scores"
PREDICTIONS_DIR="${RESULTS_DIR}/predictions"
LOGS_DIR="${RESULTS_DIR}/logs"

bash scripts/smoke_test_prepare_casp_first5.sh

mkdir -p "${RESULTS_DIR}" "${SCORES_DIR}" "${PREDICTIONS_DIR}" "${LOGS_DIR}"

conda run -n folding-benchmark python scripts/run_benchmark_from_targets.py \
  --targets "${TARGETS_CSV}" \
  --config configs/models.yaml \
  --top-k 5 \
  --predictions-dir "${PREDICTIONS_DIR}" \
  --logs-dir "${LOGS_DIR}" \
  --results-dir "${RESULTS_DIR}" \
  --run-metadata "${RUN_METADATA}" \
  --mock-runner \
  --mock-sleep-sec 0.02

test -s "${RUN_METADATA}"

conda run -n folding-benchmark python scripts/score_benchmark_from_targets.py \
  --targets "${TARGETS_CSV}" \
  --config configs/models.yaml \
  --top-k 5 \
  --predictions-dir "${PREDICTIONS_DIR}" \
  --scores-dir "${SCORES_DIR}" \
  --results-dir "${RESULTS_DIR}" \
  --run-metadata "${RUN_METADATA}" \
  --use-tmalign

python - <<'PY'
import csv
from pathlib import Path

scores = sorted(Path("results/timing_smoke/scores").glob("*_scores.csv"))
required = {
    "inference_time_sec",
    "inference_time_sec_per_prediction",
    "prediction_count",
    "trials_run",
    "max_trials",
    "successful_trial",
}
if not scores:
    raise SystemExit("No score CSVs produced")
for path in scores:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"{path} missing timing columns: {sorted(missing)}")
print(f"Timing columns present in {len(scores)} score CSVs")
PY

TARGETS_CSV="${TARGETS_CSV}" RESULTS_DIR="${SCORES_DIR}" \
  conda run -n folding-benchmark jupyter nbconvert \
    --to notebook \
    --execute notebooks/benchmark_analysis.ipynb \
    --output /tmp/benchmark_analysis_timing_smoke.ipynb \
    --ExecutePreprocessor.timeout=300

echo "Timing smoke test complete"
echo "Run metadata: ${RUN_METADATA}"
echo "Scores dir: ${SCORES_DIR}"
