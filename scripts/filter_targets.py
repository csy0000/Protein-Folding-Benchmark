#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


FALSE_VALUES = {"0", "false", "f", "no", "n", "off", "disabled", "skip"}
CASP_COLUMNS = ["casp", "casp_round", "target_set", "competition"]
LENGTH_COLUMNS = ["residue_count", "sequence_length", "n_residues", "target_length", "length", "n_res"]


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def enabled(row: dict[str, str]) -> bool:
    if "enabled" not in row:
        return True
    value = row.get("enabled", "").strip().lower()
    return value == "" or value not in FALSE_VALUES


def infer_casp(row: dict[str, str]) -> str:
    lower = {key.lower(): value for key, value in row.items()}
    for column in CASP_COLUMNS:
        value = lower.get(column, "").strip()
        if value:
            return value.upper()
    text = " ".join(str(value) for value in row.values())
    match = re.search(r"\b(CASP[0-9]+)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(r"casp_round\s*=\s*([^;\s]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


def infer_length(row: dict[str, str]) -> int | None:
    lower = {key.lower(): value for key, value in row.items()}
    for column in LENGTH_COLUMNS:
        value = lower.get(column, "").strip()
        if value.isdigit():
            return int(value)
    text = " ".join(str(value) for value in row.values())
    match = re.search(r"(?:target_length|sequence_length|residue_count)\s*=\s*([0-9]+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    sequence = row.get("sequence", "")
    if sequence:
        return len("".join(sequence.split()))
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter target CSV rows by CASP round and residue count.")
    parser.add_argument("--input", "--input-csv", dest="input_csv", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--casp", default="")
    parser.add_argument("--max-residues", type=int, default=None)
    parser.add_argument("--min-residues", type=int, default=None)
    parser.add_argument("--enabled-only", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    fields, rows = read_rows(input_path)
    if not fields:
        raise SystemExit(f"No CSV header found in {input_path}")

    output_rows: list[dict[str, str]] = []
    for row in rows:
        casp = infer_casp(row)
        length = infer_length(row)
        if args.enabled_only and not enabled(row):
            continue
        if args.casp and casp != args.casp.upper():
            continue
        if args.min_residues is not None and (length is None or length < args.min_residues):
            continue
        if args.max_residues is not None and (length is None or length > args.max_residues):
            continue
        row = dict(row)
        row["casp_filter_value"] = casp
        row["residue_count_inferred"] = "" if length is None else str(length)
        output_rows.append(row)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_fields = list(fields)
    for extra in ["casp_filter_value", "residue_count_inferred"]:
        if extra not in output_fields:
            output_fields.append(extra)
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Read {len(rows)} rows from {input_path}")
    print(f"Wrote {len(output_rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
