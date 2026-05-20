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

Current canonical score CSVs contain 18 rows per target: ESMFold 1, OmegaFold 1, Chai-1 5, Boltz-2 5, ColabFold 5, and OpenFold 1. The enabled validated model set is `esmfold`, `omegafold`, `chai1`, `boltz2`, `colabfold`, and `openfold`.

OpenFold's canonical two-target score rows are retained from prior single-sequence smoke outputs, and a fresh 7ROA single-sequence smoke passed on 2026-05-19 under `results/backend_smoke/openfold_single_sequence/`. Fresh OpenFold MSA-mode calls require configured OpenFold/AlphaFold-compatible database paths; missing databases should be treated as a setup blocker, not as successful MSA inference. A combined six-backend 7ROA smoke passed under `results/backend_smoke/six_backend_single_sequence/`.

Per-target and all-target summaries rank models by lDDT-C-alpha first, TM-score normalized by reference length second, TM-align RMSD third, and C-alpha RMSD as a diagnostic tie-breaker.

For every future Codex instruction, write a dated execution log under `codex-plan/` using the `YYYYMMDD_` filename prefix.


## ColabFold Single-vs-MSA Smoke (2026-05-20)

A first-five carbon-tracked comparison is available under `results/colabfold_single_vs_msa_first5_carbon/`. It uses explicit model IDs `colabfold_single` and `colabfold_msa`. The MSA variant cleans its run-local MSA directory and runs `colabfold_search` inside `runners/run_colabfold.sh`, so MMseqs2 search time and CodeCarbon emissions are included in the model run.


## OpenFold Single-vs-ColabFold-MSA Smoke (2026-05-20)

A first-five carbon-tracked OpenFold comparison is available under `results/openfold_single_vs_msa_first5_carbon/`. It uses `openfold_single` and `openfold_msa` as model IDs. `openfold_msa` runs local ColabFold/MMseqs2 MSA search inside `runners/run_openfold_msa.sh`, arranges the generated `.a3m` as an OpenFold precomputed alignment, then runs OpenFold inference. Timing and carbon include both MSA search and inference.
