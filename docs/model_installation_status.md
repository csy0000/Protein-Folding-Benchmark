# Model Installation Status

| Model | Backend ID | Environment | Repo path | Installed? | Runner exists? | Tested on 1UAO? | Top-k generated | Scoring succeeded? | Notes |
|---|---|---|---|---|---|---|---:|---|---|
| OpenFold | `openfold` | `openfold` | `models/openfold` | yes | yes | no | 0 | no | AF2-style PyTorch implementation; runner placeholder unless configured later. |
| OpenFold3 | `openfold3` | `openfold3` | `models/openfold-3` | repo cloned | yes | no | 0 | no | Placeholder environment and runner added; package installation and validation pending. |
| Boltz-2 | `boltz2` | `boltz` | `models/boltz` | yes | yes | yes | 5 | yes | Current canonical Boltz backend. Runner uses `boltz predict` with five diffusion samples, CPU mode, disabled optional kernels, local model cache, and explicit single-sequence MSA mode. Legacy `runners/run_boltz.sh` is only a compatibility wrapper. |
| Chai-1 | `chai1` | `chai1` | `models/chai-lab` | yes | yes | yes | 5 | yes | Runner uses `chai-lab fold` with five diffusion samples, CPU mode, local asset cache, and Chai-compatible FASTA headers. |
| ESMFold | `esmfold` | `esmfold` | `models/esm` | yes | yes | yes | 1 | yes | Runner uses local ESM source, CPU-only mode, project-local Torch cache, and a checkpoint-key compatibility shim. |
| ColabFold | `colabfold` | `colabfold` | `models/ColabFold` | yes | yes | yes | 5 | yes | Runner uses `colabfold_batch` with `--msa-mode single_sequence`, five ranked AF2-PTM models, local parameter cache, and no local sequence database requirement for the current smoke workflow. |
| AlphaFold2 | `alphafold2` | `alphafold2` | `models/alphafold` | yes | yes | no | 0 | no | Canonical AF2 baseline; official parameters/databases are not required unless explicitly requested. |
| AlphaFold3 | `alphafold3` | `alphafold3` | `models/alphafold3` | repo cloned | yes | no | 0 | no | Restricted-access baseline; weights require separate approval/terms. Placeholder environment and runner added. |
| OmegaFold | `omegafold` | `omegafold` | `models/OmegaFold` | yes | yes | yes | 1 | yes | Single-sequence baseline; produced `rank_001.pdb` and scoring succeeded. |

Chignolin currently has a model-level summary generated for the validated models at `data/scores/1UAO_chignolin_model_summary.csv`.

Ubiquitin / `1UBQ_ubiquitin` has also been run for the currently enabled validated models. Its per-target score and summary files are:

- `data/scores/1UBQ_ubiquitin_scores.csv`
- `data/scores/1UBQ_ubiquitin_model_summary.csv`

The current enabled model set is `esmfold`, `omegafold`, `chai1`, `boltz2`, and `colabfold`. The current canonical score CSVs contain 17 rows per target, and the cross-target summary is `data/scores/all_targets_model_summary.csv`.
