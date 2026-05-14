# Environment Strategy

Use one driver/scoring environment and one isolated environment per folding backend.

The `folding-benchmark` environment is only for orchestration, parsing, scoring, notebooks, and lightweight utilities. Do not merge model backends into one conda environment.

Preferred environment names:

| Environment | Purpose |
|---|---|
| `folding-benchmark` | Driver and scoring only |
| `openfold` | OpenFold backend |
| `openfold3` | OpenFold3 backend |
| `boltz2` | Preferred Boltz-2 environment name for a fresh setup |
| `boltz` | Current working Boltz-2 environment in this checkout |
| `chai1` | Chai-1 backend |
| `esmfold` | ESMFold backend |
| `colabfold` | ColabFold backend |
| `alphafold2` | AlphaFold2 backend |
| `alphafold3` | AlphaFold3 backend |
| `omegafold` | OmegaFold backend |

The benchmark backend ID is `boltz2`, but the current working conda environment may remain named `boltz` for compatibility. Do not rename or remove a working `boltz` environment just to match the backend ID.

This policy avoids dependency conflicts between PyTorch, CUDA, JAX, OpenMM, NumPy, HH-suite, and model-specific packages. It also improves reproducibility, simplifies debugging, and lets one broken model be reinstalled without touching the full project.

AlphaFold2 often requires JAX/CUDA-specific setup and model parameters. AlphaFold3 model parameters and outputs are restricted-access and subject to the applicable Google/DeepMind terms, including non-commercial-use restrictions; keep AlphaFold3 disabled unless the intended use has appropriate rights, licensing, and approval. This project should not download full AlphaFold, AlphaFold3, ColabFold, or other large databases unless the user explicitly requests them.
