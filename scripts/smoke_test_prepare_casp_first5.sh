#!/usr/bin/env bash
set -euo pipefail

INPUT_CSV="CASP_csv/casp15_casp16_prepare_targets_input.csv"
SMOKE_CSV="CASP_csv/casp15_casp16_prepare_targets_input_first5.csv"
REFERENCES_DIR="data/references"
SEQUENCES_DIR="data/sequences"
OUTPUT_TARGETS="data/targets/targets_first5.csv"

mkdir -p "CASP_csv" "${REFERENCES_DIR}" "${SEQUENCES_DIR}" "data/targets"

python - <<'PY'
import csv
from pathlib import Path

input_csv = Path("CASP_csv/casp15_casp16_prepare_targets_input.csv")
smoke_csv = Path("CASP_csv/casp15_casp16_prepare_targets_input_first5.csv")
false_values = {"0", "false", "f", "no", "n", "off", "disabled", "skip"}

with input_csv.open(newline="") as f:
    reader = csv.DictReader(f)
    rows = []
    for row in reader:
        enabled = row.get("enabled", "").strip().lower()
        if enabled and enabled in false_values:
            continue
        rows.append(row)
        if len(rows) == 5:
            break

if len(rows) < 5:
    raise SystemExit(f"Only found {len(rows)} enabled rows in {input_csv}; expected 5")

smoke_csv.parent.mkdir(parents=True, exist_ok=True)
with smoke_csv.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {smoke_csv} with {len(rows)} enabled rows")
PY

python scripts/fetch_reference_pdbs.py \
  --input-csv "${SMOKE_CSV}" \
  --references-dir "${REFERENCES_DIR}"

python scripts/prepare_targets_from_csv.py \
  --input-csv "${SMOKE_CSV}" \
  --output-targets "${OUTPUT_TARGETS}" \
  --references-dir "${REFERENCES_DIR}" \
  --sequences-dir "${SEQUENCES_DIR}" \
  --overwrite

echo
echo "Generated smoke files:"
echo "  ${SMOKE_CSV}"
echo "  ${OUTPUT_TARGETS}"
echo
echo "FASTA files:"
while IFS=, read -r target_id _; do
  if [[ "${target_id}" == "target_id" ]]; then
    continue
  fi
  echo "  ${SEQUENCES_DIR}/${target_id}.fasta"
done < "${OUTPUT_TARGETS}"
echo
echo "Reference files:"
while IFS=, read -r target_id _; do
  if [[ "${target_id}" == "target_id" ]]; then
    continue
  fi
  echo "  ${REFERENCES_DIR}/${target_id}.pdb"
done < "${OUTPUT_TARGETS}"
echo
echo "Preview of ${OUTPUT_TARGETS}:"
sed -n '1,8p' "${OUTPUT_TARGETS}"
