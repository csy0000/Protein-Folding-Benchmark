#!/usr/bin/env bash
set -euo pipefail

INPUT_CSV="${INPUT_CSV:-CASP_csv/casp15_casp16_unique_58_pdbids_lt1000_resolved_prepare_targets_input.csv}"
RESULTS_DIR="${RESULTS_DIR:-results/casp15_casp16_unique_lt1000_cuda1_$(date +%Y%m%d_%H%M%S)}"
RESOLVED_INPUT="${RESOLVED_INPUT:-${RESULTS_DIR}/resolved_unique_lt1000_prepare_targets_input.csv}"
OUTPUT_TARGETS="${OUTPUT_TARGETS:-data/targets/targets_casp15_casp16_unique_lt1000_prepared.csv}"
CONFIG="${CONFIG:-configs/models.yaml}"
RUN_CONFIG="${RUN_CONFIG:-${RESULTS_DIR}/models_requested_enabled.yaml}"
MODELS="${MODELS:-esmfold,omegafold,boltz2,chai1,colabfold,openfold,openfold3,af2}"
TOP_K="${TOP_K:-1}"
MAX_RESIDUES="${MAX_RESIDUES:-999}"
REFERENCES_DIR="${REFERENCES_DIR:-data/references}"
SEQUENCES_DIR="${SEQUENCES_DIR:-data/sequences}"
FETCH_REFERENCES="${FETCH_REFERENCES:-1}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"
export OPENFOLD_DEVICE="${OPENFOLD_DEVICE:-cuda:0}"
export CHAI1_DEVICE="${CHAI1_DEVICE:-cuda:0}"
export ESMFOLD_CPU_ONLY="${ESMFOLD_CPU_ONLY:-0}"
export BOLTZ_ACCELERATOR="${BOLTZ_ACCELERATOR:-gpu}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-csv) INPUT_CSV="$2"; shift 2 ;;
    --results-dir) RESULTS_DIR="$2"; shift 2 ;;
    --resolved-input) RESOLVED_INPUT="$2"; shift 2 ;;
    --output-targets) OUTPUT_TARGETS="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --run-config) RUN_CONFIG="$2"; shift 2 ;;
    --models) MODELS="$2"; shift 2 ;;
    --top-k) TOP_K="$2"; shift 2 ;;
    --max-residues) MAX_RESIDUES="$2"; shift 2 ;;
    --references-dir) REFERENCES_DIR="$2"; shift 2 ;;
    --sequences-dir) SEQUENCES_DIR="$2"; shift 2 ;;
    --fetch-references) FETCH_REFERENCES="1"; shift ;;
    --no-fetch-references) FETCH_REFERENCES="0"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "${RESULTS_DIR}"

python - "${CONFIG}" "${MODELS}" "${RUN_CONFIG}" <<'PYCONFIG'
from pathlib import Path
import sys

config_path = Path(sys.argv[1])
selected = {item.strip() for item in sys.argv[2].split(",") if item.strip()}
output_path = Path(sys.argv[3])
lines = config_path.read_text().splitlines(keepends=True)
available = set()
current_model = None
in_models = False
for line in lines:
    if line.startswith("models:"):
        in_models = True
        current_model = None
        continue
    if in_models and line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
        current_model = line.strip()[:-1]
        available.add(current_model)
unknown = sorted(selected - available)
if unknown:
    raise SystemExit(f"Unknown model(s) in {config_path}: {', '.join(unknown)}")
out = []
current_model = None
in_models = False
for line in lines:
    if line.startswith("models:"):
        in_models = True
        current_model = None
        out.append(line)
        continue
    if in_models and line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
        current_model = line.strip()[:-1]
        out.append(line)
        continue
    if in_models and current_model and line.startswith("    enabled:"):
        out.append(f"    enabled: {'true' if current_model in selected else 'false'}\n")
        continue
    out.append(line)
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("".join(out))
print(f"Wrote run config with enabled models {','.join(sorted(selected))}: {output_path}")
PYCONFIG

python scripts/resolve_pdb_protein_chains.py \
  --input-csv "${INPUT_CSV}" \
  --output-csv "${RESOLVED_INPUT}" \
  --max-residues-exclusive "$((MAX_RESIDUES + 1))" \
  --enabled-only

if [[ "${FETCH_REFERENCES}" == "1" ]]; then
  python scripts/fetch_reference_pdbs.py \
    --input-csv "${RESOLVED_INPUT}" \
    --references-dir "${REFERENCES_DIR}" \
    --filter-chain
fi

python scripts/prepare_targets_from_csv.py \
  --input-csv "${RESOLVED_INPUT}" \
  --output-targets "${OUTPUT_TARGETS}" \
  --references-dir "${REFERENCES_DIR}" \
  --sequences-dir "${SEQUENCES_DIR}" \
  --overwrite

python scripts/run_benchmark_from_targets.py \
  --targets "${OUTPUT_TARGETS}" \
  --config "${RUN_CONFIG}" \
  --models "${MODELS}" \
  --results-dir "${RESULTS_DIR}" \
  --top-k "${TOP_K}"

python scripts/score_benchmark_from_targets.py \
  --predictions-dir "${RESULTS_DIR}/predictions" \
  --targets "${OUTPUT_TARGETS}" \
  --scores-dir "${RESULTS_DIR}/scores" \
  --results-dir "${RESULTS_DIR}" \
  --config "${RUN_CONFIG}" \
  --models "${MODELS}"
