#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT=""
MANIFEST="${MANIFEST:-data/casp15_casp16_target_manifest_prefiltered_use.csv}"
INTERVAL_SEC="${INTERVAL_SEC:-1800}"
INCLUDE_STATUS="${INCLUDE_STATUS:-All}"
MAX_LENGTH="${MAX_LENGTH:-999}"
MAX_TARGETS="${MAX_TARGETS:-}"
ONCE=0
NO_START=0

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/watch_af2_benchmark_resume.sh --results-dir DIR [options]

Periodically checks an AF2 CASP manifest run. If prediction_manifest.csv still
has pending af2 rows and no AF2 runner process is active for this result
directory, the script relaunches the AF2 benchmark wrapper with --resume.

Options:
  --results-dir DIR       Existing AF2 result directory to monitor. Required.
  --manifest CSV          Manifest CSV for resumed runs.
  --interval-sec N        Check interval in seconds. Default: 1800.
  --include-status LIST   Forwarded to the AF2 benchmark wrapper. Default: All.
  --max-length N          Forwarded to the AF2 benchmark wrapper. Default: 999.
  --max-targets N         Optional target limit for resumed runs.
  --once                  Run one check/restart cycle and exit.
  --no-start              Only report status; do not relaunch AF2.
  -h, --help              Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --results-dir|--out-root) RUN_ROOT="$2"; shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    --interval-sec) INTERVAL_SEC="$2"; shift 2 ;;
    --include-status) INCLUDE_STATUS="$2"; shift 2 ;;
    --max-length) MAX_LENGTH="$2"; shift 2 ;;
    --max-targets) MAX_TARGETS="$2"; shift 2 ;;
    --once) ONCE=1; shift ;;
    --no-start) NO_START=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$RUN_ROOT" ]]; then
  echo "ERROR: --results-dir is required." >&2
  usage >&2
  exit 2
fi

mkdir -p "${RUN_ROOT}/logs" "${RUN_ROOT}/metadata"
WATCHDOG_LOG="${RUN_ROOT}/logs/af2_watchdog.log"

log() {
  printf '[%s] %s\n' "$(date -Iseconds)" "$*" | tee -a "$WATCHDOG_LOG"
}

manifest_counts() {
  python - "$RUN_ROOT/metadata/prediction_manifest.csv" <<'PY'
import csv
import sys
from collections import Counter
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print("0 0 0 missing")
    raise SystemExit(0)

rows = [row for row in csv.DictReader(path.open(newline="")) if row.get("model") == "af2"]
counts = Counter(row.get("success", "") for row in rows)
print(
    counts.get("true", 0),
    counts.get("false", 0),
    len(rows) - counts.get("true", 0) - counts.get("false", 0),
    "ok",
)
PY
}

af2_process_count() {
  python - "$RUN_ROOT" "$$" <<'PY'
import os
import subprocess
import sys

run_root = sys.argv[1]
self_pid = int(sys.argv[2])
patterns = (
    "run_casp15_casp16_unique_lt1000_all_default_benchmark-af2.sh",
    "run_manifest_predictions.sh",
    "runners/run_af2.sh",
    "run_af2_split_pipeline.py",
)

out = subprocess.run(["ps", "-eo", "pid=,args="], text=True, capture_output=True, check=False).stdout
count = 0
for line in out.splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        pid_text, args = line.split(None, 1)
        pid = int(pid_text)
    except ValueError:
        continue
    if pid == self_pid:
        continue
    if run_root in args and any(pattern in args for pattern in patterns):
        count += 1
print(count)
PY
}

start_resume() {
  if [[ "$NO_START" -eq 1 ]]; then
    log "AF2 resume needed, but --no-start is set."
    return
  fi

  local stamp
  local log_file
  local cmd
  stamp="$(date +%Y%m%d_%H%M%S)"
  log_file="${RUN_ROOT}/logs/af2_watchdog_resume_${stamp}.log"
  cmd=(
    bash scripts/run_casp15_casp16_unique_lt1000_all_default_benchmark-af2.sh
    --manifest "$MANIFEST"
    --results-dir "$RUN_ROOT"
    --include-status "$INCLUDE_STATUS"
    --max-length "$MAX_LENGTH"
    --resume
  )
  if [[ -n "$MAX_TARGETS" ]]; then
    cmd+=(--max-targets "$MAX_TARGETS")
  fi

  log "Starting AF2 resume: ${cmd[*]} > ${log_file}"
  setsid "${cmd[@]}" >"$log_file" 2>&1 &
  echo "$!" > "${RUN_ROOT}/metadata/af2_watchdog_resume.pid"
  log "Started AF2 resume PID $(cat "${RUN_ROOT}/metadata/af2_watchdog_resume.pid")"
}

log "AF2 watchdog started for ${RUN_ROOT}; interval=${INTERVAL_SEC}s"

while true; do
  read -r success_count failed_count pending_count count_status < <(manifest_counts)
  process_count="$(af2_process_count)"
  log "Status: success=${success_count} failed=${failed_count} pending=${pending_count} active_processes=${process_count}"

  if [[ "$count_status" == "missing" ]]; then
    log "No prediction manifest found yet; starting/resuming AF2 run."
    if [[ "$process_count" -eq 0 ]]; then
      start_resume
    fi
  elif [[ "$pending_count" -eq 0 ]]; then
    log "No pending AF2 rows remain; watchdog exiting."
    exit 0
  elif [[ "$process_count" -eq 0 ]]; then
    start_resume
  fi

  if [[ "$ONCE" -eq 1 ]]; then
    exit 0
  fi
  sleep "$INTERVAL_SEC"
done
