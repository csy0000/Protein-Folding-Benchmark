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

Current canonical score CSVs contain 18 rows per target: ESMFold 1, OmegaFold 1, Chai-1 5, Boltz-2 5, ColabFold 5, and OpenFold 1. The enabled validated model set is `esmfold`, `omegafold`, `chai1`, `boltz2`, `colabfold`, and `openfold`. Default benchmark comparisons use these canonical model IDs and record MSA provenance in `run_metadata.csv`; `*_single` and `*_msa` IDs are reserved for explicit ablation studies.

Carbon tracking defaults to world-average accounting when `--track-carbon` is used without `--carbon-country-iso-code`; pass `--carbon-country-iso-code CHE` or another supported country code for country-specific accounting. MSA generation is counted in timing/carbon when the metadata columns `msa_generation_included_in_timing` and `msa_generation_included_in_carbon` are true. A combined six-backend 7ROA single-sequence smoke passed under `results/backend_smoke/six_backend_single_sequence/`; the canonical default-mode smoke config is `tmp/backend_smoke/models_six_default_modes.yaml`.

Per-target and all-target summaries rank models by lDDT-C-alpha first, TM-score normalized by reference length second, TM-align RMSD third, and C-alpha RMSD as a diagnostic tie-breaker.

For every future Codex instruction, write a dated execution log under `codex-plan/` using the `YYYYMMDD_` filename prefix.


## ColabFold Single-vs-MSA Smoke (2026-05-20)

A first-five carbon-tracked comparison is available under `results/colabfold_single_vs_msa_first5_carbon/`. It uses explicit ablation model IDs `colabfold_single` and `colabfold_msa`. The MSA variant cleans its run-local MSA directory and runs `colabfold_search` inside `runners/run_colabfold.sh`, so MMseqs2 search time and CodeCarbon emissions are included in the model run.


## OpenFold Single-vs-ColabFold-MSA Smoke (2026-05-20)

A first-five carbon-tracked OpenFold comparison is available under `results/openfold_single_vs_msa_first5_carbon/`. It uses explicit ablation model IDs `openfold_single` and `openfold_msa`. `openfold_msa` runs local ColabFold/MMseqs2 MSA search inside `runners/run_openfold_msa.sh`, arranges the generated `.a3m` as an OpenFold precomputed alignment, then runs OpenFold inference. Timing and carbon include both MSA search and inference.

## 2026-05-21 AF2/OpenFold3 Smoke Update

AF2 was inspected using the official AlphaFold2 source cloned at `models/alphafold`, but no `af2` benchmark backend was added. The exact blocker is documented in `model-installation/af2.md` and `results/backend_smoke/af2_default/BLOCKED.md`: no separate AF2 environment or official AlphaFold database layout is configured, and reusing ColabFold would duplicate the existing `colabfold` backend.

OpenFold3 is installed experimentally in the separate `openfold3` environment and passed a 7ROA one-target low-memory smoke under `results/backend_smoke/openfold3_default/`. The run produced `rank_001.pdb`, scored successfully, and recorded runtime/carbon metadata. It remains disabled in the canonical config pending broader validation; use `tmp/backend_smoke/models_openfold3_only.yaml` for isolated experimental runs. Details are in `model-installation/openfold3.md`.


## Shared ColabFold MSA Cache Smoke (2026-05-22)

For experimental backends that accept precomputed A3M files, generate a reusable ColabFold/MMseqs2 cache first and pass it into the benchmark driver:

```bash
conda run -n folding-benchmark python scripts/generate_colabfold_msas_from_targets.py \
  --targets data/targets/targets_first5.csv \
  --sequences-dir results/shared_msa_colabfold_first5/sequences \
  --msa-output-dir results/shared_msa_colabfold_first5/msas \
  --logs-dir results/shared_msa_colabfold_first5/logs \
  --metadata-out results/shared_msa_colabfold_first5/msa_metadata.csv \
  --colabfold-db /data/chen/protein_folding_databases/colabfold \
  --mmseqs-bin /data/chen/software/mmseqs/bin/mmseqs \
  --track-carbon

conda run -n folding-benchmark python scripts/run_benchmark_from_targets.py \
  --targets data/targets/targets_first5.csv \
  --config tmp/backend_smoke/models_protenix_openfold3_shared_msa.yaml \
  --models protenix,openfold3 \
  --top-k 1 \
  --predictions-dir results/protenix_openfold3_shared_msa_first5/predictions \
  --sequences-dir results/protenix_openfold3_shared_msa_first5/sequences \
  --logs-dir results/protenix_openfold3_shared_msa_first5/logs \
  --results-dir results/protenix_openfold3_shared_msa_first5 \
  --run-metadata results/protenix_openfold3_shared_msa_first5/run_metadata.csv \
  --run-status results/protenix_openfold3_shared_msa_first5/run_status.csv \
  --shared-msa-metadata results/shared_msa_colabfold_first5/msa_metadata.csv \
  --shared-msa-root results/shared_msa_colabfold_first5/msas \
  --max-trials 1 \
  --track-carbon
```

The 2026-05-22 first-five run succeeded for `protenix` and `openfold3` on all five targets. Model inference rows exclude shared MSA generation from timing/carbon; combined totals are written to `results/protenix_openfold3_shared_msa_first5/shared_msa_score_cost_summary.csv`.
