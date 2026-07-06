#!/usr/bin/env bash
set -euo pipefail

MANIFEST="data/casp15_casp16_target_manifest_prefiltered.csv"
OUT_ROOT="results/casp15_casp16_manifest_all_status_rank1_$(date +%Y%m%d)"
INCLUDE_STATUS="All"
MODELS="boltz,boltz2,chai1,colabfold,esmfold,omegafold,openfold" # af2,af3,
MAX_TARGETS=""
MAX_LENGTH=""
RESUME=0
DRY_RUN=0
PREDICTION_COUNT=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    --include-status) INCLUDE_STATUS="$2"; shift 2 ;;
    --models) MODELS="$2"; shift 2 ;;
    --max-targets) MAX_TARGETS="$2"; shift 2 ;;
    --max-length) MAX_LENGTH="$2"; shift 2 ;;
    --resume) RESUME=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      echo "Usage: bash scripts/run_manifest_predictions.sh [--manifest CSV] [--out-root DIR] [--include-status All|Yes,Check|Yes|Check|No] [--models csv] [--max-targets N] [--max-length N] [--resume] [--dry-run]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "${OUT_ROOT}/metadata" "${OUT_ROOT}/logs" "${OUT_ROOT}/predictions"

prepare_args=(
  python scripts/prepare_manifest_fastas.py
  --manifest "$MANIFEST"
  --out-root "$OUT_ROOT"
  --include-status "$INCLUDE_STATUS"
)
if [[ -n "$MAX_LENGTH" ]]; then
  prepare_args+=(--max-length "$MAX_LENGTH")
fi
if [[ -n "$MAX_TARGETS" ]]; then
  prepare_args+=(--max-targets "$MAX_TARGETS")
fi
"${prepare_args[@]}"

METADATA="${OUT_ROOT}/metadata/prediction_manifest.csv"
TMP_METADATA="${METADATA}.tmp"


shared_msa_a3m_for_target() {
  local domain_id="$1"
  local colabfold_dir="${OUT_ROOT}/predictions/${domain_id}/colabfold"
  if [[ ! -d "$colabfold_dir" ]]; then
    return 0
  fi
  find "$colabfold_dir" -type f -name '*.a3m' -printf '%s %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true
}

runner_for_model() {
  case "$1" in
    af2) echo "runners/run_af2.sh" ;;
    af3) echo "runners/run_alphafold3.sh" ;;
    boltz) echo "runners/run_boltz.sh" ;;
    boltz2) echo "runners/run_boltz2.sh" ;;
    chai1) echo "runners/run_chai1.sh" ;;
    chai1_msa) echo "runners/run_chai1_shared_msa.sh" ;;
    colabfold) echo "runners/run_colabfold.sh" ;;
    colabfold_nomsa) echo "runners/run_colabfold.sh" ;;
    esmfold) echo "runners/run_esmfold.sh" ;;
    omegafold) echo "runners/run_omegafold.sh" ;;
    openfold) echo "runners/run_openfold_shared_msa.sh" ;;
    openfold_nomsa) echo "runners/run_openfold.sh" ;;
    boltz2_nomsa) echo "runners/run_boltz2.sh" ;;
    protenix) echo "runners/run_protenix_shared_msa.sh" ;;
    *) echo "" ;;
  esac
}

python - "$OUT_ROOT/manifest_used.csv" "$METADATA" "$MODELS" "$OUT_ROOT" "$PREDICTION_COUNT" "$RESUME" "$DRY_RUN" "$MAX_LENGTH" <<'PY'
import csv
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
metadata_path = Path(sys.argv[2])
models = [m.strip() for m in sys.argv[3].split(",") if m.strip()]
out_root = Path(sys.argv[4])
rank = sys.argv[5]
resume = sys.argv[6] == "1"
dry_run = sys.argv[7] == "1"
max_length = int(sys.argv[8]) if len(sys.argv) > 8 and sys.argv[8] else None

columns = [
    "domain_id","target_id","casp_round","pdb_id","chain_id","residue_start","residue_end",
    "sequence_start","sequence_end","target_length","sequence_length","model","rank",
    "input_fasta","output_dir","output_pdb","output_structure","success","return_code",
    "start_time","end_time","runtime_sec","log_file","command","error_message","should_use",
    "target_qc_status","qc_reason","mapping_identity","mapping_coverage","reference_coverage",
    "resolved_ca_count","expected_mapped_residue_count","chain_assignment_confidence",
    "residue_mapping_note","type","stoichiometry","description",
    "msa_used","msa_source","msa_mode","msa_database","msa_database_path","msa_a3m_file",
    "msa_build_runtime_sec","msa_build_carbon_emissions_g","msa_build_energy_consumed_kwh",
    "msa_build_included_in_runtime","msa_build_included_in_carbon","msa_reused",
    "inference_runtime_sec","inference_carbon_emissions_g","inference_energy_consumed_kwh",
    "total_runtime_sec","total_carbon_emissions_g","total_energy_consumed_kwh",
    "shared_msa_source_model","shared_msa_a3m_file","shared_msa_dir","stage_metadata_note",
]

with manifest_path.open(newline="") as f:
    manifest_rows = list(csv.DictReader(f))
if max_length is not None:
    manifest_rows = [
        row for row in manifest_rows
        if int(row.get("target_length") or row.get("sequence_length") or 0) <= max_length
    ]

existing_success = set()
existing_rows = {}
if resume and metadata_path.exists():
    with metadata_path.open(newline="") as f:
        for row in csv.DictReader(f):
            key = (row.get("domain_id", ""), row.get("model", ""))
            existing_rows[key] = row
            if row.get("success", "").lower() == "true":
                existing_success.add(key)

rows = []
for target in manifest_rows:
    domain_id = target.get("domain_id", "")
    fasta = target.get("fasta_path", str(out_root / "sequences" / f"{domain_id}.fasta"))
    for model in models:
        output_dir = out_root / "predictions" / domain_id / model
        output_pdb = output_dir / "rank_001.pdb"
        log_file = out_root / "logs" / f"{domain_id}_{model}.log"
        skipped_success = (domain_id, model) in existing_success or output_pdb.exists()
        key = (domain_id, model)
        if resume and key in existing_success and key in existing_rows:
            row = {column: existing_rows[key].get(column, "") for column in columns}
        else:
            row = {
                "domain_id": domain_id,
                "target_id": target.get("target_id", ""),
                "casp_round": target.get("casp_round", ""),
                "pdb_id": target.get("pdb_id", ""),
                "chain_id": target.get("chain_id", ""),
                "residue_start": target.get("residue_start", ""),
                "residue_end": target.get("residue_end", ""),
                "sequence_start": target.get("sequence_start", ""),
                "sequence_end": target.get("sequence_end", ""),
                "target_length": target.get("target_length", ""),
                "sequence_length": target.get("sequence_length", ""),
                "model": model,
                "rank": rank,
                "input_fasta": fasta,
                "output_dir": str(output_dir),
                "output_pdb": str(output_pdb),
                "output_structure": str(output_pdb),
                "success": "true" if skipped_success else ("" if dry_run else "pending"),
                "return_code": "0" if skipped_success else "",
                "start_time": "",
                "end_time": "",
                "runtime_sec": "",
                "log_file": str(log_file),
                "command": "",
                "error_message": "skipped existing success" if skipped_success else "",
                "should_use": target.get("should_use", ""),
                "target_qc_status": target.get("should_use", ""),
                "qc_reason": target.get("reason", ""),
                "mapping_identity": target.get("mapping_identity", ""),
                "mapping_coverage": target.get("mapping_coverage", ""),
                "reference_coverage": target.get("reference_coverage", ""),
                "resolved_ca_count": target.get("resolved_ca_count", ""),
                "expected_mapped_residue_count": target.get("expected_mapped_residue_count", ""),
                "chain_assignment_confidence": target.get("chain_assignment_confidence", ""),
                "residue_mapping_note": target.get("residue_mapping_note", ""),
                "type": target.get("type", ""),
                "stoichiometry": target.get("stoichiometry", ""),
                "description": target.get("description", ""),
            }
        rows.append(row)

metadata_path.parent.mkdir(parents=True, exist_ok=True)
with metadata_path.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
print(f"Initialized metadata rows: {len(rows)}")
PY

IFS=',' read -r -a MODEL_LIST <<< "$MODELS"

while IFS=, read -r domain_id fasta_path should_use; do
  [[ "$domain_id" == "domain_id" ]] && continue
  for model in "${MODEL_LIST[@]}"; do
    runner="$(runner_for_model "$model")"
    output_dir="${OUT_ROOT}/predictions/${domain_id}/${model}"
    log_file="${OUT_ROOT}/logs/${domain_id}_${model}.log"
    runner_carbon_json="${output_dir}/runner_carbon.json"
    command="bash ${runner} ${fasta_path} ${output_dir} ${PREDICTION_COUNT}"
    shared_msa_a3m=""
    shared_msa_dir=""
    if [[ "$model" == "openfold" || "$model" == "boltz2" || "$model" == "protenix" || "$model" == "chai1_msa" ]]; then
      shared_msa_a3m="$(shared_msa_a3m_for_target "$domain_id")"
      if [[ -n "$shared_msa_a3m" ]]; then
        shared_msa_dir="$(dirname "$shared_msa_a3m")"
        command="SHARED_MSA_A3M_FILE=${shared_msa_a3m} SHARED_MSA_DIR=${shared_msa_dir} SHARED_MSA_METADATA_FILE=${METADATA} ${command}"
      else
        command="SHARED_MSA_A3M_FILE=<missing> ${command}"
      fi
    fi
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "[dry-run] ${command}"
      continue
    fi
    if [[ -z "$runner" || ! -f "$runner" ]]; then
      echo "Missing runner for model ${model}: ${runner}" | tee "$log_file" >&2
      python - "$METADATA" "$domain_id" "$model" "false" "127" "missing runner: ${runner}" "" "" "$command" <<'PY'
import csv, sys
path, domain, model, success, rc, err, start, end, command = sys.argv[1:]
rows=list(csv.DictReader(open(path)))
fields=list(rows[0].keys()) if rows else []
for r in rows:
    if r["domain_id"] == domain and r["model"] == model:
        r.update({"success": success, "return_code": rc, "error_message": err, "command": command})
with open(path, "w", newline="") as f:
    w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
PY
      continue
    fi
    if [[ "$RESUME" -eq 1 && -s "${output_dir}/rank_001.pdb" ]]; then
      echo "[resume] ${domain_id}/${model} already has rank_001.pdb"
      python scripts/update_manifest_prediction_metadata.py \
        --metadata "$METADATA" \
        --domain-id "$domain_id" \
        --model "$model" \
        --success true \
        --return-code 0 \
        --error-message "skipped existing success" \
        --runtime-sec "" \
        --command "$command" \
        --runner-metadata "${output_dir}/metadata.json" \
        --run-carbon-metadata "$runner_carbon_json"
      continue
    fi
    mkdir -p "$output_dir"
    rm -f "$runner_carbon_json"
    start_time="$(date -Iseconds)"
    start_epoch="$(date +%s)"
    set +e
    if [[ "$model" == "openfold" || "$model" == "boltz2" || "$model" == "protenix" || "$model" == "chai1_msa" ]]; then
      if [[ -z "$shared_msa_a3m" || ! -s "$shared_msa_a3m" ]]; then
        {
          echo "${model} shared-MSA mode requires a ColabFold A3M for ${domain_id}."
          echo "Expected an existing .a3m under ${OUT_ROOT}/predictions/${domain_id}/colabfold."
          echo "Run colabfold for this target before ${model}, or remove ${model} from --models."
        } >"$log_file"
        rc=1
      else
        SHARED_MSA_A3M_FILE="$shared_msa_a3m" \
          SHARED_MSA_DIR="$shared_msa_dir" \
          SHARED_MSA_METADATA_FILE="$METADATA" \
          python scripts/run_command_with_codecarbon.py \
            --metadata-json "$runner_carbon_json" \
            --carbon-dir "${output_dir}/carbon" \
            --label "${domain_id}_${model}_inference" \
            -- \
            bash "$runner" "$fasta_path" "$output_dir" "$PREDICTION_COUNT" >"$log_file" 2>&1
        rc=$?
      fi
    elif [[ "$model" == "colabfold" || "$model" == "colabfold_nomsa" || "$model" == "af2" ]]; then
      bash "$runner" "$fasta_path" "$output_dir" "$PREDICTION_COUNT" >"$log_file" 2>&1
      rc=$?
    else
      python scripts/run_command_with_codecarbon.py \
        --metadata-json "$runner_carbon_json" \
        --carbon-dir "${output_dir}/carbon" \
        --label "${domain_id}_${model}_inference" \
        -- \
        bash "$runner" "$fasta_path" "$output_dir" "$PREDICTION_COUNT" >"$log_file" 2>&1
      rc=$?
    fi
    set -e
    end_time="$(date -Iseconds)"
    end_epoch="$(date +%s)"
    runtime=$((end_epoch - start_epoch))
    success=false
    error=""
    if [[ "$rc" -eq 0 && -s "${output_dir}/rank_001.pdb" ]]; then
      success=true
    else
      error="runner failed or rank_001.pdb missing; see ${log_file}"
    fi
    python scripts/update_manifest_prediction_metadata.py \
      --metadata "$METADATA" \
      --domain-id "$domain_id" \
      --model "$model" \
      --success "$success" \
      --return-code "$rc" \
      --error-message "$error" \
      --start-time "$start_time" \
      --end-time "$end_time" \
      --runtime-sec "$runtime" \
      --command "$command" \
      --runner-metadata "${output_dir}/metadata.json" \
      --run-carbon-metadata "$runner_carbon_json"
  done
done < <(python - "$OUT_ROOT/manifest_used.csv" "$MAX_LENGTH" <<'PY'
import csv, sys
max_length = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
for row in csv.DictReader(open(sys.argv[1])):
    if max_length is not None and int(row.get("target_length") or row.get("sequence_length") or 0) > max_length:
        continue
    print(",".join([row["domain_id"], row["fasta_path"], row.get("should_use", "")]))
PY
)

python scripts/list_manifest_prediction_status.py --out-root "$OUT_ROOT"
