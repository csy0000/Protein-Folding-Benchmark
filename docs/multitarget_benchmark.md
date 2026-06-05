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

CASP manifest prediction runs write split stage columns in `metadata/prediction_manifest.csv`: `msa_build_runtime_sec`/`msa_build_carbon_emissions_g`, `inference_runtime_sec`/`inference_carbon_emissions_g`, and total fields. The manifest runner CodeCarbon-wraps MSA-free/default runners as inference-only stages. ColabFold defaults to local `mmseqs2_uniref_env` MSA mode and records MMseqs2 search versus `colabfold_batch` inference as separate CodeCarbon stages. Official AF2 metadata preserves `msa_feature_*` and `af2_inference_*` fields while also populating the canonical manifest `msa_build_*` and `inference_*` columns. In the shared-MSA path, OpenFold inherits the ColabFold MSA build values for the same target and marks the MSA as reused so only OpenFold inference is attributed to the OpenFold runner itself.

For long official AF2 manifest runs, `scripts/watch_af2_benchmark_resume.sh` can supervise a result directory and resume if the AF2 wrapper exits while targets remain pending:

```bash
bash scripts/watch_af2_benchmark_resume.sh \
  --results-dir results/20260604_134750_casp15_casp16_unique_lt1000_all_default-af2 \
  --interval-sec 1800
```

The watchdog reads `metadata/prediction_manifest.csv`, checks for active AF2 processes tied to the same result directory, and starts `scripts/run_casp15_casp16_unique_lt1000_all_default_benchmark-af2.sh --resume` only when pending rows remain and no matching process is running.

Chai-1 default metadata is classified as `msa_used=false`, `msa_source=none`, and `msa_mode=native_embedding_no_msa`; the local runner does not provide external MSAs/templates.

Per-target and all-target summaries rank models by lDDT-C-alpha first, TM-score normalized by reference length second, TM-align RMSD third, and C-alpha RMSD as a diagnostic tie-breaker. Score CSVs also include GDT_TS (`gdt_ts` on a 0-1 scale and `gdt_ts_percent` on a 0-100 scale), using external `TMscore` when available. See `docs/scoring_metrics.md` for column definitions.

For every future Codex instruction, write a dated execution log under `codex-plan/` using the `YYYYMMDD_` filename prefix.


## ColabFold Single-vs-MSA Smoke (2026-05-20)

A first-five carbon-tracked comparison is available under `results/colabfold_single_vs_msa_first5_carbon/`. It uses explicit ablation model IDs `colabfold_single` and `colabfold_msa`. The MSA variant cleans its run-local MSA directory and runs `colabfold_search` inside `runners/run_colabfold.sh`, so MMseqs2 search time and CodeCarbon emissions are included in the model run.


## OpenFold Single-vs-ColabFold-MSA Smoke (2026-05-20)

A first-five carbon-tracked OpenFold comparison is available under `results/openfold_single_vs_msa_first5_carbon/`. It uses explicit ablation model IDs `openfold_single` and `openfold_msa`. `openfold_msa` runs local ColabFold/MMseqs2 MSA search inside `runners/run_openfold_msa.sh`, arranges the generated `.a3m` as an OpenFold precomputed alignment, then runs OpenFold inference. Timing and carbon include both MSA search and inference.

## 2026-05-21 AF2/OpenFold3 Smoke Update

The 2026-05-21 AF2 inspection was initially blocked by missing official AF2 environment/database setup. That blocker is superseded by the 2026-05-26 official `af2` first-five run below.

OpenFold3 is installed experimentally in the separate `openfold3` environment and passed a 7ROA one-target low-memory smoke under `results/backend_smoke/openfold3_default/`. The run produced `rank_001.pdb`, scored successfully, and recorded runtime/carbon metadata. It remains disabled in the canonical config pending broader validation; use `tmp/backend_smoke/models_openfold3_only.yaml` for isolated experimental runs. Details are in `model-installation/openfold3.md`.

## 2026-05-26 Official AF2 split-stage first-five run

Official AlphaFold2 is available as backend ID `af2`, disabled by default in `configs/models.yaml`. The run in `results/af2_first5_split_carbon/` used `tmp/backend_smoke/models_af2_only.yaml`, `top_k=1`, full official AlphaFold databases at `/data/chen/protein_folding_databases/alphafold`, and split CodeCarbon tracking for `msa_features` versus `inference`.

`run_status.csv` reports 5/5 successful targets. `af2_stage_metadata.csv` has two rows per target and records `msa_source=alphafold2_default`, `msa_mode=official_af2_database_search`, MSA/features runtime/carbon, and JAX inference runtime/carbon. The score summary reports mean lDDT-C-alpha `0.8754336456168662`, mean TM-score-ref `0.852168`, mean GDT_TS `0.23456000000000002`, and mean C-alpha RMSD `4.02535248453391`.


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

## 2026-05-22 Unified four-model shared-MSA first-five run

The latest shared-MSA side study is stored in `results/four_msa_models_shared_msa_first5/`. It generates one ColabFold/MMseqs2 A3M per target under `results/four_msa_models_shared_msa_first5/msa/`, then reuses that same target-specific A3M for `colabfold`, `openfold`, `protenix`, and `openfold3`. Model inference metadata marks `msa_generation_included_in_timing=false`, `msa_generation_included_in_carbon=false`, and `msa_reused=true` for all four models.

The run used `tmp/backend_smoke/models_four_msa_shared.yaml`, `top_k=1`, and CodeCarbon world-average accounting. Combined score/cost rows are written to `results/four_msa_models_shared_msa_first5/shared_msa_score_cost_summary.csv`.

## 2026-05-26 Consolidated Latest All-Model Results

The latest consolidated all-model collection is under `results/consolidated/`.
It combines first-five rows for `esmfold`, `omegafold`, `boltz2`, `chai1`,
`colabfold`, `openfold`, `protenix`, `openfold3`, and `af2`. Default/native
models come from `results/default_modes_first5_carbon_metadata/`; shared-MSA
models come from `results/four_msa_models_shared_msa_first5/`; official AF2
comes from `results/af2_first5_split_carbon/`.

The exported tables are:

- `benchmark_metadata_all_models.csv`
- `benchmark_scores_all_models.csv`
- `benchmark_model_summary_all_models.csv`
- `benchmark_collection_manifest.csv`

The same four CSVs are copied to `/home/chen/projects/carbon4science.github.io/results/`.
Superseded smoke/test directories are archived under
`results/_archived_test_artifacts_20260526/`.
