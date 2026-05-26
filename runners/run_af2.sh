#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: bash runners/run_af2.sh input.fasta output_dir top_k" >&2
  exit 2
fi

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="$3"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate "${AF2_ENV_NAME:-af2}"

export PYTHONPATH="${PWD}/models/alphafold:${PWD}/scripts:${PYTHONPATH:-}"
export XLA_PYTHON_CLIENT_PREALLOCATE="${XLA_PYTHON_CLIENT_PREALLOCATE:-false}"
export TF_FORCE_GPU_ALLOW_GROWTH="${TF_FORCE_GPU_ALLOW_GROWTH:-true}"

OPENFOLD_BIN="${OPENFOLD_BIN:-/home/chen/software/miniforge3/envs/openfold/bin}"
export AF2_JACKHMMER_BINARY="${AF2_JACKHMMER_BINARY:-${OPENFOLD_BIN}/jackhmmer}"
export AF2_HHBLITS_BINARY="${AF2_HHBLITS_BINARY:-${OPENFOLD_BIN}/hhblits}"
export AF2_HHSEARCH_BINARY="${AF2_HHSEARCH_BINARY:-${OPENFOLD_BIN}/hhsearch}"
export AF2_KALIGN_BINARY="${AF2_KALIGN_BINARY:-${OPENFOLD_BIN}/kalign}"

mkdir -p "$OUTPUT_DIR"

python scripts/run_af2_split_pipeline.py \
  --fasta "$INPUT_FASTA" \
  --output-dir "$OUTPUT_DIR" \
  --top-k "$TOP_K" \
  --data-dir "${AF2_DATA_DIR:-/data/chen/protein_folding_databases/alphafold}" \
  --model-preset "${AF2_MODEL_PRESET:-monomer}" \
  --db-preset "${AF2_DB_PRESET:-full_dbs}" \
  --max-template-date "${AF2_MAX_TEMPLATE_DATE:-2026-05-26}" \
  --track-carbon \
  --carbon-country-iso-code "${AF2_CARBON_COUNTRY_ISO_CODE:-WORLD}" \
  --carbon-measure-power-secs "${AF2_CARBON_MEASURE_POWER_SECS:-1.0}"
