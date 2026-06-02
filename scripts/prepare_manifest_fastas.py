#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


def parse_statuses(value: str) -> set[str]:
    value = (value or "All").strip()
    if value.lower() == "all":
        return {"Yes", "Check", "No"}
    statuses = {part.strip() for part in value.split(",") if part.strip()}
    allowed = {"Yes", "Check", "No"}
    unknown = statuses - allowed
    if unknown:
        raise SystemExit(f"Unknown --include-status value(s): {', '.join(sorted(unknown))}")
    return statuses


def clean_sequence(value: str) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def wrap_sequence(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[i : i + width] for i in range(0, len(sequence), width))


def safe_name(value: str) -> str:
    name = re.sub(r"[^0-9A-Za-z_.-]+", "_", value.strip())
    return name.strip("_") or "target"


def fasta_header(row: dict[str, str]) -> str:
    domain_id = row.get("domain_id", "")
    qc = row.get("should_use", "")
    casp_round = row.get("casp_round", "")
    pdb_chain = f"{row.get('pdb_id', '')}_{row.get('chain_id', '')}".strip("_")
    residue = f"{row.get('residue_start', '')}-{row.get('residue_end', '')}"
    seq_range = f"{row.get('sequence_start', '')}-{row.get('sequence_end', '')}"
    coverage = row.get("reference_coverage", "")
    return f">{domain_id}|qc={qc}|{casp_round}|{pdb_chain}|residue={residue}|seq={seq_range}|coverage={coverage}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare FASTA files from a CASP manifest while preserving QC columns.")
    parser.add_argument("--manifest", default="data/casp15_casp16_target_manifest_prefiltered.csv")
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--include-status", default="All")
    parser.add_argument("--max-targets", type=int, default=0)
    parser.add_argument("--max-length", type=int, default=0, help="Maximum target_length/sequence length to include")
    args = parser.parse_args()

    manifest = Path(args.manifest)
    out_root = Path(args.out_root)
    sequences_dir = out_root / "sequences"
    sequences_dir.mkdir(parents=True, exist_ok=True)
    statuses = parse_statuses(args.include_status)

    with manifest.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [row for row in reader if row.get("should_use", "") in statuses]

    if args.max_length:
        rows = [
            row for row in rows
            if int(row.get("target_length") or len(clean_sequence(row.get("sequence", "")))) <= args.max_length
        ]

    if args.max_targets:
        rows = rows[: args.max_targets]

    if not fieldnames:
        raise SystemExit(f"No CSV header found in {manifest}")

    output_fields = list(fieldnames)
    for extra in ["fasta_path", "sequence_length", "sequence_warning"]:
        if extra not in output_fields:
            output_fields.append(extra)

    output_rows: list[dict[str, str]] = []
    for row in rows:
        domain_id = row.get("domain_id", "").strip()
        sequence = clean_sequence(row.get("sequence", ""))
        if not domain_id:
            raise SystemExit("Manifest row has empty domain_id")
        if not sequence:
            raise SystemExit(f"Manifest row has empty sequence for {domain_id}")
        warning = ""
        target_length = row.get("target_length", "").strip()
        if target_length.isdigit() and int(target_length) != len(sequence):
            warning = f"target_length {target_length} differs from sequence_length {len(sequence)}"
        fasta_path = sequences_dir / f"{safe_name(domain_id)}.fasta"
        fasta_path.write_text(f"{fasta_header(row)}\n{wrap_sequence(sequence)}\n")
        out = dict(row)
        out["fasta_path"] = str(fasta_path)
        out["sequence_length"] = str(len(sequence))
        out["sequence_warning"] = warning
        output_rows.append(out)

    out_root.mkdir(parents=True, exist_ok=True)
    manifest_out = out_root / "manifest_used.csv"
    with manifest_out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Selected rows: {len(output_rows)}")
    print(f"Wrote FASTA files: {len(output_rows)}")
    print(f"Wrote {manifest_out}")


if __name__ == "__main__":
    main()
