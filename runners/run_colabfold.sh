#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-5}"

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate colabfold

COLABFOLD_MSA_MODE="${COLABFOLD_MSA_MODE:-mmseqs2_uniref_env}"
COLABFOLD_DB="${COLABFOLD_DB:-/data/chen/protein_folding_databases/colabfold}"
COLABFOLD_MMSEQS="${COLABFOLD_MMSEQS:-/data/chen/software/mmseqs/bin/mmseqs}"
COLABFOLD_SEARCH_GPU="${COLABFOLD_SEARCH_GPU:-1}"
COLABFOLD_SEARCH_THREADS="${COLABFOLD_SEARCH_THREADS:-64}"
COLABFOLD_MODEL_NAME="${COLABFOLD_MODEL_NAME:-colabfold}"

TMP_DIR="${OUTPUT_DIR}/tmp_colabfold"
SEARCH_DIR="${OUTPUT_DIR}/tmp_colabfold_msa_search"
CARBON_DIR="${OUTPUT_DIR}/carbon"
MSA_CARBON_JSON="${OUTPUT_DIR}/msa_build_carbon.json"
INFERENCE_CARBON_JSON="${OUTPUT_DIR}/inference_carbon.json"
rm -rf "$TMP_DIR" "$SEARCH_DIR"
mkdir -p "$TMP_DIR"

export MPLCONFIGDIR="${PWD}/.cache/matplotlib"
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export PATH="$(dirname "$COLABFOLD_MMSEQS"):$PATH"
mkdir -p "$MPLCONFIGDIR"
mkdir -p "${PWD}/weights/colabfold"

COLABFOLD_INPUT="$INPUT_FASTA"
COLABFOLD_BATCH_MSA_ARGS=(--msa-mode "$COLABFOLD_MSA_MODE")
MSA_RUNTIME_SEC="0"
INFERENCE_RUNTIME_SEC=""

if [ "$COLABFOLD_MSA_MODE" != "single_sequence" ]; then
  if [ ! -d "$COLABFOLD_DB" ]; then
    echo "COLABFOLD_DB does not exist: $COLABFOLD_DB" >&2
    exit 1
  fi
  if [ ! -x "$COLABFOLD_MMSEQS" ]; then
    echo "COLABFOLD_MMSEQS is not executable: $COLABFOLD_MMSEQS" >&2
    exit 1
  fi
  echo "Running ColabFold local MSA search inside timed benchmark run."
  echo "COLABFOLD_MSA_MODE=$COLABFOLD_MSA_MODE"
  echo "COLABFOLD_DB=$COLABFOLD_DB"
  echo "COLABFOLD_MMSEQS=$COLABFOLD_MMSEQS"
  mkdir -p "$SEARCH_DIR"
  msa_start_epoch="$(date +%s)"
  python scripts/run_command_with_codecarbon.py \
    --metadata-json "$MSA_CARBON_JSON" \
    --carbon-dir "$CARBON_DIR" \
    --label "${COLABFOLD_MODEL_NAME}_msa_build" \
    -- \
    colabfold_search \
    --mmseqs "$COLABFOLD_MMSEQS" \
    --gpu "$COLABFOLD_SEARCH_GPU" \
    --threads "$COLABFOLD_SEARCH_THREADS" \
    "$INPUT_FASTA" \
    "$COLABFOLD_DB" \
    "$SEARCH_DIR"
  msa_end_epoch="$(date +%s)"
  MSA_RUNTIME_SEC="$((msa_end_epoch - msa_start_epoch))"
  COLABFOLD_INPUT="$SEARCH_DIR"
  COLABFOLD_BATCH_MSA_ARGS=()
fi

inference_start_epoch="$(date +%s)"
python scripts/run_command_with_codecarbon.py \
  --metadata-json "$INFERENCE_CARBON_JSON" \
  --carbon-dir "$CARBON_DIR" \
  --label "${COLABFOLD_MODEL_NAME}_inference" \
  -- \
  colabfold_batch \
  "${COLABFOLD_BATCH_MSA_ARGS[@]}" \
  --num-models "$TOP_K" \
  --num-recycle 3 \
  --model-type alphafold2_ptm \
  --data "${PWD}/weights/colabfold" \
  --overwrite-existing-results \
  "$COLABFOLD_INPUT" \
  "$TMP_DIR" || {
    echo "ColabFold failed. Temporary output tree:" >&2
    find "$TMP_DIR" -maxdepth 5 -type f | sort >&2
    exit 1
  }
inference_end_epoch="$(date +%s)"
INFERENCE_RUNTIME_SEC="$((inference_end_epoch - inference_start_epoch))"

python scripts/standardize_structure_outputs.py \
  --input-dir "$TMP_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --top-k "$TOP_K" \
  --model-name "$COLABFOLD_MODEL_NAME" \
  --environment colabfold \
  --top-k-policy "ColabFold ranked outputs; use genuine generated structures only; no artificial duplication"

python - "$OUTPUT_DIR" "$TMP_DIR" "$SEARCH_DIR" "$COLABFOLD_MSA_MODE" "$COLABFOLD_DB" "$MSA_RUNTIME_SEC" "$INFERENCE_RUNTIME_SEC" "$MSA_CARBON_JSON" "$INFERENCE_CARBON_JSON" <<'PY'
import json
import sys
from pathlib import Path

output_dir = Path(sys.argv[1])
tmp_dir = Path(sys.argv[2])
search_dir = Path(sys.argv[3])
msa_mode = sys.argv[4]
colabfold_db = sys.argv[5]
msa_runtime = sys.argv[6]
inference_runtime = sys.argv[7]
msa_carbon_path = Path(sys.argv[8])
inference_carbon_path = Path(sys.argv[9])
metadata_path = output_dir / "metadata.json"
metadata = json.loads(metadata_path.read_text())
a3m_candidates = sorted(tmp_dir.rglob("*.a3m"), key=lambda p: (-p.stat().st_size, str(p)))
search_a3m_candidates = sorted(search_dir.rglob("*.a3m"), key=lambda p: (-p.stat().st_size, str(p))) if search_dir.exists() else []
a3m_file = search_a3m_candidates[0] if search_a3m_candidates else (a3m_candidates[0] if a3m_candidates else None)
msa_used = msa_mode != "single_sequence"
msa_note = (
    "ColabFold local MMseqs2 MSA search measured separately from colabfold_batch inference."
    if msa_used else
    "ColabFold single_sequence mode; generated A3M contains only the query sequence."
)

def load_carbon(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"carbon_error": repr(exc)}

def num(value):
    try:
        text = str(value).strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None

def add_values(*values):
    nums = [num(value) for value in values]
    nums = [value for value in nums if value is not None]
    return str(sum(nums)) if nums else ""

def carbon_value(carbon, key):
    value = carbon.get(key, "")
    return "" if value is None else str(value)

msa_carbon = load_carbon(msa_carbon_path) if msa_used else {}
inference_carbon = load_carbon(inference_carbon_path)
msa_carbon_g = carbon_value(msa_carbon, "carbon_emissions_g") if msa_used else ""
msa_energy = carbon_value(msa_carbon, "carbon_energy_consumed_kwh") if msa_used else ""
inference_carbon_g = carbon_value(inference_carbon, "carbon_emissions_g")
inference_energy = carbon_value(inference_carbon, "carbon_energy_consumed_kwh")
metadata.update(
    {
        "msa_used": msa_used,
        "msa_source": "colabfold_mmseqs2" if msa_used else "none",
        "msa_mode": msa_mode,
        "msa_database": "colabfold" if msa_used else "none",
        "msa_database_path": colabfold_db if msa_used else "",
        "msa_a3m_file": str(a3m_file) if a3m_file else "",
        "msa_build_runtime_sec": msa_runtime if msa_used else "0",
        "msa_build_carbon_emissions_g": msa_carbon_g,
        "msa_build_energy_consumed_kwh": msa_energy,
        "msa_build_included_in_runtime": str(msa_used).lower(),
        "msa_build_included_in_carbon": str(bool(msa_carbon_g)).lower(),
        "msa_reused": "false",
        "inference_runtime_sec": inference_runtime,
        "inference_carbon_emissions_g": inference_carbon_g,
        "inference_energy_consumed_kwh": inference_energy,
        "total_runtime_sec": str(float(msa_runtime or 0) + float(inference_runtime or 0)),
        "total_carbon_emissions_g": add_values(msa_carbon_g, inference_carbon_g),
        "total_energy_consumed_kwh": add_values(msa_energy, inference_energy),
        "stage_metadata_note": msa_note,
    }
)
metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
PY
