# Model Installation Notes

Model source trees are expected under `models/`, but that directory is ignored
by Git. Keep tracked setup notes here so the benchmark is reproducible without
committing source checkouts, model weights, generated predictions, or databases.

Each backend note should cover:

- benchmark backend name from `configs/models.yaml`
- expected conda environment or container
- install command summary or official documentation pointer
- required environment variables
- smoke-test command
- benchmark output convention
- known local caveats

Current enabled/scored backends:

- `boltz2`
- `chai1`
- `esmfold`
- `colabfold`
- `omegafold`
- `openfold`

Future or disabled backends:

- `alphafold2`
- `alphafold3`
- `openfold3`
