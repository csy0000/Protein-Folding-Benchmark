#!/usr/bin/env bash

# OpenFold runtime setup for this benchmark.
#
# Usage:
#   conda activate openfold
#   source envs/openfold_runtime.sh

if [ -z "${CONDA_PREFIX:-}" ]; then
  echo "ERROR: CONDA_PREFIX is not set. Activate the openfold conda environment first." >&2
  return 2 2>/dev/null || exit 2
fi

if [ "${CONDA_DEFAULT_ENV:-}" != "openfold" ]; then
  echo "WARNING: current conda environment is '${CONDA_DEFAULT_ENV:-unknown}', expected 'openfold'." >&2
fi

if ! python -c "import torch" >/dev/null 2>&1; then
  echo "ERROR: Python cannot import torch in this environment." >&2
  return 2 2>/dev/null || exit 2
fi

export OPENFOLD_REPO="${OPENFOLD_REPO:-$PWD/models/openfold}"

export CUDA_HOME="${CUDA_HOME:-$CONDA_PREFIX}"
export PATH="$CUDA_HOME/bin:$PATH"

export TORCH_LIB_DIR="${TORCH_LIB_DIR:-$(python -c "import torch, os; print(os.path.join(os.path.dirname(torch.__file__), 'lib'))")}"
export LD_LIBRARY_PATH="$TORCH_LIB_DIR:$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"

# RTX 2000 Ada / Lovelace architecture used by the current workstation.
# Users on other GPUs may need to adjust this.
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.9}"

# Keep runtime caches inside the project when running through Codex/sandboxes.
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-$PWD/.cache/triton}"
mkdir -p "$TRITON_CACHE_DIR"

echo "OpenFold runtime configured:"
echo "  OPENFOLD_REPO=$OPENFOLD_REPO"
echo "  CUDA_HOME=$CUDA_HOME"
echo "  TORCH_LIB_DIR=$TORCH_LIB_DIR"
echo "  TORCH_CUDA_ARCH_LIST=$TORCH_CUDA_ARCH_LIST"
