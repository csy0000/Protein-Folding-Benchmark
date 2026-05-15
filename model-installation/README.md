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

- [`boltz2`](boltz2.md): five-sample Boltz-2 backend in the current local setup.
- [`chai1`](chai1.md): five-sample Chai-1 backend in the current local setup.
- [`esmfold`](esmfold.md): single-output sequence baseline.
- [`colabfold`](colabfold.md): five ranked AF2-style outputs in single-sequence smoke mode.
- [`omegafold`](omegafold.md): single-output sequence baseline.
- [`openfold`](openfold.md): enabled from existing smoke outputs; easy CSV runner uses explicit single-sequence mode unless MSA databases are configured.

Future or disabled backends:

- [`alphafold2`](alphafold2.md)
- [`alphafold3`](alphafold3.md)
- [`openfold3`](openfold3.md)

For the CSV-driven benchmark pipeline, use:

```bash
python scripts/prepare_targets_from_csv.py --input-csv examples/example_targets.csv
python scripts/run_benchmark_from_targets.py --targets data/targets/targets.csv --top-k 5
python scripts/score_benchmark_from_targets.py --targets data/targets/targets.csv --top-k 5
```

The CSV benchmark driver defaults model runs to GPU where supported by setting
`BOLTZ_ACCELERATOR=gpu`, `CHAI1_DEVICE=cuda:0`, `ESMFOLD_CPU_ONLY=0`, and
`OPENFOLD_DEVICE=cuda:0` unless those variables are already set.
