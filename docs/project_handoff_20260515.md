# Project Handoff: Protein-Folding-Benchmark

Date: 2026-05-15  
Last updated by Codex: 2026-05-18

This repository is a local benchmark harness for protein structure prediction
models. It prepares targets from CSV files, runs enabled local model backends,
standardizes predictions as `rank_*.pdb`, scores structures against references,
and summarizes target-level and cross-target model performance.

## Current Stage

The project is ready for small and medium CSV-driven benchmark batches with six
working local backends:

| Backend ID | Model | Runner | Environment | Output count |
|---|---|---|---|---:|
| `colabfold` | ColabFold | `runners/run_colabfold.sh` | `colabfold` | up to 5 |
| `openfold` | OpenFold | `runners/run_openfold.sh` | `openfold` | 1 in current easy setup |
| `boltz2` | Boltz-2 | `runners/run_boltz2.sh` | `boltz` | up to 5 |
| `chai1` | Chai-1 | `runners/run_chai1.sh` | `chai1` | up to 5 |
| `esmfold` | ESMFold | `runners/run_esmfold.sh` | `esmfold` | 1 |
| `omegafold` | OmegaFold | `runners/run_omegafold.sh` | `omegafold` | 1 |

The benchmark driver prioritizes `colabfold` and `openfold` before the other
enabled backends, then waits after each target/model run so CUDA/JAX/PyTorch
processes have time to release GPU memory. Tune this with
`--gpu-cleanup-sleep-sec`.

## Disabled Or Future Backends

These backends are intentionally inactive:

| Backend ID | Status | Reason |
|---|---|---|
| `alphafold2` | disabled/future | Full AF2 database setup is not available locally. |
| `openfold3` | disabled/future | Setup and validation pending. |
| `alphafold3` | disabled/future | Restricted-access weights/outputs and terms review required. |

Do not download AlphaFold/OpenFold MSA/template databases as part of routine
benchmark runs. The current local machine does not have enough free disk for
full database trees.

## Repository Policy

`models/` is ignored by Git and should remain ignored. Do not commit model
source checkouts, weights, MSA databases, AlphaFold/OpenFold databases, large
prediction artifacts, large logs, or external downloaded packages.

Commit durable benchmark code and documentation instead:

- `scripts/`
- `runners/`
- `configs/`
- `notebooks/`
- `model-installation/`
- `README.md`
- `docs/`
- small CSV inputs and small metadata/status files

## Scoring And Ranking

Canonical scoring uses:

1. Primary metric: lDDT-C-alpha / `lddt_ca`
2. Secondary metric: TM-score normalized by reference length
3. Additional diagnostics: TM-align RMSD and C-alpha RMSD

Use enabled-model filtering so stale prediction directories do not contaminate
score CSVs:

```bash
python scripts/score_benchmark_from_targets.py \
  --targets data/targets/targets.csv \
  --config configs/models.yaml \
  --top-k 5 \
  --results-dir results \
  --use-tmalign
```

The scorer merges timing and retry metadata from `results/run_metadata.csv`
when available, including:

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

## CSV-Driven Workflow

Input CSVs need at least:

```csv
PDBID,chain
1UAO,A
1UBQ,A
```

Optional columns include `name`, `description`, `sequence`, `reference_path`,
and `enabled`. Rows with `enabled=false` are skipped.

Prepare targets:

```bash
python scripts/prepare_targets_from_csv.py \
  --input-csv examples/example_targets.csv \
  --output-targets data/targets/targets.csv \
  --references-dir data/references \
  --sequences-dir data/sequences
```

Fetch references first for CASP-style tables when the local references are
missing:

```bash
python scripts/fetch_reference_pdbs.py \
  --input-csv CASP_csv/casp15_casp16_prepare_targets_input.csv \
  --references-dir data/references
```

Run enabled models:

```bash
conda run -n folding-benchmark python scripts/run_benchmark_from_targets.py \
  --targets data/targets/targets.csv \
  --config configs/models.yaml \
  --top-k 5
```

For memory-sensitive runs, prefer smaller model subsets and fewer retries:

```bash
conda run -n folding-benchmark python scripts/run_benchmark_from_targets.py \
  --targets data/targets/targets_first5.csv \
  --config configs/models.yaml \
  --models colabfold,openfold \
  --top-k 5 \
  --max-trials 1 \
  --gpu-cleanup-sleep-sec 10
```

Score and summarize:

```bash
python scripts/score_benchmark_from_targets.py \
  --targets data/targets/targets.csv \
  --config configs/models.yaml \
  --top-k 5 \
  --results-dir results \
  --use-tmalign

python scripts/05_summarize_all_targets.py \
  --targets data/targets/targets.csv \
  --scores-dir data/scores \
  --out-csv data/scores/all_targets_model_summary.csv \
  --out-md data/scores/all_targets_model_summary.md
```

## Minimal Smoke Tests

Two known small targets are:

```text
1UAO_chignolin
1UBQ_ubiquitin
```

A small example CSV is tracked at:

```text
examples/example_targets.csv
```

Fast plumbing smoke without expensive inference:

```bash
bash scripts/smoke_test_prepare_casp_first5.sh
bash scripts/smoke_test_casp_first5_with_timing.sh
```

Single-model runner smoke examples:

```bash
bash runners/run_esmfold.sh data/sequences/1UAO_chignolin.fasta /tmp/esmfold_smoke 5
bash runners/run_omegafold.sh data/sequences/1UAO_chignolin.fasta /tmp/omegafold_smoke 5
BOLTZ_ACCELERATOR=gpu bash runners/run_boltz2.sh data/sequences/1UAO_chignolin.fasta /tmp/boltz2_smoke 5
CHAI1_DEVICE=cuda:0 bash runners/run_chai1.sh data/sequences/1UAO_chignolin.fasta /tmp/chai1_smoke 5
bash runners/run_colabfold.sh data/sequences/1UAO_chignolin.fasta /tmp/colabfold_smoke 5
OPENFOLD_MODE=single_sequence OPENFOLD_DEVICE=cuda:0 bash runners/run_openfold.sh data/sequences/1UAO_chignolin.fasta /tmp/openfold_smoke 1
```

## Model Notes

### Boltz-2

- Backend ID: `boltz2`
- Environment used by the current runner: `boltz`
- Runner: `runners/run_boltz2.sh`
- Produces up to five genuine diffusion samples.
- Defaults to CPU at the runner layer, but the CSV benchmark driver injects
  `BOLTZ_ACCELERATOR=gpu` unless the caller overrides it.
- Detailed notes: [Boltz-2 setup](../model-installation/boltz2.md)

Checks:

```bash
conda run -n boltz boltz --help
BOLTZ_ACCELERATOR=gpu bash runners/run_boltz2.sh data/sequences/1UAO_chignolin.fasta /tmp/boltz2_test 5
```

### Chai-1

- Backend ID: `chai1`
- Environment: `chai1`
- Runner: `runners/run_chai1.sh`
- Converts FASTA headers into Chai-compatible `protein|name=...` records.
- Produces up to five genuine samples.
- Defaults to CPU at the runner layer; use `CHAI1_DEVICE=cuda:0` for CUDA. The
  CSV benchmark driver injects this by default.
- Detailed notes: [Chai-1 setup](../model-installation/chai1.md)

### ESMFold

- Backend ID: `esmfold`
- Environment: `esmfold`
- Runner: `runners/run_esmfold.sh`
- Single-sequence model; no MSA databases required.
- Usually produces one deterministic `rank_001.pdb`.
- Keep ESMFold in a separate environment because its dependencies can conflict
  with OpenFold and other OpenFold-derived packages.
- Detailed notes: [ESMFold setup](../model-installation/esmfold.md)

### ColabFold

- Backend ID: `colabfold`
- Environment: `colabfold`
- Runner: `runners/run_colabfold.sh`
- Current runner uses `colabfold_batch --msa-mode single_sequence`.
- The current benchmark runner does not call the public MMseqs2 online MSA
  service and does not require a full local AF2/OpenFold database tree.
- Public online MSA services are not appropriate for heavy or bulk benchmarking.
- CUDA JAX support is installed via `jax[cuda12]==0.5.3`; sanity check with
  `jax.devices()`.
- Detailed notes: [ColabFold setup](../model-installation/colabfold.md)

### OmegaFold

- Backend ID: `omegafold`
- Environment: `omegafold`
- Runner: `runners/run_omegafold.sh`
- Produces one structure per sequence in the current wrapper.
- Critical pitfall: OmegaFold/PyTorch binaries compiled against NumPy 1.x may
  segfault with NumPy 2.x. Known bad combination observed locally:

```text
torch 1.12.0+cu113
numpy 2.0.2
```

Fix:

```bash
conda activate omegafold
pip install "numpy==1.26.4" --force-reinstall
```

`runners/run_omegafold.sh` now checks `numpy<2` before calling the native
`omegafold` executable, so the pipeline fails with a clear message instead of a
segmentation fault.

Detailed notes: [OmegaFold setup](../model-installation/omegafold.md)

### OpenFold

- Backend ID: `openfold`
- Environment: `openfold`
- Source checkout: `models/openfold` (ignored by Git)
- OpenFold was installed and compiled successfully.
- `attn_core_inplace_cuda` import works.
- `models/openfold/run_pretrained_openfold.py --help` works.
- Current scored outputs are from single-sequence smoke mode unless metadata
  explicitly proves a true MSA-mode run.
- Full MSA mode is blocked by missing large AF2/OpenFold-compatible databases.
- Detailed notes: [OpenFold setup](../model-installation/openfold.md)

Important installation lessons are preserved in `model-installation/openfold.md`,
including CUDA 12.1 PyTorch wheels, CUDA toolkit headers inside the environment,
conda GCC/G++ compilers, `TORCH_CUDA_ARCH_LIST=8.9`, `pip install .
--no-build-isolation`, runtime `LD_LIBRARY_PATH` fixes, `cuda-python==12.1.0`,
TensorRT, and Polygraphy.

Validation:

```bash
conda activate openfold
cd /path/to/Protein-Folding-Benchmark
export TORCH_LIB_DIR=$(python -c "import torch, os; print(os.path.join(os.path.dirname(torch.__file__), 'lib'))")
export LD_LIBRARY_PATH="$TORCH_LIB_DIR:$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
python -c "import attn_core_inplace_cuda; print('OpenFold CUDA extension OK')"
python models/openfold/run_pretrained_openfold.py --help
```

## Shared AF2/OpenFold Database Status

Full local MSA/template protocols require a database root outside the Git
repository, for example:

```bash
export AF2_OPENFOLD_DB_ROOT=/media/$USER/AFDB/alphafold_databases
# or
export AF2_OPENFOLD_DB_ROOT=$HOME/databases/alphafold
```

Expected database types include UniRef90, MGnify, BFD or small_BFD, UniRef30 or
Uniclust30, PDB70, PDB mmCIF templates, and an obsolete PDBs file.

Storage requirements are large:

- Reduced AF2/OpenFold setup: hundreds of GB, roughly 600 GB.
- Full AF2/OpenFold setup: roughly 2 TB or more.

Current local disk space is insufficient, so MSA-heavy protocols are paused.
See [shared AF2/OpenFold databases](../model-installation/shared_af2_databases.md).

## Failure Handling

The current pipeline records model failures without stopping the full benchmark
unless `--fail-fast` is used. It preserves per-model logs and writes failure
rows to `results/run_metadata.csv` with:

```text
target_id,pdb_id,chain_id,model,rank,output_pdb,success,return_code,
inference_time_sec,inference_time_sec_per_prediction,prediction_count,
trials_run,max_trials,successful_trial,command,error_message
```

Rules:

- Do not create fake prediction rows.
- Do not duplicate deterministic model outputs to satisfy `top_k`.
- Preserve logs for failed models.
- Represent missing or failed predictions in downstream analysis as missing
  data, not zero-quality structures.

Future TODO: add a dedicated `data/run_status.csv` if users need a compact run
status table separate from timing metadata. Suggested columns:

```text
target_id,pdb_id,chain,model,status,exit_code,runtime_sec,log_file,reason
```

## Notebook Documentation

Benchmark visualization notebook:

```text
notebooks/benchmark_analysis.ipynb
```

The notebook is intended to handle CSV-driven benchmark outputs, not only the
two original targets. It reads target metadata and score CSVs, uses lDDT-C-alpha
as the primary ranking metric, TM-score as the secondary metric, and includes
runtime plots when timing metadata are available.

Common invocation:

```bash
TARGETS_CSV=data/targets/targets.csv RESULTS_DIR=data/scores \
  jupyter notebook notebooks/benchmark_analysis.ipynb
```

For timing smoke outputs:

```bash
TARGETS_CSV=data/targets/targets_first5.csv RESULTS_DIR=results/timing_smoke/scores \
  jupyter notebook notebooks/benchmark_analysis.ipynb
```

Expected notebook views:

1. Per-target model comparisons.
2. Aggregate mean/median lDDT-C-alpha.
3. Aggregate mean/median TM-score.
4. Runtime distributions when available.
5. Missing/failed predictions represented as absent timing/score rows.

## Recommended Next Steps

Once external storage is available:

1. Download reduced AF2/OpenFold databases to an external drive.
2. Validate OpenFold true MSA mode on `1UAO_chignolin` and `1UBQ_ubiquitin`.
3. Decide whether to split OpenFold model IDs into `openfold_single_seq` and
   `openfold_msa`, or keep one backend ID with explicit metadata.
4. Add canonical AlphaFold2 using the same shared database root.
5. Optionally add OpenFold3 and official AF3 Docker-based backends later.

## Quick Maintainer Checklist

- Keep `models/` ignored.
- Keep one conda environment per folding backend.
- Use `configs/models.yaml` and enabled-model filtering for canonical scores.
- Use `--max-trials 1` for memory-sensitive debugging; retries can amplify
  native GPU pressure.
- Use `--gpu-cleanup-sleep-sec 10` for long mixed-backend GPU runs.
- Do not download large MSA/template databases into the repository.
