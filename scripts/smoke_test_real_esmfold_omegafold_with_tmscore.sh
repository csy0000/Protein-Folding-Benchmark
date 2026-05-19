#!/usr/bin/env bash
set -euo pipefail

TARGETS_CSV="${TARGETS_CSV:-results/real_backend_smoke/targets_7ROA_chainA.csv}"
RESULTS_DIR="${RESULTS_DIR:-results/real_backend_smoke}"
MODELS="${MODELS:-esmfold,omegafold}"
TOP_K="${TOP_K:-1}"
GPU_CLEANUP_SLEEP_SEC="${GPU_CLEANUP_SLEEP_SEC:-10}"

RUN_METADATA="${RESULTS_DIR}/run_metadata.csv"
RUN_STATUS="${RESULTS_DIR}/run_status.csv"
SCORES_DIR="${RESULTS_DIR}/scores"
PREDICTIONS_DIR="${RESULTS_DIR}/predictions"
SEQUENCES_DIR="${RESULTS_DIR}/sequences"
LOGS_DIR="${RESULTS_DIR}/logs"

mkdir -p "${RESULTS_DIR}" "${SCORES_DIR}" "${PREDICTIONS_DIR}" "${SEQUENCES_DIR}" "${LOGS_DIR}"

if [ ! -f "${TARGETS_CSV}" ]; then
  cat > "${TARGETS_CSV}" <<'EOF'
target_id,pdb_id,chain_id,sequence,reference_pdb,notes
7ROA_chainA,7ROA,A,QLEDSEVEAVAKGLEEYANGVTEDNFKNYVKNNFAQQEISSVEEELNVNISDSCVANKIKDEFFAISISAIVKAAQKKAWKELAVTVLRFAKANGLKTNAIIVAGQLALWAVQCG,data/references/7ROA_chainA.pdb,casp_round=CASP15; target_id=T1104; target_length=117; size_bin=small; stoichiometry=A1; notes=EntV136
EOF
fi

conda run -n folding-benchmark python scripts/run_benchmark_from_targets.py \
  --targets "${TARGETS_CSV}" \
  --config configs/models.yaml \
  --models "${MODELS}" \
  --top-k "${TOP_K}" \
  --predictions-dir "${PREDICTIONS_DIR}" \
  --sequences-dir "${SEQUENCES_DIR}" \
  --logs-dir "${LOGS_DIR}" \
  --results-dir "${RESULTS_DIR}" \
  --run-metadata "${RUN_METADATA}" \
  --run-status "${RUN_STATUS}" \
  --max-trials 1 \
  --gpu-cleanup-sleep-sec "${GPU_CLEANUP_SLEEP_SEC}"

conda run -n folding-benchmark python scripts/score_benchmark_from_targets.py \
  --targets "${TARGETS_CSV}" \
  --config configs/models.yaml \
  --models "${MODELS}" \
  --top-k "${TOP_K}" \
  --predictions-dir "${PREDICTIONS_DIR}" \
  --scores-dir "${SCORES_DIR}" \
  --results-dir "${RESULTS_DIR}" \
  --run-metadata "${RUN_METADATA}" \
  --use-tmalign

RUN_STATUS="${RUN_STATUS}" SCORES_DIR="${SCORES_DIR}" python - <<'PY'
import csv
import os
from pathlib import Path

status_path = Path(os.environ["RUN_STATUS"])
score_path = Path(os.environ["SCORES_DIR"]) / "7ROA_chainA_scores.csv"

with status_path.open(newline="") as f:
    rows = list(csv.DictReader(f))
failed = [row for row in rows if row.get("status") != "success"]
if failed:
    raise SystemExit(f"Real backend smoke has failed rows: {failed}")

with score_path.open(newline="") as f:
    score_rows = list(csv.DictReader(f))
if not score_rows:
    raise SystemExit(f"No score rows found in {score_path}")
missing_tm = [
    row for row in score_rows
    if row.get("tmalign_available") != "True" or not row.get("tmalign_tm_score_ref")
]
if missing_tm:
    raise SystemExit(f"TM-score columns were not populated for all rows: {missing_tm}")

print(f"Real ESMFold/OmegaFold smoke rows: {len(rows)}")
print(f"TM-score rows populated: {len(score_rows)}")
PY

echo "Real ESMFold/OmegaFold smoke test complete"
echo "Run metadata: ${RUN_METADATA}"
echo "Run status: ${RUN_STATUS}"
echo "Scores dir: ${SCORES_DIR}"
