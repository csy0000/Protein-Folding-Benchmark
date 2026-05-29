#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIR="${RESULTS_DIR:-results/casp15_lt1000_cuda1_$(date +%Y%m%d_%H%M%S)}"
OUTPUT_TARGETS="${OUTPUT_TARGETS:-data/targets/targets_casp15_lt1000_prepared.csv}"
MODELS="${MODELS:-esmfold,omegafold,boltz2,chai1,colabfold,openfold,openfold3,af2}"
TOP_K="${TOP_K:-1}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"
export OPENFOLD_DEVICE="${OPENFOLD_DEVICE:-cuda:0}"
export CHAI1_DEVICE="${CHAI1_DEVICE:-cuda:0}"
export ESMFOLD_CPU_ONLY="${ESMFOLD_CPU_ONLY:-0}"
export BOLTZ_ACCELERATOR="${BOLTZ_ACCELERATOR:-gpu}"

echo "Running CASP15 <=999-residue benchmark on physical GPU ${CUDA_VISIBLE_DEVICES}"
echo "Inside the masked process, the selected GPU is exposed as cuda:0"
echo "Results: ${RESULTS_DIR}"

bash scripts/run_casp15_lt1000_benchmark.sh \
  --input-csv CASP_csv/casp15_casp16_prepare_targets_input.csv \
  --output-targets "${OUTPUT_TARGETS}" \
  --results-dir "${RESULTS_DIR}" \
  --models "${MODELS}" \
  --top-k "${TOP_K}"
