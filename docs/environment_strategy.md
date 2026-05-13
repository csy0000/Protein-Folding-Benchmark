# Environment Strategy

Use one driver/scoring environment and one isolated environment per folding model.

The `folding-benchmark` environment is only for orchestration, parsing, scoring, notebooks, and lightweight utilities. Each folding backend has its own environment: `esmfold`, `omegafold`, `boltz`, `chai1`, `colabfold`, `alphafold2`, `openfold`, and `rosettafold`.

This policy avoids dependency conflicts between PyTorch, CUDA, JAX, OpenMM, NumPy, HH-suite, and model-specific packages. It also improves reproducibility, simplifies debugging, and lets one broken model be reinstalled without touching the full project.

AlphaFold2 often requires JAX/CUDA-specific setup and model parameters. This project should not download full AlphaFold, ColabFold, or RoseTTAFold databases unless the user explicitly requests them. OpenFold and RoseTTAFold may need repository-specific installation steps after cloning.
