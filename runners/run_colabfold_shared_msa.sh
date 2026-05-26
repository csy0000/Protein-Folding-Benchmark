#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-1}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate colabfold

SHARED_A3M="${SHARED_MSA_A3M_FILE:-}"
SHARED_MSA_DIR="${SHARED_MSA_DIR:-}"
SHARED_MSA_METADATA_FILE="${SHARED_MSA_METADATA_FILE:-}"

if [ -z "$SHARED_A3M" ] || [ ! -s "$SHARED_A3M" ]; then
  echo "SHARED_MSA_A3M_FILE must point to an existing non-empty A3M file: ${SHARED_A3M:-<unset>}" >&2
  exit 1
fi

TMP_DIR="${OUTPUT_DIR}/tmp_colabfold_shared_msa"
INPUT_DIR="${OUTPUT_DIR}/tmp_colabfold_shared_input"
rm -rf "$TMP_DIR" "$INPUT_DIR"
mkdir -p "$TMP_DIR" "$INPUT_DIR"

TARGET_ID="$(awk '/^>/ { sub(/^>/, ""); print $1; exit }' "$INPUT_FASTA")"
if [ -z "$TARGET_ID" ]; then
  TARGET_ID="$(basename "$INPUT_FASTA")"
  TARGET_ID="${TARGET_ID%.*}"
fi

QUERY_A3M="${INPUT_DIR}/${TARGET_ID}.a3m"
cp "$SHARED_A3M" "$QUERY_A3M"

export MPLCONFIGDIR="${PWD}/.cache/matplotlib"
export XLA_PYTHON_CLIENT_PREALLOCATE=false
mkdir -p "$MPLCONFIGDIR"
mkdir -p "${PWD}/weights/colabfold"

echo "Running ColabFold prediction from shared precomputed A3M."
echo "TARGET_ID=$TARGET_ID"
echo "SHARED_MSA_A3M_FILE=$SHARED_A3M"
echo "SHARED_MSA_DIR=$SHARED_MSA_DIR"
echo "SHARED_MSA_METADATA_FILE=$SHARED_MSA_METADATA_FILE"

colabfold_batch \
  --num-models "$TOP_K" \
  --num-recycle 3 \
  --model-type alphafold2_ptm \
  --data "${PWD}/weights/colabfold" \
  --overwrite-existing-results \
  "$QUERY_A3M" \
  "$TMP_DIR" || {
    echo "ColabFold shared-MSA prediction failed. Temporary output tree:" >&2
    find "$TMP_DIR" -maxdepth 5 -type f | sort >&2
    exit 1
  }

python scripts/standardize_structure_outputs.py \
  --input-dir "$TMP_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --top-k "$TOP_K" \
  --model-name colabfold \
  --environment colabfold \
  --top-k-policy "ColabFold prediction from shared precomputed ColabFold/MMseqs A3M; no MMseqs search inside model runner"

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
        "msa_notes": "Shared ColabFold/MMseqs MSA generated once per target; MSA cost tracked separately",
    }
)
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
PY
