#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

STAGE_COLUMNS = [
    "msa_used",
    "msa_source",
    "msa_mode",
    "msa_database",
    "msa_database_path",
    "msa_a3m_file",
    "msa_build_runtime_sec",
    "msa_build_carbon_emissions_g",
    "msa_build_energy_consumed_kwh",
    "msa_build_included_in_runtime",
    "msa_build_included_in_carbon",
    "msa_reused",
    "inference_runtime_sec",
    "inference_carbon_emissions_g",
    "inference_energy_consumed_kwh",
    "total_runtime_sec",
    "total_carbon_emissions_g",
    "total_energy_consumed_kwh",
    "shared_msa_source_model",
    "shared_msa_a3m_file",
    "shared_msa_dir",
    "stage_metadata_note",
]

MSA_COPY_COLUMNS = [
    "msa_used",
    "msa_source",
    "msa_mode",
    "msa_database",
    "msa_database_path",
    "msa_a3m_file",
    "msa_build_runtime_sec",
    "msa_build_carbon_emissions_g",
    "msa_build_energy_consumed_kwh",
    "msa_build_included_in_runtime",
    "msa_build_included_in_carbon",
]

KEY_ALIASES = {
    "msa_generation_time_sec": "msa_build_runtime_sec",
    "shared_msa_a3m_file": "shared_msa_a3m_file",
    "local_msa_a3m_file": "msa_a3m_file",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update one prediction_manifest.csv row from runner metadata.json.")
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--domain-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--success", required=True)
    parser.add_argument("--return-code", required=True)
    parser.add_argument("--error-message", default="")
    parser.add_argument("--start-time", default="")
    parser.add_argument("--end-time", default="")
    parser.add_argument("--runtime-sec", default="")
    parser.add_argument("--command", default="")
    parser.add_argument("--runner-metadata", type=Path)
    parser.add_argument("--run-carbon-metadata", type=Path)
    return parser.parse_args()


def read_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_json(path: Path | None) -> dict[str, object]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        return {"stage_metadata_note": f"could not parse runner metadata: {exc!r}"}


def stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def metadata_values(raw: dict[str, object]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in raw.items():
        target = KEY_ALIASES.get(key, key)
        if target in STAGE_COLUMNS:
            values[target] = stringify(value)
    return values




def numeric(value: str) -> float | None:
    try:
        text = str(value).strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None


def sum_values(*values: str) -> str:
    nums = [numeric(value) for value in values]
    nums = [value for value in nums if value is not None]
    return str(sum(nums)) if nums else ""


def carbon_stage_values(raw: dict[str, object]) -> dict[str, str]:
    if not raw:
        return {}
    values: dict[str, str] = {}
    if "elapsed_sec" in raw:
        values["inference_runtime_sec"] = stringify(raw.get("elapsed_sec"))
    if "carbon_emissions_g" in raw:
        values["inference_carbon_emissions_g"] = stringify(raw.get("carbon_emissions_g"))
    if "carbon_energy_consumed_kwh" in raw:
        values["inference_energy_consumed_kwh"] = stringify(raw.get("carbon_energy_consumed_kwh"))
    note_parts = []
    output_file = stringify(raw.get("carbon_output_file"))
    if output_file:
        note_parts.append(f"runner CodeCarbon output: {output_file}")
    error = stringify(raw.get("carbon_error"))
    command_error = stringify(raw.get("command_error"))
    if error:
        note_parts.append(f"runner CodeCarbon error: {error}")
    if command_error:
        note_parts.append(f"runner command error: {command_error}")
    if note_parts:
        values["stage_metadata_note"] = "; ".join(note_parts)
    return values

SHARED_MSA_COPY_MODELS = {
    "openfold": "OpenFold",
    "boltz2": "Boltz-2",
    "protenix": "Protenix",
}

def find_colabfold_row(rows: list[dict[str, str]], domain_id: str) -> dict[str, str]:
    for row in rows:
        if row.get("domain_id") == domain_id and row.get("model") == "colabfold":
            return row
    return {}


def main() -> None:
    args = parse_args()
    rows, fieldnames = read_rows(args.metadata)
    for column in STAGE_COLUMNS:
        if column not in fieldnames:
            fieldnames.append(column)
            for row in rows:
                row[column] = ""

    runner_values = metadata_values(load_json(args.runner_metadata))
    carbon_values = carbon_stage_values(load_json(args.run_carbon_metadata))
    colabfold_row = find_colabfold_row(rows, args.domain_id)

    for row in rows:
        if row.get("domain_id") != args.domain_id or row.get("model") != args.model:
            continue
        row.update(
            {
                "success": args.success,
                "return_code": args.return_code,
                "error_message": args.error_message,
                "start_time": args.start_time,
                "end_time": args.end_time,
                "runtime_sec": args.runtime_sec,
                "command": args.command,
            }
        )
        row.update(runner_values)
        if carbon_values:
            carbon_note = carbon_values.pop("stage_metadata_note", "")
            row.update({key: value for key, value in carbon_values.items() if value})
            if carbon_note:
                row["stage_metadata_note"] = "; ".join(part for part in [row.get("stage_metadata_note", ""), carbon_note] if part)
        if not row.get("inference_runtime_sec"):
            row["inference_runtime_sec"] = args.runtime_sec
        if not row.get("total_runtime_sec"):
            row["total_runtime_sec"] = args.runtime_sec
        if args.model in SHARED_MSA_COPY_MODELS and colabfold_row:
            for column in MSA_COPY_COLUMNS:
                row[column] = colabfold_row.get(column, row.get(column, ""))
            source_a3m = colabfold_row.get("msa_a3m_file", "") or row.get("shared_msa_a3m_file", "")
            row["msa_reused"] = "true"
            row["shared_msa_source_model"] = "colabfold"
            row["shared_msa_a3m_file"] = source_a3m
            row["msa_build_included_in_runtime"] = "false"
            row["msa_build_included_in_carbon"] = "false"
            note = row.get("stage_metadata_note", "")
            addition = f"{SHARED_MSA_COPY_MODELS[args.model]} reused the ColabFold A3M; MSA build time/carbon copied from the colabfold row."
            row["stage_metadata_note"] = "; ".join(part for part in [note, addition] if part)
        if row.get("msa_build_runtime_sec") or row.get("inference_runtime_sec"):
            row["total_runtime_sec"] = sum_values(row.get("msa_build_runtime_sec", ""), row.get("inference_runtime_sec", "")) or row.get("total_runtime_sec", "")
        if row.get("msa_build_carbon_emissions_g") or row.get("inference_carbon_emissions_g"):
            row["total_carbon_emissions_g"] = sum_values(row.get("msa_build_carbon_emissions_g", ""), row.get("inference_carbon_emissions_g", ""))
        if row.get("msa_build_energy_consumed_kwh") or row.get("inference_energy_consumed_kwh"):
            row["total_energy_consumed_kwh"] = sum_values(row.get("msa_build_energy_consumed_kwh", ""), row.get("inference_energy_consumed_kwh", ""))
        break
    else:
        raise SystemExit(f"No metadata row for {args.domain_id}/{args.model}")

    write_rows(args.metadata, rows, fieldnames)


if __name__ == "__main__":
    main()
