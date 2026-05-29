#!/usr/bin/env bash
set -euo pipefail

TARGETS="${TARGETS:-data/targets/targets_casp15_casp16_unique_lt1000_prepared.csv}"
BASE_CONFIG="${BASE_CONFIG:-configs/models.yaml}"
RESULTS_DIR="${RESULTS_DIR:-results/casp15_casp16_unique_lt1000_all_default_$(date +%Y%m%d_%H%M%S)}"
RUN_CONFIG="${RUN_CONFIG:-${RESULTS_DIR}/models_all_available_default.yaml}"
MODELS="${MODELS:-esmfold,omegafold,boltz2,chai1,colabfold,openfold,openfold3,af2}"
TOP_K="${TOP_K:-1}"
MAX_TRIALS="${MAX_TRIALS:-1}"
GPU_CLEANUP_SLEEP_SEC="${GPU_CLEANUP_SLEEP_SEC:-5}"
GPU_DEVICES="${GPU_DEVICES:-auto}"
RESUME_EXISTING="${RESUME_EXISTING:-0}"
TRACK_CARBON="${TRACK_CARBON:-1}"
CARBON_COUNTRY_ISO_CODE="${CARBON_COUNTRY_ISO_CODE:-WORLD}"
SEQUENCES_DIR="${SEQUENCES_DIR:-${RESULTS_DIR}/sequences}"
PREDICTIONS_DIR="${PREDICTIONS_DIR:-${RESULTS_DIR}/predictions}"
LOGS_DIR="${LOGS_DIR:-${RESULTS_DIR}/logs}"
SCORES_DIR="${SCORES_DIR:-${RESULTS_DIR}/scores}"
SEPARATE_COLABFOLD_MSA="${SEPARATE_COLABFOLD_MSA:-1}"
COLABFOLD_DB="${COLABFOLD_DB:-/data/chen/protein_folding_databases/colabfold}"
COLABFOLD_MMSEQS="${COLABFOLD_MMSEQS:-/data/chen/software/mmseqs/bin/mmseqs}"
COLABFOLD_MSA_GPU="${COLABFOLD_MSA_GPU:-auto}"
MSA_DIR="${MSA_DIR:-${RESULTS_DIR}/msa}"
MSA_METADATA="${MSA_METADATA:-${MSA_DIR}/msa_metadata.csv}"
MSA_LOGS_DIR="${MSA_LOGS_DIR:-${MSA_DIR}/logs}"

mkdir -p "${RESULTS_DIR}" "${SEQUENCES_DIR}" "${PREDICTIONS_DIR}" "${LOGS_DIR}" "${SCORES_DIR}" "${MSA_DIR}" "${MSA_LOGS_DIR}"

if [[ "${COLABFOLD_MSA_GPU}" == "auto" ]]; then
  COLABFOLD_MSA_GPU="$(nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | awk 'NF {gsub(/,/, "", $1); print $1; exit}' || true)"
  COLABFOLD_MSA_GPU="${COLABFOLD_MSA_GPU:-0}"
fi

python - "${BASE_CONFIG}" "${MODELS}" "${RUN_CONFIG}" "${SEPARATE_COLABFOLD_MSA}" <<'PYCONFIG'
from pathlib import Path
import sys
import yaml

config_path = Path(sys.argv[1])
selected = [item.strip() for item in sys.argv[2].split(',') if item.strip()]
output_path = Path(sys.argv[3])
separate_msa = sys.argv[4] == '1'
with config_path.open() as f:
    config = yaml.safe_load(f)
models = config.get('models', {})
unknown = sorted(set(selected) - set(models))
if unknown:
    raise SystemExit(f"Unknown model(s) in {config_path}: {', '.join(unknown)}")
for name, spec in models.items():
    spec['enabled'] = name in selected
if separate_msa:
    shared_specs = {
        'colabfold': 'bash runners/run_colabfold_shared_msa.sh',
        'openfold': 'env OPENFOLD_DEVICE=cuda:0 bash runners/run_openfold_shared_msa.sh',
    }
    for name, runner in shared_specs.items():
        if name in models and name in selected:
            models[name].update({
                'runner': runner,
                'use_shared_msa': True,
                'msa_used': True,
                'msa_source': 'colabfold_mmseqs2',
                'msa_mode': 'shared_precomputed_msa',
                'msa_database': 'colabfold',
                'msa_database_path': '/data/chen/protein_folding_databases/colabfold',
                'msa_generation_included_in_timing': False,
                'msa_generation_included_in_carbon': False,
                'msa_reused': True,
                'msa_notes': 'Shared ColabFold/MMseqs MSA generated once per target; MSA cost tracked separately',
            })
output_path.parent.mkdir(parents=True, exist_ok=True)
with output_path.open('w') as f:
    yaml.safe_dump(config, f, sort_keys=False)
print(f"Wrote run config with enabled models {','.join(selected)}: {output_path}")
if separate_msa:
    print('Separate ColabFold/MMseqs MSA carbon accounting enabled for colabfold/openfold.')
PYCONFIG

run_args=(
  --targets "${TARGETS}"
  --config "${RUN_CONFIG}"
  --models "${MODELS}"
  --top-k "${TOP_K}"
  --predictions-dir "${PREDICTIONS_DIR}"
  --sequences-dir "${SEQUENCES_DIR}"
  --logs-dir "${LOGS_DIR}"
  --results-dir "${RESULTS_DIR}"
  --run-metadata "${RESULTS_DIR}/run_metadata.csv"
  --run-status "${RESULTS_DIR}/run_status.csv"
  --max-trials "${MAX_TRIALS}"
  --gpu-cleanup-sleep-sec "${GPU_CLEANUP_SLEEP_SEC}"
  --gpu-devices "${GPU_DEVICES}"
)

if [[ "${TRACK_CARBON}" == "1" ]]; then
  run_args+=(--track-carbon --carbon-country-iso-code "${CARBON_COUNTRY_ISO_CODE}")
fi
if [[ "${RESUME_EXISTING}" == "1" ]]; then
  run_args+=(--resume)
fi

if [[ "${SEPARATE_COLABFOLD_MSA}" == "1" ]]; then
  msa_args=(
    --targets "${TARGETS}"
    --sequences-dir "${SEQUENCES_DIR}"
    --msa-output-dir "${MSA_DIR}/msas"
    --logs-dir "${MSA_LOGS_DIR}"
    --metadata-out "${MSA_METADATA}"
    --colabfold-db "${COLABFOLD_DB}"
    --mmseqs-bin "${COLABFOLD_MMSEQS}"
    --gpu "${COLABFOLD_MSA_GPU}"
  )
  if [[ "${TRACK_CARBON}" == "1" ]]; then
    msa_args+=(--track-carbon --carbon-country-iso-code "${CARBON_COUNTRY_ISO_CODE}")
  fi
  if [[ "${RESUME_EXISTING}" == "1" ]]; then
    msa_args+=(--skip-existing)
  fi
  python scripts/generate_colabfold_msas_from_targets.py "${msa_args[@]}"
  run_args+=(--shared-msa-metadata "${MSA_METADATA}" --shared-msa-root "${MSA_DIR}/msas")
fi

python scripts/run_benchmark_from_targets.py "${run_args[@]}"

python scripts/score_benchmark_from_targets.py \
  --targets "${TARGETS}" \
  --config "${RUN_CONFIG}" \
  --models "${MODELS}" \
  --top-k "${TOP_K}" \
  --predictions-dir "${PREDICTIONS_DIR}" \
  --scores-dir "${SCORES_DIR}" \
  --results-dir "${RESULTS_DIR}" \
  --run-metadata "${RESULTS_DIR}/run_metadata.csv" \
  --use-tmalign \
  --use-gdt-ts

if [[ "${SEPARATE_COLABFOLD_MSA}" == "1" ]]; then
  echo "Separate MSA carbon metadata: ${MSA_METADATA}"
fi
printf "\nBenchmark completed. Results: %s\n" "${RESULTS_DIR}"
