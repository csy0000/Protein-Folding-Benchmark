# Chignolin Example

```bash
mkdir -p data/sequences data/references data/predictions data/scores logs

cat > data/sequences/1UAO_chignolin.fasta << 'EOF_FASTA'
>1UAO_chignolin
GYDPETGTWG
EOF_FASTA

wget https://files.rcsb.org/download/1UAO.pdb -O data/references/1UAO_raw.pdb

python scripts/prepare_reference_model1.py \
  --input data/references/1UAO_raw.pdb \
  --output data/references/1UAO_model1_chainA.pdb \
  --chain A

python scripts/01_predict_top5.py \
  --target-id 1UAO_chignolin \
  --fasta data/sequences/1UAO_chignolin.fasta \
  --top-k 5

python scripts/02_score_predictions.py \
  --target-id 1UAO_chignolin \
  --reference data/references/1UAO_model1_chainA.pdb \
  --ref-chain A \
  --pred-chain A \
  --match-mode sequential \
  --use-tmalign \
  --config configs/models.yaml \
  --only-enabled-models

python scripts/03_summarize_scores.py \
  --scores data/scores/1UAO_chignolin_scores.csv \
  --output data/scores/1UAO_chignolin_model_summary.csv \
  --markdown-output data/scores/1UAO_chignolin_model_summary.md
```

For Chignolin, sequential C-alpha matching is preferred because some prediction tools may write arbitrary residue numbers. The scorer computes `lddt_ca` as a C-alpha-only, superposition-free local distance agreement metric. TM-align / US-align scoring is also available and writes `tmalign_tm_score_ref`, `tmalign_tm_score_pred`, `tmalign_rmsd`, and `tmalign_aligned_length`. Chignolin is a pipeline-debug target; lDDT-C-alpha, TM-score, and RMSD can be unstable for very short peptides.

The current validated local configuration enables ESMFold, OmegaFold, Boltz-2, Chai-1, ColabFold, and OpenFold. ESMFold and OmegaFold each produce one standardized prediction by default. OpenFold has one existing scored smoke prediction for this target; fresh OpenFold runner calls now default to MSA mode and require configured databases. Boltz-2, Chai-1, and ColabFold each produce five genuine ranked structures and record their raw source files in `metadata.json`; no top-k ranks are filled by duplicating one output.

Benchmark scoring should use `--config configs/models.yaml --only-enabled-models` so stale or deprecated prediction folders are ignored. The canonical Chignolin score CSV should contain 18 rows: ESMFold 1, OmegaFold 1, OpenFold 1, Chai-1 5, Boltz-2 5, and ColabFold 5.

The model summary step aggregates those per-prediction rows into one row per backend and selects each model's best prediction using lDDT-C-alpha as the primary metric, TM-score normalized by reference length as the secondary metric, TM-align RMSD as the tertiary metric, and C-alpha RMSD as a diagnostic tie-breaker.

For the multi-target workflow that includes both Chignolin and ubiquitin, use `data/targets/targets.csv` with `scripts/04_run_benchmark_targets.py` and `scripts/05_summarize_all_targets.py`; see `docs/multitarget_benchmark.md`.
