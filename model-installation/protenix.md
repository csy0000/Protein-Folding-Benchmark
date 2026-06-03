# Protenix Setup Notes

Backend ID: `protenix`
Environment: `protenix`
Source checkout: `models/protenix`
Status: installed experimentally / disabled by default.

Protenix was installed on 2026-05-22 as an experimental shared-MSA backend. It is not part of the canonical benchmark model set and is not enabled in `configs/models.yaml`.

## Installed Components

- Conda environment: `protenix`
- Python: 3.11
- Package: PyPI `protenix==2.0.0`
- CUDA toolkit: `cuda-toolkit=12.6` installed inside the `protenix` env
- Source checkout: `models/protenix`
- Runtime cache/checkpoint root: `weights/protenix`
- Default benchmark model selector: `protenix-v2` (falls back to `protenix_base_default_v1.0.0` when no local `protenix-v2.pt` is cached)
- Existing local checkpoint cache: `weights/protenix/checkpoint/protenix_base_default_v1.0.0.pt`
- Additional Protenix checkpoints may be downloaded lazily by the CLI when `protenix-v2` is first requested

The environment needs CUDA variables exported before CLI use:

```bash
CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
export NVCC_PREPEND_FLAGS="${NVCC_PREPEND_FLAGS:-}"
conda activate protenix
export CUDA_HOME="${CONDA_PREFIX}"
export PATH="${CONDA_PREFIX}/bin:${PATH}"
export CPATH="${CONDA_PREFIX}/targets/x86_64-linux/include:${CPATH:-}"
export LIBRARY_PATH="${CONDA_PREFIX}/targets/x86_64-linux/lib:${CONDA_PREFIX}/lib:${LIBRARY_PATH:-}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${CONDA_PREFIX}/targets/x86_64-linux/lib:${LD_LIBRARY_PATH:-}"
export PROTENIX_ROOT_DIR="${PWD}/weights/protenix"
```

## Runner

The experimental benchmark runner is:

```text
runners/run_protenix_shared_msa.sh
```

It preserves the standard runner interface:

```bash
bash runners/run_protenix_shared_msa.sh input.fasta output_dir top_k
```

The runner currently supports `top_k=1`. It expects `SHARED_MSA_DIR` and `SHARED_MSA_A3M_FILE` from the benchmark driver, converts the shared ColabFold A3M into Protenix-compatible `non_pairing.a3m` and query-only `pairing.a3m`, runs `protenix pred` with one sample, defaulting to `PROTENIX_MODEL_NAME=protenix-v2`, converts the first CIF prediction to `rank_001.pdb`, and writes `metadata.json`.

## 2026-05-22 Shared-MSA Results

One-target smoke:

- Output root: `results/backend_smoke/protenix_shared_msa/`
- Prediction: `results/backend_smoke/protenix_shared_msa/predictions/7ROA_chainA/protenix/rank_001.pdb`
- Combined score/cost table: `results/backend_smoke/protenix_shared_msa/shared_msa_score_cost_summary.csv`

First-five smoke:

- Output root: `results/protenix_openfold3_shared_msa_first5/`
- Status: 5/5 targets succeeded
- Mean lDDT-C-alpha: `0.8665522357206289`
- Mean TM-score normalized by reference: `0.855224`
- Combined score/cost table: `results/protenix_openfold3_shared_msa_first5/shared_msa_score_cost_summary.csv`

## Resolved Install Issues

- `CUDA_HOME environment variable is not set`: resolved by installing `cuda-toolkit=12.6` in the Protenix environment and exporting `CUDA_HOME=${CONDA_PREFIX}`.
- `NVCC_PREPEND_FLAGS: unbound variable`: resolved by seeding `NVCC_PREPEND_FLAGS` before `conda activate protenix` in the runner.

## Notes

Protenix downloads cache files and model checkpoints on first use. Keep this backend experimental until licensing, checkpoint provenance, and broader validation are reviewed for the intended benchmark release.
