#!/usr/bin/env bash
# Run the full 8-model CASP15/CASP16 benchmark two more times (rep2, rep3) to reach
# 3 total repeats for performance / time / CO2 statistics.
#
# Self-gating: waits (hourly) until ALL GPUs are idle AND the NVIDIA driver is healthy
# (nvidia-smi / NVML must work), then runs each rep end-to-end pinned to physical GPU 1.
# Designed to be launched detached (nohup ... &) so it survives a session drop.
#
#   nohup bash scripts/run_two_more_reps.sh > results/run_two_more_reps.log 2>&1 &
#
# Every rep = 3 backend-group prediction sub-runs -> combine -> references -> score,
# producing results/<TS>_combine-8models-gpu_<rep>/.
#
# The msa-free and colabfold groups rebuild their MSAs every rep. AF2 does NOT: it
# reuses the features.pkl from the rep1 AF2 run (AF2_REUSE_FEATURES_ROOT), which cuts
# ~20 h/rep of CPU jackhmmer search. Consequence for reporting: AF2's MSA cost stays
# n=1 (measured once, in rep1); only AF2 *inference* gets a per-rep measurement.

set -uo pipefail   # NOT -e: a single model/target failure must not abort the whole job.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

REPS="${REPS:-rep2 rep3}"
# Physical GPU to pin (CUDA_VISIBLE_DEVICES). NOT 0: GPU 0 (0000:19:00.0) hangs under
# sustained load -- it killed rep2 twice on 2026-07-31 (once from a fresh boot) and again
# on 2026-08-01. A hung GPU 0 poisons CUDA init process-wide and only a reboot recovers it,
# so keep it idle.
GPU="${GPU:-1}"

# The 45-target benchmark set. The msa-free group's own default is the 71-row manifest
# (63 targets <=999 aa), whose extra 18 targets the combine step discards -- so pin all
# three groups to the same _use.csv list.
MANIFEST_USE="${MANIFEST_USE:-data/casp15_casp16_target_manifest_prefiltered_use.csv}"

# AF2 MSA reuse: predictions/ root of a completed AF2 run holding per-target
# <target>/af2/af2_features/features.pkl. Read-only. Set to "" to force a full
# ~20 h/rep database search instead.
AF2_REUSE_FEATURES_ROOT="${AF2_REUSE_FEATURES_ROOT:-${REPO_ROOT}/results/20260604_134750_casp15_casp16_unique_lt1000_all_default-af2/predictions}"
POLL_SECONDS="${POLL_SECONDS:-3600}"    # hourly idle checks
MAX_WAIT_HOURS="${MAX_WAIT_HOURS:-72}"  # give up waiting after this many hours
UTIL_IDLE_MAX="${UTIL_IDLE_MAX:-5}"     # %; GPU counts as idle at or below this
STATUS_FILE="${STATUS_FILE:-results/run_two_more_reps.status}"
CONDA_SH="/home/chen/software/miniforge3/etc/profile.d/conda.sh"

log()    { echo "[$(date -Iseconds)] $*"; }
status() { echo "$*" > "$STATUS_FILE"; log "STATUS: $*"; }

# ---------------------------------------------------------------------------
# GPU idle gate (driver-mismatch aware)
# ---------------------------------------------------------------------------
# Echoes exactly one of: DRIVER_ERROR | BUSY | IDLE
gpu_state() {
  local util_out apps_out
  util_out="$(nvidia-smi --query-gpu=index,utilization.gpu --format=csv,noheader,nounits 2>&1)"
  # A driver-wide failure is fatal; a single dead card is not. When one GPU has hung
  # ("Unable to determine the device handle for GPUn"), nvidia-smi still reports the
  # healthy ones and exits 0 -- gate on those rather than blocking forever.
  if grep -qiE 'Failed to initialize NVML|driver/library version mismatch|couldn.t communicate' <<<"$util_out"; then
    echo "DRIVER_ERROR"; return
  fi
  # NOTE: stderr only. gpu_state's stdout IS its return value (captured by $(...)),
  # so anything logged to stdout here corrupts the state string.
  if grep -qiE 'Unable to determine the device handle' <<<"$util_out"; then
    log "WARN: at least one GPU is unreadable (hung/failed); gating on the remaining GPUs only." >&2
  fi
  # The GPU we intend to pin to must itself be readable.
  if ! grep -qE "^[[:space:]]*${GPU}[[:space:]]*," <<<"$util_out"; then
    echo "DRIVER_ERROR"; return
  fi
  # Any CUDA compute (C-type) process => busy. Graphics (Xorg) is not listed here.
  apps_out="$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null)"
  if [[ -n "$(tr -d '[:space:]' <<<"$apps_out")" ]]; then
    echo "BUSY"; return
  fi
  # Every readable GPU must be at/below the idle utilization threshold.
  local busy=0 readable=0
  while IFS=',' read -r idx util; do
    util="$(tr -d '[:space:]' <<<"$util")"
    [[ "$util" =~ ^[0-9]+$ ]] || continue
    readable=$(( readable + 1 ))
    if (( util > UTIL_IDLE_MAX )); then busy=1; fi
  done <<<"$util_out"
  (( readable == 0 )) && { echo "DRIVER_ERROR"; return; }
  [[ "$busy" -eq 0 ]] && echo "IDLE" || echo "BUSY"
}

wait_for_idle() {
  local waited=0 max_seconds=$(( MAX_WAIT_HOURS * 3600 ))
  status "waiting for all GPUs idle + healthy driver (polling every ${POLL_SECONDS}s)"
  while true; do
    local st1 st2
    st1="$(gpu_state)"
    if [[ "$st1" == "IDLE" ]]; then
      sleep 10
      st2="$(gpu_state)"          # confirm across two samples
      if [[ "$st2" == "IDLE" ]]; then
        status "GPUs idle + driver healthy -> proceeding"
        return 0
      fi
    fi
    if [[ "$st1" == "DRIVER_ERROR" ]]; then
      log "GATE: nvidia-smi/NVML unhealthy (driver-library mismatch?) - NOT launching. Needs a driver reload/reboot."
    else
      log "GATE: GPUs $st1 - continuing to wait."
    fi
    if (( waited >= max_seconds )); then
      status "GAVE UP after ${MAX_WAIT_HOURS}h waiting for idle GPUs"
      log "ERROR: exceeded MAX_WAIT_HOURS=${MAX_WAIT_HOURS}; aborting."
      return 1
    fi
    sleep "$POLL_SECONDS"
    waited=$(( waited + POLL_SECONDS ))
  done
}

# ---------------------------------------------------------------------------
# Per-group success gate
# ---------------------------------------------------------------------------
# The group scripts exit 0 even when most targets fail, so a mid-run GPU fault
# ("CUDA error: unspecified launch failure", card falling off the bus) would
# otherwise burn hours producing unusable predictions. Fail fast instead.
MIN_SUCCESS_RATE="${MIN_SUCCESS_RATE:-0.90}"

group_success_ok() {
  local dir="$1" label="$2"
  local manifest="${dir}/metadata/prediction_manifest.csv"
  if [[ ! -f "$manifest" ]]; then
    log "GUARD: ${label}: no manifest at ${manifest}"
    return 1
  fi
  python - "$manifest" "$MIN_SUCCESS_RATE" "$label" <<'PY'
import csv, sys
path, threshold, label = sys.argv[1], float(sys.argv[2]), sys.argv[3]
rows = list(csv.DictReader(open(path)))
total = len(rows)
ok = sum(1 for r in rows if str(r.get("success", "")).strip().lower() == "true")
rate = ok / total if total else 0.0
print(f"GUARD: {label}: {ok}/{total} predictions succeeded ({rate:.1%}); threshold {threshold:.0%}")
sys.exit(0 if total and rate >= threshold else 1)
PY
}

require_group() {
  local dir="$1" label="$2"
  if ! group_success_ok "$dir" "$label"; then
    status "ABORTED: ${label} below ${MIN_SUCCESS_RATE} success rate"
    log "ABORT: ${label} mostly failed. Check GPU health (nvidia-smi) and ${dir}/logs."
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# One full 8-model run for a given rep label
# ---------------------------------------------------------------------------
run_one_rep() {
  local rep="$1"
  local ts; ts="$(date +%Y%m%d_%H%M%S)"
  local base="results/${ts}_casp15_casp16_unique_lt1000_all_default"
  local msa_free_dir="${base}_msa-free_${rep}"
  local colabfold_dir="${base}_colabfold_${rep}"
  local af2_dir="${base}-af2_${rep}"
  local combine_dir="results/${ts}_combine-8models-gpu_${rep}"

  # AF2 inference is seeded per rep so the run is reproducible. The seed drives MSA
  # subsampling: fixed seed reproduces to ~1e-4 lDDT (GPU float noise), a different
  # seed moves lDDT by ~0.02. rep1's seed was never recorded, so it is not reproducible.
  local af2_seed="${rep//[!0-9]/}"
  af2_seed="${af2_seed:-1}"

  status "${rep}: msa-free group -> ${msa_free_dir}"
  MANIFEST="$MANIFEST_USE" RESULTS_DIR="$msa_free_dir" \
    bash scripts/run_casp15_casp16_unique_lt1000_all_default_benchmark-msa-free.sh --no-resume
  log "${rep}: msa-free group rc=$?"
  require_group "$msa_free_dir" "${rep} msa-free group" || return 1

  status "${rep}: colabfold shared-MSA group -> ${colabfold_dir}"
  MANIFEST="$MANIFEST_USE" RESULTS_DIR="$colabfold_dir" \
    bash scripts/run_casp15_casp16_unique_lt1000_all_default_benchmark-colabfold.sh --no-resume
  log "${rep}: colabfold group rc=$?"
  require_group "$colabfold_dir" "${rep} colabfold group" || return 1

  if [[ -n "$AF2_REUSE_FEATURES_ROOT" ]]; then
    status "${rep}: af2 group (inference only, reusing MSA features; seed=${af2_seed}) -> ${af2_dir}"
  else
    status "${rep}: af2 group (full CPU jackhmmer MSA, slow; seed=${af2_seed}) -> ${af2_dir}"
  fi
  MANIFEST="$MANIFEST_USE" RESULTS_DIR="$af2_dir" \
    AF2_REUSE_FEATURES_ROOT="$AF2_REUSE_FEATURES_ROOT" AF2_RANDOM_SEED="$af2_seed" \
    bash scripts/run_casp15_casp16_unique_lt1000_all_default_benchmark-af2.sh --no-resume
  log "${rep}: af2 group rc=$?"
  require_group "$af2_dir" "${rep} af2 group" || return 1

  # Provenance: record which three source dirs feed this rep's combine.
  { echo "msa_free_dir=$msa_free_dir"
    echo "colabfold_dir=$colabfold_dir"
    echo "af2_dir=$af2_dir"
    echo "combine_dir=$combine_dir"; } > "results/combine_sources_${rep}.txt"

  status "${rep}: combine 8 models -> ${combine_dir}"
  python scripts/combine_8model_predictions.py --dest "$combine_dir" \
    --msa-free-dir "$msa_free_dir" \
    --colabfold-dir "$colabfold_dir" \
    --af2-dir "$af2_dir"
  log "${rep}: combine rc=$?"

  # Boltz-2 is fed a pre-copied A3M, so its runner records no MSA-build stage. Charge it
  # the shared ColabFold build cost from THIS rep's own colabfold rows, as rep1 was. Without
  # this, boltz2 looks ~11x faster in rep2/rep3 -- an accounting artifact, not variance.
  status "${rep}: restore boltz2 shared-MSA attribution"
  python scripts/fix_boltz2_shared_msa_attribution.py --run-dir "$combine_dir"
  log "${rep}: boltz2 attribution rc=$?"

  status "${rep}: build combined references"
  python scripts/build_combined_references.py --run-dir "$combine_dir" --cache-dir data/cache/rcsb
  log "${rep}: references rc=$?"

  status "${rep}: score combined 8 models"
  conda run -n folding-benchmark python scripts/score_combined_8models.py \
    --run-dir "$combine_dir" --match-mode sequence
  log "${rep}: score rc=$?"

  status "${rep}: DONE -> ${combine_dir}"
  log "${rep}: complete. Deliverable: ${combine_dir}"
}

# ---------------------------------------------------------------------------
main() {
  mkdir -p results
  log "run_two_more_reps starting. reps='${REPS}', GPU=${GPU}, repo=${REPO_ROOT}"

  # Conda base env for orchestration python + scoring (model runners self-activate
  # their own envs). Also puts `conda` on PATH for the runners' `conda info --base`.
  if [[ -f "$CONDA_SH" ]]; then
    # shellcheck disable=SC1090
    source "$CONDA_SH"
    conda activate folding-benchmark || log "WARN: could not activate folding-benchmark env"
  else
    log "WARN: conda.sh not found at ${CONDA_SH}; relying on ambient PATH."
  fi

  # GPU pinning: inside the masked process the selected GPU is exposed as cuda:0.
  export CUDA_VISIBLE_DEVICES="${GPU}"
  export OPENFOLD_DEVICE=cuda:0
  export CHAI1_DEVICE=cuda:0
  export BOLTZ_ACCELERATOR=gpu
  export ESMFOLD_CPU_ONLY=0
  export OMEGAFOLD_DEVICE=cuda:0
  export COLABFOLD_SEARCH_GPU=1
  log "GPU env: CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES} (exposed as cuda:0 inside runners)"

  if ! wait_for_idle; then
    exit 1
  fi

  for rep in $REPS; do
    log "===== BEGIN ${rep} ====="
    if ! run_one_rep "$rep"; then
      log "ABORT: ${rep} failed a group success gate; not starting any remaining reps."
      status "ABORTED during ${rep}"
      exit 1
    fi
    log "===== END ${rep} ====="
  done

  status "ALL REPS COMPLETE"
  log "All requested reps finished."
}

main "$@"
