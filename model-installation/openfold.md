# OpenFold Installation and Benchmark Notes

Backend ID: `openfold`
Environment: `openfold`
Source checkout: `models/openfold`
Status: enabled and validated on 2026-05-19 for 7ROA single-sequence smoke and combined six-backend smoke. Full MSA mode still requires real OpenFold/AlphaFold-compatible databases and was not freshly validated.

`models/` is ignored by Git, so keep durable benchmark instructions in this
tracked file rather than only in `models/openfold/README.md`.

## Current Validated Setup (2026-05-19)

This machine uses the existing ESMFold-compatible OpenFold checkout at commit `4b41059694619831a7db195b7e0988fc4ff3a307`. The environment was created from `models/openfold/environment.yml` as a separate `openfold` conda environment.

```bash
mamba env create -n openfold -f models/openfold/environment.yml
mamba install -n openfold -c conda-forge "mkl<2024" --yes
conda run -n openfold python -m pip install gemmi
```

The MKL pin fixes this old PyTorch import failure:

```text
ImportError: .../libtorch_cpu.so: undefined symbol: iJIT_NotifyEvent
```

The runner uses the source checkout directly through `scripts/run_openfold.py`; it does not require building the CUDA extension for the current single-sequence smoke path. The wrapper is compatible with both newer OpenFold checkouts that accept `--use_single_seq_mode` and this older checkout that relies on an empty precomputed alignment directory to create a dummy one-sequence MSA.

Validation commands:

```bash
conda run -n openfold python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.device_count())"
conda run -n openfold python -c "import sys; sys.path.insert(0, 'models/openfold'); import openfold; print('openfold import OK')"
conda run -n openfold python models/openfold/run_pretrained_openfold.py --help
```

Fresh smoke outputs:

- `results/backend_smoke/openfold_single_sequence/`
- `results/backend_smoke/six_backend_single_sequence/`

## Historical/Alternative Patched Environment

The upstream `models/openfold/environment.yml` may use a different name, such
as `openfold-env`. This benchmark uses:

```text
openfold
```

A local patched environment file was created under ignored source checkout
space, for example:

```text
models/openfold/environment_openfold_local.yml
```

Documented edits:

- set `name: openfold`
- remove or relax conda PyTorch/CUDA constraints if solving fails
- remove `flash-attn` from the initial pip section because it needs `torch`
  during build
- install PyTorch manually afterward

Create the environment with flexible channel priority:

```bash
mamba env create \
  --channel-priority flexible \
  -f models/openfold/environment_openfold_local.yml
```

## PyTorch, CUDA, and Compilers

Validated local stack:

```text
Python: 3.10
PyTorch: 2.5.1+cu121
CUDA available: True
torch.version.cuda: 12.1
GPU architecture: TORCH_CUDA_ARCH_LIST=8.9 for RTX 2000 Ada / Lovelace
```

Install PyTorch:

```bash
conda activate openfold
pip install torch==2.5.1 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Install compilers and CUDA toolkit:

```bash
mamba install -c conda-forge gxx_linux-64=12.4 gcc_linux-64=12.4 -y
mamba install -c nvidia cuda-toolkit=12.1 -y
```

Build variables:

```bash
export CUDA_HOME="$CONDA_PREFIX"
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$CUDA_HOME/lib:$LD_LIBRARY_PATH"

export CC="$(which x86_64-conda-linux-gnu-gcc)"
export CXX="$(which x86_64-conda-linux-gnu-g++)"
export CUDAHOSTCXX="$CXX"
export TORCH_CUDA_ARCH_LIST="8.9"
```

The correct `nvcc` should be:

```text
$CONDA_PREFIX/bin/nvcc
```

not `/usr/bin/nvcc`.

## Build OpenFold

Editable mode failed because the build backend did not support the editable
PEP 660 hook. The successful command was non-editable and disabled build
isolation so the build could see already-installed `torch`:

```bash
cd models/openfold
rm -rf build openfold.egg-info
pip install . --no-build-isolation -v 2>&1 | tee /tmp/openfold_build.log
```

Expected success text:

```text
Successfully built openfold
Successfully installed openfold-2.2.0
```

## Runtime Packages

Additional packages used locally:

```bash
pip install pytorch-lightning
pip install "cuda-python==12.1.0"
pip install --extra-index-url https://pypi.nvidia.com tensorrt-cu12
pip install --extra-index-url https://pypi.nvidia.com polygraphy
```

`cuda-python` 13.x did not provide the expected `cuda.cudart` namespace for
this OpenFold version. `cuda-python==12.1.0` worked.

## Runtime Setup

After activating the env, source:

```bash
conda activate openfold
source envs/openfold_runtime.sh
```

The important linker fix is:

```bash
export TORCH_LIB_DIR=$(python -c "import torch, os; print(os.path.join(os.path.dirname(torch.__file__), 'lib'))")
export LD_LIBRARY_PATH="$TORCH_LIB_DIR:$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"
```

This fixed:

```text
ImportError: libc10.so: cannot open shared object file
```

## Successful Validation Tests

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)"
python -c "import attn_core_inplace_cuda; print('OpenFold CUDA extension OK')"
python -c "import cuda.cudart as cudart; print('cuda.cudart OK')"
python -c "import tensorrt as trt; print('TensorRT OK', trt.__version__)"
python -c "import polygraphy; print('polygraphy OK')"
python models/openfold/run_pretrained_openfold.py --help
```

Non-fatal warnings observed:

- DeepSpeed `async_io requires libaio`
- FutureWarnings about `torch.cuda.amp.custom_fwd/custom_bwd`

## Benchmark Runner

The runner uses the benchmark interface:

```bash
bash runners/run_openfold.sh input.fasta output_dir top_k
```

It writes:

```text
data/predictions/<target_id>/openfold/rank_001.pdb
data/predictions/<target_id>/openfold/metadata.json
```

## MSA Mode

The runner now defaults to:

```bash
OPENFOLD_MODE=msa
```

MSA mode requires real OpenFold/AlphaFold-compatible database paths under
`OPENFOLD_DATA_DIR`, including at least UniRef90, MGnify, PDB70, and for the
default `full_dbs` preset, BFD and UniRef30. It also requires a nonempty
template mmCIF directory.

Required/typical paths:

```bash
export OPENFOLD_REPO=/path/to/openfold
export OPENFOLD_PARAMS_DIR=/path/to/openfold_or_alphafold_params
export OPENFOLD_PARAM_PATH=/path/to/params_model_1.npz
export OPENFOLD_DATA_DIR=/path/to/openfold_databases
export OPENFOLD_TEMPLATE_MMCIF_DIR=/path/to/pdb_mmcif/mmcif_files
```

The current machine does not have the full MSA database tree configured, so a
fresh MSA prediction fails early with clear missing-path diagnostics. Existing
OpenFold score rows come from the prior single-sequence smoke run.

## Existing Smoke Outputs

| Target | rank_001.pdb | Scored | Mode |
|---|---:|---:|---|
| `1UAO_chignolin` | yes | yes | single-sequence smoke |
| `1UBQ_ubiquitin` | yes | yes | single-sequence smoke |

Observed summary metrics from the current score CSVs:

| Target | best_lddt_ca | best_tmalign_tm_score_ref |
|---|---:|---:|
| `1UAO_chignolin` | 0.87778 | 0.48520 |
| `1UBQ_ubiquitin` | 0.95445 | 0.96435 |

Do not overinterpret quality from these two smoke targets.


## Validated ColabFold/MMseqs MSA Mode (2026-05-20)

`runners/run_openfold_msa.sh` implements the benchmark `openfold_msa` variant. It keeps the standard runner interface, removes the run-local `tmp_openfold_colabfold_msa` directory, runs:

```bash
conda run -n colabfold colabfold_search --mmseqs /data/chen/software/mmseqs/bin/mmseqs --gpu 1 --threads 64 input.fasta /data/chen/protein_folding_databases/colabfold <output>/tmp_openfold_colabfold_msa/colabfold_search
```

Then it copies the generated A3M to `<output>/tmp_openfold_colabfold_msa/precomputed_alignments/<target_id>/colabfold.a3m` and runs `scripts/run_openfold.py` with `--use-precomputed-alignments` pointing at that freshly created alignment root. Because both steps happen inside one runner subprocess, `run_benchmark_from_targets.py` timing and CodeCarbon include MSA search plus OpenFold inference.

The first-five smoke comparison passed on 2026-05-20 under `results/openfold_single_vs_msa_first5_carbon/`.
