#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-1}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"

SHARED_A3M="${SHARED_MSA_A3M_FILE:-}"
SHARED_MSA_DIR="${SHARED_MSA_DIR:-}"
SHARED_MSA_METADATA_FILE="${SHARED_MSA_METADATA_FILE:-}"

if [ -z "$SHARED_A3M" ] || [ ! -s "$SHARED_A3M" ]; then
  echo "SHARED_MSA_A3M_FILE must point to an existing non-empty A3M file: ${SHARED_A3M:-<unset>}" >&2
  exit 1
fi

TARGET_ID="$(awk '/^>/ { sub(/^>/, ""); print $1; exit }' "$INPUT_FASTA")"
if [ -z "$TARGET_ID" ]; then
  TARGET_ID="$(basename "$INPUT_FASTA")"
  TARGET_ID="${TARGET_ID%.*}"
fi

WORK_DIR="${OUTPUT_DIR}/tmp_openfold_shared_msa"
ALIGNMENT_ROOT="${WORK_DIR}/precomputed_alignments"
TARGET_ALIGNMENT_DIR="${ALIGNMENT_ROOT}/${TARGET_ID}"

rm -rf "$WORK_DIR"
mkdir -p "$TARGET_ALIGNMENT_DIR"
cp "$SHARED_A3M" "${TARGET_ALIGNMENT_DIR}/colabfold.a3m"

echo "Running OpenFold prediction from shared precomputed A3M."
echo "TARGET_ID=$TARGET_ID"
echo "SHARED_MSA_A3M_FILE=$SHARED_A3M"
echo "SHARED_MSA_DIR=$SHARED_MSA_DIR"
echo "SHARED_MSA_METADATA_FILE=$SHARED_MSA_METADATA_FILE"
echo "OPENFOLD_PRECOMPUTED_ALIGNMENTS=$ALIGNMENT_ROOT"

conda activate openfold

TORCH_LIB_DIR="$(python -c "import torch, os; print(os.path.join(os.path.dirname(torch.__file__), 'lib'))")"
export CUDA_HOME="${CUDA_HOME:-$CONDA_PREFIX}"
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$TORCH_LIB_DIR:$CONDA_PREFIX/lib:${LD_LIBRARY_PATH:-}"
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-8.9}"
export TRITON_CACHE_DIR="${TRITON_CACHE_DIR:-${PWD}/.cache/triton}"
mkdir -p "$TRITON_CACHE_DIR"

OPENFOLD_PARAMS_DIR="${OPENFOLD_PARAMS_DIR:-${PWD}/weights/colabfold/params}"
OPENFOLD_PARAM_PATH="${OPENFOLD_PARAM_PATH:-${OPENFOLD_PARAMS_DIR}/params_model_1.npz}"
OPENFOLD_DATA_DIR="${OPENFOLD_DATA_DIR:-${PWD}/work/openfold_inputs}"
OPENFOLD_TEMPLATE_MMCIF_DIR="${OPENFOLD_TEMPLATE_MMCIF_DIR:-${PWD}/models/openfold/tests/test_data/mmcifs}"

python scripts/run_openfold.py \
  --fasta-path "$INPUT_FASTA" \
  --output-dir "$OUTPUT_DIR" \
  --num-models "$TOP_K" \
  --openfold-repo "${OPENFOLD_REPO:-models/openfold}" \
  --params-dir "$OPENFOLD_PARAMS_DIR" \
  --param-path "$OPENFOLD_PARAM_PATH" \
  --data-dir "$OPENFOLD_DATA_DIR" \
  --template-mmcif-dir "$OPENFOLD_TEMPLATE_MMCIF_DIR" \
  --config-preset "${OPENFOLD_CONFIG_PRESET:-model_1}" \
  --device "${OPENFOLD_DEVICE:-cuda:0}" \
  --mode single_sequence \
  --use-precomputed-alignments "$ALIGNMENT_ROOT" \
  --skip-relaxation

python - "$OUTPUT_DIR" "$SHARED_A3M" "$SHARED_MSA_DIR" "$SHARED_MSA_METADATA_FILE" <<'PY'
import json
import sys
from pathlib import Path

output_dir = Path(sys.argv[1])
metadata_path = output_dir / "metadata.json"
metadata = json.loads(metadata_path.read_text())
metadata.update(
    {
        "msa_used": True,
        "msa_source": "colabfold_mmseqs2",
        "msa_mode": "shared_precomputed_msa",
        "msa_generation_included_in_timing": False,
        "msa_generation_included_in_carbon": False,
        "msa_reused": True,
        "shared_msa_a3m_file": sys.argv[2],
        "shared_msa_dir": sys.argv[3],
        "shared_msa_metadata_file": sys.argv[4],
        "local_msa_a3m_file": str(output_dir / "tmp_openfold_shared_msa" / "precomputed_alignments"),
        "msa_notes": "Shared ColabFold/MMseqs MSA generated once per target; MSA cost tracked separately",
    }
)
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
PY
