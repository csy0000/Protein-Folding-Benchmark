# Multi-Target Benchmark

`data/targets/targets.csv` is the source of truth for benchmark targets.

Current targets, exactly:

- Chignolin / `1UAO_chignolin`: 10-residue smoke-test peptide target.
- Ubiquitin / `1UBQ_ubiquitin`: first larger single-chain protein benchmark target.

Prepare FASTA files from the target table:

```bash
conda run -n folding-benchmark python scripts/prepare_targets.py \
  --targets data/targets/targets.csv \
  --overwrite
```

Run prediction, scoring, and per-target model summaries for every target:

```bash
conda run -n folding-benchmark python scripts/04_run_benchmark_targets.py \
  --targets data/targets/targets.csv \
  --config configs/models.yaml \
  --top-k 5 \
  --only-enabled-models \
  --use-tmalign \
  --match-mode sequential
```

Aggregate model-level performance across targets:

```bash
conda run -n folding-benchmark python scripts/05_summarize_all_targets.py \
  --targets data/targets/targets.csv \
  --scores-dir data/scores \
  --out-csv data/scores/all_targets_model_summary.csv \
  --out-md data/scores/all_targets_model_summary.md
```

Expected output files include:

- `data/scores/1UAO_chignolin_scores.csv`
- `data/scores/1UAO_chignolin_model_summary.csv`
- `data/scores/1UBQ_ubiquitin_scores.csv`
- `data/scores/1UBQ_ubiquitin_model_summary.csv`
- `data/scores/all_targets_model_summary.csv`
- `data/scores/all_targets_model_summary.md`
- `data/scores/benchmark_run_status.csv`

Current canonical score CSVs contain 17 rows per target: ESMFold 1, OmegaFold 1, Chai-1 5, Boltz-2 5, and ColabFold 5. The enabled validated model set is `esmfold`, `omegafold`, `chai1`, `boltz2`, and `colabfold`.

For every future Codex instruction, write a dated execution log under `codex-plan/` using the `YYYYMMDD_` filename prefix.
