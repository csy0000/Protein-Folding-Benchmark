# Model Installation Status

| Model | Backend ID | Environment | Repo path | Installed? | Runner exists? | Tested on 1UAO? | Top-k generated | Scoring succeeded? | Notes |
|---|---|---|---|---|---|---|---:|---|---|
| OpenFold | `openfold` | `openfold` | `models/openfold` | yes | yes | yes | 1 | yes | Python 3.7/PyTorch 1.12 OpenFold env installed from `models/openfold/environment.yml`; pinned `mkl<2024` and installed `gemmi`. Canonical default uses fresh ColabFold/MMseqs2 MSA input; `openfold_single`/`openfold_msa` remain explicit ablation IDs. |
| OpenFold3 | `openfold3` | `openfold3` | `models/openfold-3` | experimental | yes | 7ROA only | 1 | yes | Installed from PyPI `openfold3==0.4.1` with env-local CUDA toolkit 12.8 and checkpoint `weights/openfold3/of3-p2-155k.pt`; passed a one-target 7ROA low-memory smoke, but remains disabled in canonical config pending broader validation. |
| Protenix | `protenix` | `protenix` | `models/protenix` | experimental | yes | 7ROA and first-five CASP smoke | 1 | yes | PyPI `protenix==2.0.0` installed in a separate env with env-local CUDA toolkit 12.6 and cache/checkpoint under `weights/protenix`; shared ColabFold/MMseqs2 MSA smoke passed for 5/5 first-five targets. Disabled in canonical config. |
| Boltz-2 | `boltz2` | `boltz` | `models/boltz` | yes | yes | yes | 5 | yes | Current canonical Boltz backend. Runner defaults to CPU via `BOLTZ_ACCELERATOR=cpu`; Chignolin CUDA smoke passed with `BOLTZ_ACCELERATOR=gpu`. Uses disabled optional kernels, local model cache, and explicit single-sequence MSA mode. Legacy `runners/run_boltz.sh` is only a compatibility wrapper. |
| Chai-1 | `chai1` | `chai1` | `models/chai-lab` | yes | yes | yes | 5 | yes | Runner defaults to CPU via `CHAI1_DEVICE=cpu`; Chignolin CUDA smoke passed with `CHAI1_DEVICE=cuda:0`. Default benchmark mode is no-MSA/native embedding (`native_embedding_no_msa`); external MSAs/templates are optional in Chai-1 but not used by this runner. |
| ESMFold | `esmfold` | `esmfold` | `models/esm` | yes | yes | yes | 1 | yes | Runner defaults to CPU-only mode; Chignolin CUDA smoke passed with `ESMFOLD_CPU_ONLY=0`. Uses local ESM source, project-local Torch cache, and a checkpoint-key compatibility shim. |
| ColabFold | `colabfold` | `colabfold` | n/a | yes | yes | yes | 5 | yes | Installed from PyPI package `colabfold[alphafold]`; canonical default uses local ColabFold/MMseqs2 MSA mode with AF2-PTM parameters under `weights/colabfold`. `colabfold_single`/`colabfold_msa` remain explicit ablation IDs. |
| AlphaFold2 | `af2` | `af2` | `models/alphafold` | yes | yes | first-five CASP smoke | 1 | yes | Official DeepMind AlphaFold2 backend validated on 2026-05-26 with full AlphaFold database search, split MSA/features and JAX inference carbon metadata, and 5/5 first-five targets successful. Disabled in canonical config; use `tmp/backend_smoke/models_af2_only.yaml`. |
| AlphaFold3 | `alphafold3` | `alphafold3` | `models/alphafold3` | repo cloned | yes | no | 0 | no | Restricted-access baseline; weights require separate approval/terms. Placeholder environment and runner added. |
| OmegaFold | `omegafold` | `omegafold` | `models/OmegaFold` | yes | yes | yes | 1 | yes | Single-sequence baseline; produced `rank_001.pdb` and scoring succeeded. |

Chignolin currently has a model-level summary generated for the validated models at `data/scores/1UAO_chignolin_model_summary.csv`.

Ubiquitin / `1UBQ_ubiquitin` has also been run for the currently enabled validated models. Its per-target score and summary files are:

- `data/scores/1UBQ_ubiquitin_scores.csv`
- `data/scores/1UBQ_ubiquitin_model_summary.csv`

The current enabled model set is `esmfold`, `omegafold`, `chai1`, `boltz2`, `colabfold`, and `openfold`. Main/default-mode runs keep these canonical names and write MSA provenance columns to `run_metadata.csv`; suffixed `*_single` and `*_msa` names are side-study ablations. `scripts/run_benchmark_from_targets.py` defaults carbon tracking to world-average accounting and can be overridden with `--carbon-country-iso-code CHE`. It defaults backend runs to GPU where supported by injecting `BOLTZ_ACCELERATOR=gpu`, `CHAI1_DEVICE=cuda:0`, `ESMFOLD_CPU_ONLY=0`, and `OPENFOLD_DEVICE=cuda:0` unless the caller already set those variables. The driver runs `colabfold` and `openfold` before other enabled models and waits 5 seconds after each target/model run by default to let GPU memory settle. The current canonical score CSVs contain 18 rows per target, include lDDT-C-alpha columns from `scripts/02_score_predictions.py`, and rank models by lDDT-C-alpha first, TM-score normalized by reference length second, TM-align RMSD third, and C-alpha RMSD as a diagnostic tie-breaker. The cross-target summary is `data/scores/all_targets_model_summary.csv`.

## Optional OpenFold Setup

OpenFold is present as an enabled backend with existing single-sequence smoke outputs for both active targets and a fresh 7ROA single-sequence smoke from 2026-05-19. To reproduce or extend the installation, use the tracked notes in `model-installation/openfold.md`. The short setup outline for the current checkout is:

```bash
git clone https://github.com/aqlaboratory/openfold.git models/openfold
cd models/openfold
mamba env create -n openfold -f environment.yml
conda activate openfold
mamba install -n openfold -c conda-forge "mkl<2024" --yes
conda run -n openfold python -m pip install gemmi
```

For MSA/template-based inference, OpenFold also needs AlphaFold/OpenFold-compatible databases. Do not download large databases for this benchmark unless explicitly requested.

Runtime configuration:

```bash
export OPENFOLD_REPO=/path/to/openfold
export OPENFOLD_PARAMS_DIR=/path/to/openfold_params
export OPENFOLD_DATA_DIR=/path/to/openfold_databases
```

The current smoke path has produced `rank_001.pdb` for both active targets and for the 7ROA 2026-05-19 smoke, and scoring succeeds. Canonical OpenFold now uses the `runners/run_openfold_msa.sh` path with fresh ColabFold/MMseqs2 A3M input. Use `openfold_single` only for explicit smoke/ablation tests.

AlphaFold3 remains disabled as a future restricted/non-commercial-use backend and should not be enabled until parameter and output usage terms are compatible with the intended use.


## ColabFold MSA Mode Update (2026-05-20)

`colabfold_single` and `colabfold_msa` were validated as explicit temporary benchmark variants. `colabfold_msa` uses the local ColabFold/MMseqs2 database at `/data/chen/protein_folding_databases/colabfold` and reruns MSA search inside each timed/carbon-tracked inference. The first-five comparison passed with 10/10 successful runs under `results/colabfold_single_vs_msa_first5_carbon/`. OpenFold MSA mode was attempted as `openfold_msa` and blocked by missing OpenFold/AlphaFold-compatible databases under `work/openfold_inputs`, not by ColabFold database availability.


## OpenFold ColabFold-MSA Mode Update (2026-05-20)

`openfold_single` and `openfold_msa` were validated as explicit temporary benchmark variants. `openfold_msa` uses `runners/run_openfold_msa.sh` to generate a fresh ColabFold/MMseqs2 A3M from `/data/chen/protein_folding_databases/colabfold` during every model run, then passes it to OpenFold through `--use-precomputed-alignments`. The first-five comparison passed with 10/10 successful runs under `results/openfold_single_vs_msa_first5_carbon/`.

## 2026-05-21 AF2/OpenFold3 Smoke Update

The 2026-05-21 AF2 attempt was initially blocked by missing official AF2 environment/database setup. That blocker is superseded by the 2026-05-26 official `af2` first-five run documented below.

OpenFold3 is installed experimentally in the separate `openfold3` environment with PyPI `openfold3==0.4.1`, env-local CUDA toolkit 12.8, and checkpoint `weights/openfold3/of3-p2-155k.pt`. A 7ROA one-target low-memory smoke succeeded under `results/backend_smoke/openfold3_default/` with `rank_001.pdb`, runtime `82.752562` seconds, `2.3836289056808897` g CO2e, lDDT-C-alpha `0.4756351915054986`, and TM-score normalized by reference length `0.39914`. It remains disabled in the canonical config pending broader validation; details are in `model-installation/openfold3.md`.


## Shared ColabFold MSA Cache Update (2026-05-22)

A shared ColabFold/MMseqs2 MSA cache workflow was added for experimental backends that can consume precomputed A3M files. MSA search is run once per target with `scripts/generate_colabfold_msas_from_targets.py`; inference runners receive `SHARED_MSA_*` paths from `scripts/run_benchmark_from_targets.py`, and the benchmark records `msa_generation_included_in_timing=false`, `msa_generation_included_in_carbon=false`, and `msa_reused=true` for model inference rows.

Generated cache outputs:

- One-target 7ROA cache: `results/shared_msa_colabfold_7ROA/msa_metadata.csv`
- First-five cache: `results/shared_msa_colabfold_first5/msa_metadata.csv`

Experimental shared-MSA results:

- `openfold3`: 5/5 first-five targets succeeded using `runners/run_openfold3_shared_msa.sh`; mean lDDT-C-alpha `0.8514732150023233`, mean TM-score-ref `0.834862`.
- `protenix`: 5/5 first-five targets succeeded using `runners/run_protenix_shared_msa.sh`; mean lDDT-C-alpha `0.8665522357206289`, mean TM-score-ref `0.855224`.

Summary files:

- `results/protenix_openfold3_shared_msa_first5/run_metadata.csv`
- `results/protenix_openfold3_shared_msa_first5/scores/all_targets_model_summary.csv`
- `results/protenix_openfold3_shared_msa_first5/shared_msa_score_cost_summary.csv`

These backends remain experimental and are not enabled in `configs/models.yaml`.

## 2026-05-22 unified shared-MSA status

`colabfold`, `openfold`, `protenix`, and `openfold3` all completed the first-five target set using the same per-target ColabFold/MMseqs2 A3M cache in `results/four_msa_models_shared_msa_first5/msa/`. The ColabFold shared runner passes the A3M directly to `colabfold_batch`; the OpenFold shared runner copies it into a precomputed-alignment layout; Protenix and OpenFold3 use their existing shared-MSA adapters. All 20 target/model inference rows succeeded and were scored.

## 2026-05-26 Official AF2 Split-Stage Update

Official AlphaFold2 is installed as backend ID `af2` in the separate `af2` environment. The runner `runners/run_af2.sh` calls `scripts/run_af2_split_pipeline.py`, imports DeepMind AlphaFold from `models/alphafold`, uses `/data/chen/protein_folding_databases/alphafold`, and records split-stage metadata for `msa_features` and `inference` in `af2_stage_metadata.csv`.

The first-five run under `results/af2_first5_split_carbon/` produced 5/5 successful `rank_001.pdb` predictions and scored successfully with mean lDDT-C-alpha `0.8754336456168662`, mean TM-score-ref `0.852168`, and mean C-alpha RMSD `4.02535248453391`. Mean total runtime was `1854.0478058` seconds per target, with mean total CO2e `49.61637650354013` g per target.
