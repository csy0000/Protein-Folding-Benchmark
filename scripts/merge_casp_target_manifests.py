#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from build_casp_target_manifest import MANIFEST_COLUMNS, write_qc_summary


STRICT_COLUMNS = [
    "domain_id",
    "target_id",
    "pdb_id",
    "chain_id",
    "sequence",
    "target_length",
    "sequence_start",
    "sequence_end",
    "residue_start",
    "residue_end",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge CASP target manifests and write QC summaries.")
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--qc-out", default="data/casp_manifest_qc_summary.csv")
    parser.add_argument("--strict-out", default="data/casp15_casp16_strict_monomer_targets.csv")
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    for input_path in args.inputs:
        rows.extend(read_rows(Path(input_path)))

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in MANIFEST_COLUMNS})

    write_qc_summary(rows, Path(args.qc_out))

    strict_rows = [row for row in rows if row.get("should_use") == "Yes"]
    strict_output = Path(args.strict_out)
    strict_output.parent.mkdir(parents=True, exist_ok=True)
    with strict_output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STRICT_COLUMNS)
        writer.writeheader()
        for row in strict_rows:
            writer.writerow({field: row.get(field, "") for field in STRICT_COLUMNS})

    print(f"Merged rows: {len(rows)}")
    print(f"Rows with PDB codes: {sum(1 for row in rows if row.get('pdb_id'))}")
    print(f"Rows with extracted sequences: {sum(1 for row in rows if row.get('sequence'))}")
    print(f"High-confidence chain mappings: {sum(1 for row in rows if row.get('chain_assignment_confidence') == 'high')}")
    print(f"should_use counts: {dict(Counter(row.get('should_use', '') for row in rows))}")
    print(f"Wrote {output}")
    print(f"Wrote {args.qc_out}")
    print(f"Wrote {strict_output}")


if __name__ == "__main__":
    main()
