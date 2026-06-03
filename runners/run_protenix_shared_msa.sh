#!/usr/bin/env bash
set -euo pipefail

INPUT_FASTA="$1"
OUTPUT_DIR="$2"
TOP_K="${3:-1}"

if [[ "$TOP_K" != "1" ]]; then
  echo "Protenix experimental shared-MSA runner only supports top_k=1 for smoke tests." >&2
  exit 2
fi

if [[ -z "${SHARED_MSA_DIR:-}" || -z "${SHARED_MSA_A3M_FILE:-}" ]]; then
  echo "SHARED_MSA_DIR and SHARED_MSA_A3M_FILE must be set by the benchmark driver." >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"

CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
export NVCC_PREPEND_FLAGS="${NVCC_PREPEND_FLAGS:-}"
conda activate protenix

export CUDA_HOME="${CUDA_HOME:-${CONDA_PREFIX}}"
export PATH="${CONDA_PREFIX}/bin:${PATH}"
export CPATH="${CONDA_PREFIX}/targets/x86_64-linux/include:${CPATH:-}"
export LIBRARY_PATH="${CONDA_PREFIX}/targets/x86_64-linux/lib:${CONDA_PREFIX}/lib:${LIBRARY_PATH:-}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${CONDA_PREFIX}/targets/x86_64-linux/lib:${LD_LIBRARY_PATH:-}"
export PROTENIX_ROOT_DIR="${PROTENIX_ROOT_DIR:-${PWD}/weights/protenix}"
mkdir -p "$PROTENIX_ROOT_DIR"

REQUESTED_PROTENIX_MODEL_NAME="${PROTENIX_MODEL_NAME:-protenix-v2}"
ACTUAL_PROTENIX_MODEL_NAME="$REQUESTED_PROTENIX_MODEL_NAME"
if [[ "$REQUESTED_PROTENIX_MODEL_NAME" == "protenix-v2" && ! -f "${PROTENIX_ROOT_DIR}/checkpoint/protenix-v2.pt" ]]; then
  if [[ -f "${PROTENIX_ROOT_DIR}/checkpoint/protenix_base_default_v1.0.0.pt" ]]; then
    echo "Requested Protenix model $REQUESTED_PROTENIX_MODEL_NAME is not cached locally; falling back to protenix_base_default_v1.0.0." >&2
    ACTUAL_PROTENIX_MODEL_NAME="protenix_base_default_v1.0.0"
  fi
fi

RAW_OUTPUT="${OUTPUT_DIR}/raw_protenix"
PROTENIX_MSA_DIR="${OUTPUT_DIR}/protenix_msa/0"
INPUT_JSON="${OUTPUT_DIR}/query_protenix_shared_msa.json"
mkdir -p "$PROTENIX_MSA_DIR"
rm -rf "$RAW_OUTPUT"
mkdir -p "$RAW_OUTPUT"

python - "$INPUT_FASTA" "$SHARED_MSA_A3M_FILE" "$PROTENIX_MSA_DIR" "$INPUT_JSON" <<'PYJSON'
import json
import sys
from pathlib import Path

fasta = Path(sys.argv[1])
shared_a3m = Path(sys.argv[2])
msa_dir = Path(sys.argv[3])
query_json = Path(sys.argv[4])

header = ""
seq_parts = []
for line in fasta.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    if line.startswith(">"):
        header = line[1:].split()[0]
    else:
        seq_parts.append(line)
target_id = header or fasta.stem
sequence = "".join(seq_parts).upper()
if not sequence:
    raise SystemExit(f"No sequence found in {fasta}")

lines = shared_a3m.read_text().splitlines()
if not lines:
    raise SystemExit(f"Shared A3M is empty: {shared_a3m}")
for idx, line in enumerate(lines):
    if line.startswith(">"):
        lines[idx] = ">query"
        break
else:
    lines.insert(0, ">query")

non_pairing = msa_dir / "non_pairing.a3m"
pairing = msa_dir / "pairing.a3m"
non_pairing.write_text("\n".join(lines).rstrip() + "\n")
pairing.write_text(f">query\n{sequence}\n")

payload = [
    {
        "name": target_id,
        "sequences": [
            {
                "proteinChain": {
                    "sequence": sequence,
                    "count": 1,
                    "id": ["A"],
                    "modifications": [],
                    "pairedMsaPath": str(pairing.resolve()),
                    "unpairedMsaPath": str(non_pairing.resolve()),
                }
            }
        ],
        "covalent_bonds": [],
    }
]
query_json.write_text(json.dumps(payload, indent=2) + "\n")
print(target_id)
PYJSON

protenix pred \
  -i "$INPUT_JSON" \
  -o "$RAW_OUTPUT" \
  -s "${PROTENIX_SEEDS:-101}" \
  -c "${PROTENIX_CYCLE:-4}" \
  -p "${PROTENIX_STEP:-20}" \
  -e "${PROTENIX_SAMPLE:-1}" \
  -d "${PROTENIX_DTYPE:-bf16}" \
  -n "$ACTUAL_PROTENIX_MODEL_NAME" \
  --use_msa true \
  --use_template false \
  --use_default_params false \
  --trimul_kernel "${PROTENIX_TRIMUL_KERNEL:-torch}" \
  --triatt_kernel "${PROTENIX_TRIATT_KERNEL:-torch}" \
  --enable_fusion false

PREDICTED_CIF="$(find "$RAW_OUTPUT" -type f -name '*.cif' | sort | head -1)"
if [[ -z "$PREDICTED_CIF" ]]; then
  echo "Protenix finished but no .cif was found under $RAW_OUTPUT" >&2
  find "$RAW_OUTPUT" -maxdepth 5 -type f | sort >&2
  exit 1
fi

python - "$PREDICTED_CIF" "${OUTPUT_DIR}/rank_001.pdb" <<'PYPDB'
import sys
from pathlib import Path
from Bio.PDB import MMCIFParser, PDBIO

cif = Path(sys.argv[1])
pdb = Path(sys.argv[2])
parser = MMCIFParser(QUIET=True)
structure = parser.get_structure("protenix", str(cif))
io = PDBIO()
io.set_structure(structure)
io.save(str(pdb))
PYPDB

python - "$OUTPUT_DIR" "$INPUT_FASTA" "$PREDICTED_CIF" "$PROTENIX_ROOT_DIR" "$SHARED_MSA_A3M_FILE" "$SHARED_MSA_DIR" "${PROTENIX_MSA_DIR}/non_pairing.a3m" "${PROTENIX_MSA_DIR}/pairing.a3m" "$REQUESTED_PROTENIX_MODEL_NAME" "$ACTUAL_PROTENIX_MODEL_NAME" <<'PYMETA'
import json
import sys
from pathlib import Path

output_dir = Path(sys.argv[1])
metadata = {
    "model": "protenix",
    "model_name_requested": sys.argv[9],
    "model_name": sys.argv[10],
    "environment": "protenix",
    "input_fasta": sys.argv[2],
    "source_prediction": sys.argv[3],
    "protenix_root_dir": sys.argv[4],
    "top_k_requested": 1,
    "top_k_generated": 1,
    "top_k_policy": "experimental Protenix shared-MSA smoke; one seed and one sample",
    "msa_used": True,
    "msa_source": "colabfold_mmseqs2",
    "msa_mode": "shared_precomputed_msa",
    "msa_storage": "Shared cache A3M converted into runner-local Protenix paired/unpaired MSA files",
    "shared_msa_a3m_file": sys.argv[5],
    "shared_msa_dir": sys.argv[6],
    "local_msa_dir": str(output_dir / "protenix_msa" / "0"),
    "local_unpaired_msa_a3m_file": sys.argv[7],
    "local_paired_msa_a3m_file": sys.argv[8],
    "protenix_unpairedMsaPath": sys.argv[7],
    "protenix_pairedMsaPath": sys.argv[8],
    "use_templates": False,
}
(output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
PYMETA
