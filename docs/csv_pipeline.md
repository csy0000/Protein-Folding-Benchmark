# CSV-Driven Benchmark Pipeline

Use `scripts/prepare_targets_from_csv.py` to turn a user CSV into the existing
benchmark target table. Required input columns are:

```csv
PDBID,chain
1UAO,A
1UBQ,A
```

Optional columns are `name`, `description`, `sequence`, `reference_path`, and
`enabled`. Rows with `enabled=false` are skipped.

The prepared target table keeps the existing schema:

```csv
target_id,pdb_id,chain_id,sequence,reference_pdb,notes
```

Run the pipeline:

```bash
python scripts/prepare_targets_from_csv.py --input-csv examples/example_targets.csv
python scripts/run_benchmark_from_targets.py --targets data/targets/targets.csv --config configs/models.yaml --top-k 5
python scripts/score_benchmark_from_targets.py --targets data/targets/targets.csv --config configs/models.yaml --top-k 5
python scripts/05_summarize_all_targets.py --targets data/targets/targets.csv --scores-dir data/scores --out-csv data/scores/all_targets_model_summary.csv --out-md data/scores/all_targets_model_summary.md
```

`boltz2`, `chai1`, and `colabfold` can produce up to five ranked structures in
the current setup. `esmfold`, `omegafold`, and `openfold` currently produce one
standardized prediction. The easy runner uses `OPENFOLD_MODE=single_sequence`
for OpenFold unless `--openfold-mode msa` is requested.

`scripts/run_benchmark_from_targets.py` defaults model runs to GPU where the
local backend supports it. It injects these environment defaults unless they are
already set by the caller:

```text
BOLTZ_ACCELERATOR=gpu
CHAI1_DEVICE=cuda:0
ESMFOLD_CPU_ONLY=0
OPENFOLD_DEVICE=cuda:0
```

ColabFold uses its CUDA-enabled JAX environment and OmegaFold uses its backend
auto-detection. To force a CPU run for a specific backend, set the corresponding
environment variable before launching the benchmark.

The driver runs `colabfold` and `openfold` before the other enabled backends, so
the AF2-style/JAX-heavy jobs run before later PyTorch backends add memory
pressure. After each target/model run, it waits 5 seconds by default
(`--gpu-cleanup-sleep-sec 5`) to give exited CUDA/JAX/PyTorch processes time to
release GPU memory. Set `--gpu-cleanup-sleep-sec 0` to disable this cooldown.

Analyze outputs with:

```bash
jupyter notebook notebooks/benchmark_analysis.ipynb
```

## CASP15/CASP16 First-Five Smoke Test

Prepare the first five enabled CASP rows, download their RCSB PDB references,
and write `data/targets/targets_first5.csv` with:

```bash
bash scripts/smoke_test_prepare_casp_first5.sh
```

Then run or dry-run the benchmark against that target table:

```bash
python scripts/run_benchmark_from_targets.py --targets data/targets/targets_first5.csv --config configs/models.yaml --top-k 5 --dry-run
python scripts/score_benchmark_from_targets.py --targets data/targets/targets_first5.csv --config configs/models.yaml --top-k 5 --use-tmalign
```

Inference timing is written by `scripts/run_benchmark_from_targets.py` to
`results/run_metadata.csv` by default, or to the path passed with
`--run-metadata`. A compact target/model status table is written to
`data/run_status.csv` by default, or to the path passed with `--run-status`.
The scorer merges timing into per-target score CSVs when metadata are
available. Model runs are retried up to `--max-trials` times per target/model;
the default is 5. The run metadata records `trials_run`, `max_trials`, and
`successful_trial` instead of start/end timestamps.

For a fast end-to-end timing smoke test that avoids expensive model inference,
use the mock runner path:

```bash
bash scripts/smoke_test_casp_first5_with_timing.sh
```

This writes:

```text
results/timing_smoke/run_metadata.csv
results/timing_smoke/run_status.csv
results/timing_smoke/scores/*_scores.csv
/tmp/benchmark_analysis_timing_smoke.ipynb
```

For the current real-backend ESMFold/OmegaFold smoke, including USalign-backed TM-score validation, run:

```bash
bash scripts/smoke_test_real_esmfold_omegafold_with_tmscore.sh
```

The script writes under `results/real_backend_smoke/` and passes `--models esmfold,omegafold` to both inference and scoring.

For the full CASP table, fetch references before preparing targets:

```bash
python scripts/fetch_reference_pdbs.py --input-csv CASP_csv/casp15_casp16_prepare_targets_input.csv --references-dir data/references
python prepare_targets_from_csv.py --input-csv CASP_csv/casp15_casp16_prepare_targets_input.csv --output-targets data/targets/targets.csv --references-dir data/references --sequences-dir data/sequences --overwrite
```
