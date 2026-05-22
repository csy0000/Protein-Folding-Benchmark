# Protein Folding Benchmark

This project benchmarks locally runnable protein folding backends on selected protein targets. For each target, the pipeline runs configured prediction backends, stores their outputs in a standardized layout, and scores predicted structures against an experimental reference structure.

Benchmark targets are listed in `data/targets/targets.csv`. The first two targets are:

- Target ID: `1UAO_chignolin`
- PDB ID: `1UAO`
- Sequence: `GYDPETGTWG`
- Reference: `data/references/1UAO_model1_chainA.pdb`
- Target ID: `1UBQ_ubiquitin`
- PDB ID: `1UBQ`
- Sequence length: 76 residues
- Reference: `data/references/1UBQ_chainA.pdb`

## Benchmark Model Set

The core benchmark scope is exactly these 9 backends:

1. ESMFold (`esmfold`)
2. OmegaFold (`omegafold`)
3. Chai-1 (`chai1`)
4. Boltz-2 (`boltz2`)
5. OpenFold (`openfold`)
6. OpenFold3 (`openfold3`)
7. ColabFold (`colabfold`)
8. AlphaFold2 (`alphafold2`)
9. AlphaFold3 (`alphafold3`)

Model families:

- AF2-style / MSA-template family: AlphaFold2, OpenFold, ColabFold
- AF3-style / biomolecular family: AlphaFold3, OpenFold3, Boltz-2, Chai-1
- Single-sequence language-model / sequence-only baselines: ESMFold, OmegaFold

AlphaFold3 is included as a future optional restricted-access baseline and remains disabled by default. Its inference code is available, but model parameters and outputs are subject to the applicable Google/DeepMind terms, including non-commercial-use restrictions. Do not use AlphaFold3 for non-academic or commercial work unless rights, licensing, and any approved commercial route have been resolved.

OpenFold is included as an AF2-style backend and is enabled after smoke validation. The main benchmark keeps canonical model IDs (`esmfold`, `omegafold`, `boltz2`, `chai1`, `colabfold`, `openfold`) and records MSA use in `run_metadata.csv` instead of encoding it in the model name. Current default-mode `colabfold` and `openfold` runs use local ColabFold/MMseqs2 MSAs from `/data/chen/protein_folding_databases/colabfold`; suffixed IDs such as `colabfold_single`, `colabfold_msa`, `openfold_single`, and `openfold_msa` are reserved for explicit ablation studies. The benchmark does not download OpenFold, AlphaFold, or ColabFold sequence/template databases automatically.

Model-specific setup notes are in `model-installation/`. Model source trees live under `models/`, which is ignored by Git, so reproducibility notes should be tracked outside model checkouts. Other backend status details are tracked in `docs/model_installation_status.md`.

For the current project handoff, installation status, smoke-test commands, and known model caveats, start with `docs/project_handoff_20260515.md`. Shared AlphaFold2/OpenFold database requirements are tracked in `model-installation/shared_af2_databases.md`; these large databases are not downloaded by this repository.

Exact license and usage terms should be checked from each upstream repository before publication, redistribution, or benchmark release.

## Environment Policy

Use one driver/scoring environment plus one isolated conda environment per folding model. Do not install all folding models into a single conda environment.

| Environment | Purpose |
|---|---|
| `folding-benchmark` | Driver and scoring environment only |
| `openfold` | OpenFold backend |
| `openfold3` | OpenFold3 backend |
| `boltz` | Current working Boltz-2 backend environment; kept for compatibility |
| `chai1` | Chai-1 backend |
| `esmfold` | ESMFold backend |
| `colabfold` | ColabFold backend |
| `alphafold2` | AlphaFold2 backend |
| `alphafold3` | AlphaFold3 backend |
| `omegafold` | OmegaFold backend |

The benchmark backend ID is `boltz2`, but the current working conda environment may remain named `boltz` for compatibility.

## Runner Interface

Each runner must accept exactly:

```bash
bash runners/run_MODEL.sh input.fasta output_dir top_k
```

Each runner should write standardized outputs:

```text
output_dir/
├── rank_001.pdb
├── rank_002.pdb
├── rank_003.pdb
├── rank_004.pdb
├── rank_005.pdb
└── metadata.json
```

`top_k=5` is a request, not a guarantee. If a model only produces one structure, it should write only `rank_001.pdb` and record this in `metadata.json`. Runners must not duplicate deterministic outputs to satisfy `top_k`. `metadata.json` records `top_k_requested`, `top_k_generated`, `top_k_policy`, and, for multi-sample adapters, the source files used for each standardized rank.

## Chignolin Example

```bash
conda activate folding-benchmark

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
```

Use `--config configs/models.yaml --only-enabled-models` for benchmark score generation. This prevents stale prediction folders, such as archived or deprecated backend IDs, from contaminating the canonical CSV.

Carbon tracking defaults to world-average accounting. `scripts/run_benchmark_from_targets.py --track-carbon` records `carbon_country_iso_code=WORLD`, `carbon_intensity_mode=world_average`, and applies the configurable default intensity in `scripts/carbon_tracking.py`; pass `--carbon-country-iso-code CHE` or another supported country code to override this. MSA generation is included in timing and carbon when `msa_generation_included_in_timing=true` and `msa_generation_included_in_carbon=true`.

## CSV-Driven Benchmark Pipeline

For a new benchmark batch, start from a small CSV with at least:

```csv
PDBID,chain
1UAO,A
1UBQ,A
```

Optional columns are `name`, `description`, `sequence`, `reference_path`, and `enabled`. `PDBID` is normalized to uppercase. Rows with `enabled=false` are skipped. Existing target IDs are preserved for known targets such as `1UAO_chignolin` and `1UBQ_ubiquitin`; otherwise target IDs default to `<PDBID>_chain<CHAIN>` or `<PDBID>_<name>`.

If `sequence` is omitted, `scripts/prepare_targets_from_csv.py` first reuses an existing `data/targets/targets.csv` entry for that PDB/chain, then tries to extract sequence from a prepared reference PDB. It does not download large databases or silently fetch missing references. Provide `reference_path` for new targets, or prepare the reference file first.

Example input:

```text
examples/example_targets.csv
```

Four-command workflow:

```bash
python scripts/prepare_targets_from_csv.py \
  --input-csv examples/example_targets.csv \
  --output-targets data/targets/targets.csv \
  --references-dir data/references \
  --sequences-dir data/sequences

python scripts/run_benchmark_from_targets.py \
  --targets data/targets/targets.csv \
  --config configs/models.yaml \
  --top-k 5

python scripts/score_benchmark_from_targets.py \
  --targets data/targets/targets.csv \
  --config configs/models.yaml \
  --top-k 5

python scripts/05_summarize_all_targets.py \
  --targets data/targets/targets.csv \
  --scores-dir data/scores \
  --out-csv data/scores/all_targets_model_summary.csv \
  --out-md data/scores/all_targets_model_summary.md
```

Current enabled working models are `boltz2`, `chai1`, `esmfold`, `colabfold`, `omegafold`, and `openfold`. Expected top-k behavior:

| Model | Current top-k behavior |
|---|---|
| `boltz2` | up to top 5 |
| `chai1` | up to top 5 |
| `colabfold` | up to top 5 |
| `esmfold` | top 1 |
| `omegafold` | top 1 |
| `openfold` | top 1 in the current easy pipeline setup |

The easy runner defaults OpenFold to explicit `OPENFOLD_MODE=single_sequence` so the general CSV pipeline does not require full OpenFold/AF2 MSA databases. True OpenFold MSA runs require external databases and template files; see `model-installation/openfold.md`. AlphaFold2 and AlphaFold3 remain disabled/future backends. OpenFold3 is installed experimentally and has passed a one-target low-memory smoke, but it remains disabled in the canonical config pending broader validation.

## Experimental OpenFold3 Smoke

OpenFold3 (`openfold3`) is installed experimentally in its own environment with
checkpoint `weights/openfold3/of3-p2-155k.pt`. A one-target 7ROA low-memory smoke
passed on 2026-05-21 under `results/backend_smoke/openfold3_default/`, producing
`rank_001.pdb` and score/carbon metadata. Use
`tmp/backend_smoke/models_openfold3_only.yaml` for isolated experimental runs; do
not include `openfold3` in canonical score CSVs until broader validation is
requested. AlphaFold2 remains blocked on official database/parameter setup rather
than being aliased to ColabFold.

Open the notebook after scoring:

```bash
jupyter notebook notebooks/benchmark_analysis.ipynb
```

## CASP15/CASP16 Smoke Test

The CASP input table is:

```text
CASP_csv/casp15_casp16_prepare_targets_input.csv
```

Before launching a large CASP15/CASP16 benchmark, run the first-five target preparation smoke test:

```bash
bash scripts/smoke_test_prepare_casp_first5.sh
```

This creates:

```text
CASP_csv/casp15_casp16_prepare_targets_input_first5.csv
data/targets/targets_first5.csv
data/references/<target_id>.pdb
data/sequences/<target_id>.fasta
```

Run the enabled models on the first-five target table with:

```bash
python scripts/run_benchmark_from_targets.py \
  --targets data/targets/targets_first5.csv \
  --config configs/models.yaml \
  --top-k 5
```

Model inference timing is recorded in `results/run_metadata.csv` by default. Each generated `rank_*.pdb` gets one metadata row with wall-clock `inference_time_sec`, `inference_time_sec_per_prediction`, retry-trial columns, return code, command, and failure message when applicable. A compact target/model status table is also written to `data/run_status.csv` by default, or to `--run-status` when supplied. The driver retries each target/model up to `--max-trials` times; the default is 5. It runs `colabfold` and `openfold` before the other enabled models and waits 5 seconds after each target/model run by default (`--gpu-cleanup-sleep-sec 5`) so GPU memory has time to settle.

Score the first-five benchmark with:

```bash
python scripts/score_benchmark_from_targets.py \
  --targets data/targets/targets_first5.csv \
  --config configs/models.yaml \
  --top-k 5 \
  --results-dir results \
  --use-tmalign
```

The scorer merges timing columns into each per-target score CSV when run metadata are available:

```text
inference_time_sec
inference_time_sec_per_prediction
prediction_count
trials_run
max_trials
successful_trial
success
return_code
```

To test the timing/reporting plumbing without expensive model inference, run:

```bash
bash scripts/smoke_test_casp_first5_with_timing.sh
```

This writes mock predictions, timing metadata, compact run status, timed score CSVs, and an executed notebook under `results/timing_smoke/` and `/tmp/benchmark_analysis_timing_smoke.ipynb`.

To re-run the real one-target ESMFold/OmegaFold smoke with TM-score validation:

```bash
bash scripts/smoke_test_real_esmfold_omegafold_with_tmscore.sh
```

This writes real backend predictions and scores under `results/real_backend_smoke/`. The script uses `--models esmfold,omegafold` for both inference and scoring so intentionally omitted enabled backends do not produce warning noise. To include the now-validated Boltz-2 and Chai-1 backends in the same smoke directory, run the controller/scorer with `--models esmfold,omegafold,boltz2,chai1`.

For full CASP target preparation, fetch references first, then prepare the target metadata:

```bash
python scripts/fetch_reference_pdbs.py \
  --input-csv CASP_csv/casp15_casp16_prepare_targets_input.csv \
  --references-dir data/references

python prepare_targets_from_csv.py \
  --input-csv CASP_csv/casp15_casp16_prepare_targets_input.csv \
  --output-targets data/targets/targets.csv \
  --references-dir data/references \
  --sequences-dir data/sequences \
  --overwrite
```

The notebook defaults to `data/targets/targets_first5.csv` when it exists and discovers score CSVs under `data/scores`. Override these paths when needed:

```bash
TARGETS_CSV=data/targets/targets_first5.csv RESULTS_DIR=data/scores \
  jupyter notebook notebooks/benchmark_analysis.ipynb
```

For timed smoke-test outputs:

```bash
TARGETS_CSV=data/targets/targets_first5.csv RESULTS_DIR=results/timing_smoke/scores \
  jupyter notebook notebooks/benchmark_analysis.ipynb
```

## Scoring and Ranking

The benchmark now records both local and global structural metrics.

Primary ranking metric:

- `lddt_ca`: C-alpha-only local distance difference test. Higher is better.

Secondary ranking metric:

- `tmalign_tm_score_ref`: TM-score from TM-align/US-align, normalized by the reference length. Higher is better.

`folding-benchmark` includes the Bioconda `USalign` package on this machine, so `--use-tmalign --tmalign-bin auto` populates TM-score columns locally.

Additional diagnostic metrics:

- `tmalign_rmsd`: RMSD from TM-align/US-align. Lower is better.
- `ca_rmsd`: C-alpha RMSD using the configured matching mode. Lower is better.
- `n_aligned_ca`: number of aligned C-alpha atoms.

Current scoring also records TM-score normalized by prediction length, TM-align aligned length, TM-align sequence identity, C-alpha diagnostic counts, missing residue lists, and internal RMSD Z-score across all successful predictions for one target.

For the current benchmark, lDDT-C-alpha is treated as the major metric because it measures local distance agreement and is superposition-free. TM-score remains the main global-fold metric and is used as the secondary ranking criterion.

For very short targets such as Chignolin, lDDT-C-alpha and TM-score can be noisy. Chignolin is mainly a smoke-test target; ubiquitin is the first more meaningful folded-protein target.

Future scoring should include GDT_TS, runtime, GPU memory, and energy consumption or CO2 estimates.

## Model-Level Summary and Ranking

The raw score CSV has one row per predicted structure. The model summary CSV has one row per model/backend and selects the best prediction for each model.

```bash
python scripts/03_summarize_scores.py \
  --scores data/scores/1UAO_chignolin_scores.csv \
  --output data/scores/1UAO_chignolin_model_summary.csv \
  --markdown-output data/scores/1UAO_chignolin_model_summary.md
```

By default, ranking uses `lddt_ca` as the primary metric, `tmalign_tm_score_ref` as the secondary metric, `tmalign_rmsd` as the tertiary metric, and `ca_rmsd` as the quaternary metric. Higher `lddt_ca` and `tmalign_tm_score_ref` are better; lower `tmalign_rmsd` and `ca_rmsd` are better.

## Multi-Target Benchmark

Use `data/targets/targets.csv` as the source of truth for benchmark targets. Chignolin / `1UAO_chignolin` is a 10-residue smoke-test peptide; ubiquitin / `1UBQ_ubiquitin` is the first larger single-chain protein target.

Prepare FASTA files from the target table:

```bash
python scripts/prepare_targets.py \
  --targets data/targets/targets.csv \
  --overwrite
```

Run all targets through prediction, scoring, and per-target summaries:

```bash
python scripts/04_run_benchmark_targets.py \
  --targets data/targets/targets.csv \
  --config configs/models.yaml \
  --top-k 5 \
  --only-enabled-models \
  --use-tmalign \
  --match-mode sequential
```

Aggregate model summaries across targets:

```bash
python scripts/05_summarize_all_targets.py \
  --targets data/targets/targets.csv \
  --scores-dir data/scores \
  --out-csv data/scores/all_targets_model_summary.csv \
  --out-md data/scores/all_targets_model_summary.md
```

## Current Model Status

The active target set is exactly two targets: `1UAO_chignolin` and `1UBQ_ubiquitin`. The benchmark has currently been validated only with models that produced standardized `rank_*.pdb` files and were successfully read by the scoring script.

| Model | Enabled | Validated on 1UAO | Validated on 1UBQ | Structures per target | Notes |
|---|---|---|---|---:|---|
| ESMFold (`esmfold`) | yes | yes | yes | 1 | Deterministic/single-output sequence baseline. |
| OmegaFold (`omegafold`) | yes | yes | yes | 1 | Deterministic/single-output sequence baseline. |
| Chai-1 (`chai1`) | yes | yes | yes | 5 | Uses genuine generated samples only. |
| Boltz-2 (`boltz2`) | yes | yes | yes | 5 | Current Boltz backend; uses genuine generated samples only. |
| OpenFold (`openfold`) | yes | yes | yes | 1 | Canonical default uses `runners/run_openfold_msa.sh` with fresh ColabFold/MMseqs2 A3M input; single-sequence mode remains an explicit ablation. See `model-installation/openfold.md`. |
| OpenFold3 (`openfold3`) | no | no | no | 0 | AF3-style open implementation; setup pending. |
| ColabFold (`colabfold`) | yes | yes | yes | 5 | Canonical default uses local ColabFold/MMseqs2 MSA mode with AF2-PTM parameters; single-sequence mode remains an explicit ablation. |
| AlphaFold2 (`alphafold2`) | no | no | no | 0 | Canonical AF2 baseline; full databases not required for this project unless explicitly requested. |
| AlphaFold3 (`alphafold3`) | no | no | no | 0 | Future optional restricted/non-commercial baseline; weights and outputs require separate terms review. |

The old backend ID `boltz` is deprecated. `runners/run_boltz.sh` is retained only as a compatibility wrapper that delegates to `runners/run_boltz2.sh`.

GPU defaults and smoke notes:

- `scripts/run_benchmark_from_targets.py` now defaults backend runs to GPU where supported by injecting `BOLTZ_ACCELERATOR=gpu`, `CHAI1_DEVICE=cuda:0`, `ESMFOLD_CPU_ONLY=0`, and `OPENFOLD_DEVICE=cuda:0` unless the caller already set those variables.
- The benchmark driver runs `colabfold` and `openfold` before other enabled models and applies a 5-second post-run GPU cooldown by default.
- Boltz-2 Chignolin CUDA smoke passed with `BOLTZ_ACCELERATOR=gpu`.
- Chai-1 Chignolin CUDA smoke passed with `CHAI1_DEVICE=cuda:0`.
- ESMFold Chignolin CUDA smoke passed with `ESMFOLD_CPU_ONLY=0`.
- OpenFold CUDA smoke passed with `OPENFOLD_MODE=single_sequence OPENFOLD_DEVICE=cuda:0`; the 2026-05-19 7ROA run produced `rank_001.pdb` in `results/backend_smoke/openfold_single_sequence/`.
- OmegaFold's environment sees CUDA through PyTorch and its Chignolin smoke prediction completed successfully.
- ColabFold CUDA smoke now passes after installing `jax[cuda12]==0.5.3`; its JAX stack reports CUDA devices, and the 2026-05-19 7ROA run produced `rank_001.pdb` in `results/backend_smoke/colabfold_single_sequence/`.

A one-target six-backend real smoke for `esmfold`, `omegafold`, `boltz2`, `chai1`, `colabfold`, and `openfold` passed on 7ROA on 2026-05-19 under `results/backend_smoke/six_backend_single_sequence/`. On 2026-05-20 the canonical default-mode config was updated so `colabfold` and `openfold` use MSA-capable default paths while the suffixed single/MSA IDs remain side experiments. The current canonical score outputs should contain 18 rows per target: ESMFold 1, OmegaFold 1, Chai-1 5, Boltz-2 5, ColabFold 5, and OpenFold 1. The cross-target aggregate summary is `data/scores/all_targets_model_summary.csv`.

## ColabFold MSA Timing/Carbon Variant

The main benchmark uses canonical `colabfold` and records MSA provenance in metadata. The ColabFold runner also supports explicit ablation model IDs for comparing no-MSA and local-MSA modes:

| Model ID | Meaning |
|---|---|
| `colabfold_single` | ColabFold with `--msa-mode single_sequence` |
| `colabfold_msa` | ColabFold with local MMseqs2 MSA search using `/data/chen/protein_folding_databases/colabfold` |

Use `scripts/smoke_test_colabfold_single_vs_msa_first5_with_carbon.sh` to rerun the first-five comparison. The MSA runner removes the run-local MSA search directory before each inference and runs `colabfold_search` inside the timed CodeCarbon-tracked subprocess, so timing and carbon include both MSA generation and structure prediction. Results are written to `results/colabfold_single_vs_msa_first5_carbon/`.

## OpenFold With ColabFold-Generated MSA

The main benchmark uses canonical `openfold` and records MSA provenance in metadata. The OpenFold runner set also includes explicit ablation model IDs for comparing dummy/single-sequence input against a freshly generated ColabFold/MMseqs2 MSA:

| Model ID | Meaning |
|---|---|
| `openfold_single` | OpenFold single-sequence/dummy-MSA smoke path |
| `openfold_msa` | OpenFold using a run-local ColabFold/MMseqs2 A3M from `/data/chen/protein_folding_databases/colabfold` |

Use `scripts/smoke_test_openfold_single_vs_msa_first5_with_carbon.sh` to rerun the first-five comparison. The MSA runner removes its run-local alignment directory, runs `colabfold_search`, copies the generated A3M into OpenFold's precomputed alignment layout, and runs OpenFold inference in the same timed CodeCarbon-tracked subprocess. Results are written to `results/openfold_single_vs_msa_first5_carbon/`.

## 2026-05-21 AF2/OpenFold3 Smoke Update

AF2 was inspected using the official AlphaFold2 source cloned at `models/alphafold`, but no `af2` benchmark backend was added. The exact blocker is documented in `model-installation/af2.md` and `results/backend_smoke/af2_default/BLOCKED.md`: no separate AF2 environment or official AlphaFold database layout is configured, and reusing ColabFold would duplicate the existing `colabfold` backend.

OpenFold3 was cloned at `models/openfold-3` and inspected. The one-target smoke was not attempted because upstream docs require CUDA 12.1+ and at least a 32 GB GPU for inference, while the local RTX A5000 GPUs expose about 24 GB each; no `openfold3` environment or model parameters are installed. Details are in `model-installation/openfold3.md` and `results/backend_smoke/openfold3_default/BLOCKED.md`.


## Experimental Shared-MSA Backends

A reusable ColabFold/MMseqs2 MSA cache workflow is available for experimental backends. `scripts/generate_colabfold_msas_from_targets.py` writes per-target A3M files and `msa_metadata.csv`; `scripts/run_benchmark_from_targets.py` can pass those rows into runners with `--shared-msa-metadata` and `--shared-msa-root`. Model inference metadata marks the shared MSA as reused and excludes MSA search from model timing/carbon; `scripts/summarize_shared_msa_benchmark.py` joins MSA cost, inference cost, and structure scores.

On 2026-05-22, `protenix` and `openfold3` both passed a first-five shared-MSA smoke under `results/protenix_openfold3_shared_msa_first5/`. These remain experimental and disabled in the canonical config.
