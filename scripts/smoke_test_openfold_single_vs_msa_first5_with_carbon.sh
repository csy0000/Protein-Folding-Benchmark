#!/usr/bin/env bash
set -euo pipefail

RESULTS_DIR="${RESULTS_DIR:-results/openfold_single_vs_msa_first5_carbon}"
CONFIG="${CONFIG:-tmp/backend_smoke/models_openfold_single_msa.yaml}"
TARGETS="${TARGETS:-data/targets/targets_first5.csv}"
TOP_K="${TOP_K:-1}"

export PATH="/data/chen/software/mmseqs/bin:${PATH}"
export COLABFOLD_DB="${COLABFOLD_DB:-/data/chen/protein_folding_databases/colabfold}"
export COLABFOLD_MMSEQS="${COLABFOLD_MMSEQS:-/data/chen/software/mmseqs/bin/mmseqs}"

rm -rf "$RESULTS_DIR"
mkdir -p "$RESULTS_DIR"

conda run -n folding-benchmark python scripts/run_benchmark_from_targets.py \
  --targets "$TARGETS" \
  --config "$CONFIG" \
  --models openfold_single,openfold_msa \
  --top-k "$TOP_K" \
  --predictions-dir "$RESULTS_DIR/predictions" \
  --sequences-dir "$RESULTS_DIR/sequences" \
  --logs-dir "$RESULTS_DIR/logs" \
  --results-dir "$RESULTS_DIR" \
  --run-metadata "$RESULTS_DIR/run_metadata.csv" \
  --run-status "$RESULTS_DIR/run_status.csv" \
  --max-trials 1 \
  --gpu-cleanup-sleep-sec 10 \
  --track-carbon \
  --carbon-country-iso-code CHE

conda run -n folding-benchmark python scripts/score_benchmark_from_targets.py \
  --targets "$TARGETS" \
  --config "$CONFIG" \
  --models openfold_single,openfold_msa \
  --top-k "$TOP_K" \
  --predictions-dir "$RESULTS_DIR/predictions" \
  --scores-dir "$RESULTS_DIR/scores" \
  --results-dir "$RESULTS_DIR" \
  --run-metadata "$RESULTS_DIR/run_metadata.csv" \
  --use-tmalign
