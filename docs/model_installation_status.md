# Model Installation Status

| Model | Backend ID | Environment | Repo path | Installed? | Runner exists? | Tested on 1UAO? | Top-k generated | Scoring succeeded? | Notes |
|---|---|---|---|---|---|---|---:|---|---|
| OpenFold | `openfold` | `openfold` | `models/openfold` | yes | yes | yes | 1 | yes | Enabled after two-target smoke validation. Existing score rows come from prior single-sequence smoke outputs. The runner now defaults to MSA mode and requires configured databases for fresh prediction. See `model-installation/openfold.md`. |
| OpenFold3 | `openfold3` | `openfold3` | `models/openfold-3` | repo cloned | yes | no | 0 | no | Placeholder environment and runner added; package installation and validation pending. |
| Boltz-2 | `boltz2` | `boltz` | `models/boltz` | yes | yes | yes | 5 | yes | Current canonical Boltz backend. Runner defaults to CPU via `BOLTZ_ACCELERATOR=cpu`; Chignolin CUDA smoke passed with `BOLTZ_ACCELERATOR=gpu`. Uses disabled optional kernels, local model cache, and explicit single-sequence MSA mode. Legacy `runners/run_boltz.sh` is only a compatibility wrapper. |
| Chai-1 | `chai1` | `chai1` | `models/chai-lab` | yes | yes | yes | 5 | yes | Runner defaults to CPU via `CHAI1_DEVICE=cpu`; Chignolin CUDA smoke passed with `CHAI1_DEVICE=cuda:0`. Uses local asset cache and Chai-compatible FASTA headers. |
| ESMFold | `esmfold` | `esmfold` | `models/esm` | yes | yes | yes | 1 | yes | Runner defaults to CPU-only mode; Chignolin CUDA smoke passed with `ESMFOLD_CPU_ONLY=0`. Uses local ESM source, project-local Torch cache, and a checkpoint-key compatibility shim. |
| ColabFold | `colabfold` | `colabfold` | `models/ColabFold` | yes | yes | yes | 5 | yes | Runner uses `colabfold_batch` with `--msa-mode single_sequence`, five ranked AF2-PTM models, local parameter cache, and no local sequence database requirement for the current smoke workflow. CUDA JAX packages are installed; Chignolin GPU smoke logs `Running on GPU`. |
| AlphaFold2 | `alphafold2` | `alphafold2` | `models/alphafold` | yes | yes | no | 0 | no | Canonical AF2 baseline; official parameters/databases are not required unless explicitly requested. |
| AlphaFold3 | `alphafold3` | `alphafold3` | `models/alphafold3` | repo cloned | yes | no | 0 | no | Restricted-access baseline; weights require separate approval/terms. Placeholder environment and runner added. |
| OmegaFold | `omegafold` | `omegafold` | `models/OmegaFold` | yes | yes | yes | 1 | yes | Single-sequence baseline; produced `rank_001.pdb` and scoring succeeded. |

Chignolin currently has a model-level summary generated for the validated models at `data/scores/1UAO_chignolin_model_summary.csv`.

Ubiquitin / `1UBQ_ubiquitin` has also been run for the currently enabled validated models. Its per-target score and summary files are:

- `data/scores/1UBQ_ubiquitin_scores.csv`
- `data/scores/1UBQ_ubiquitin_model_summary.csv`

The current enabled model set is `esmfold`, `omegafold`, `chai1`, `boltz2`, `colabfold`, and `openfold`. `scripts/run_benchmark_from_targets.py` defaults these runs to GPU where supported by injecting `BOLTZ_ACCELERATOR=gpu`, `CHAI1_DEVICE=cuda:0`, `ESMFOLD_CPU_ONLY=0`, and `OPENFOLD_DEVICE=cuda:0` unless the caller already set those variables. The current canonical score CSVs contain 18 rows per target, include lDDT-C-alpha columns from `scripts/02_score_predictions.py`, and rank models by lDDT-C-alpha first, TM-score normalized by reference length second, TM-align RMSD third, and C-alpha RMSD as a diagnostic tie-breaker. The cross-target summary is `data/scores/all_targets_model_summary.csv`.

## Optional OpenFold Setup

OpenFold is present as an enabled backend with existing single-sequence smoke outputs for both active targets. To reproduce or extend the installation, use the tracked notes in `model-installation/openfold.md`. The short setup outline is:

```bash
git clone https://github.com/aqlaboratory/openfold.git models/openfold
cd models/openfold
mamba env create -n openfold -f environment.yml
conda activate openfold
python setup.py install
bash scripts/download_alphafold_params.sh /path/to/openfold_params
```

For MSA/template-based inference, OpenFold also needs AlphaFold/OpenFold-compatible databases. Do not download large databases for this benchmark unless explicitly requested.

Runtime configuration:

```bash
export OPENFOLD_REPO=/path/to/openfold
export OPENFOLD_PARAMS_DIR=/path/to/openfold_params
export OPENFOLD_DATA_DIR=/path/to/openfold_databases
```

The current smoke path has produced `rank_001.pdb` for both active targets and scoring succeeds. Fresh runner invocations default to MSA mode; provide real template/databases before drawing scientific conclusions. Use `OPENFOLD_MODE=single_sequence` only for explicit smoke tests.

AlphaFold3 remains disabled as a future restricted/non-commercial-use backend and should not be enabled until parameter and output usage terms are compatible with the intended use.
