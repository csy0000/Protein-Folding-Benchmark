#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


def truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize manifest prediction status metadata.")
    parser.add_argument("--out-root", required=True)
    args = parser.parse_args()

    out_root = Path(args.out_root)
    metadata_path = out_root / "metadata" / "prediction_manifest.csv"
    if not metadata_path.exists():
        raise SystemExit(f"Missing metadata file: {metadata_path}")

    with metadata_path.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    domains = {row.get("domain_id", "") for row in rows if row.get("domain_id")}
    models = {row.get("model", "") for row in rows if row.get("model")}
    successful = [row for row in rows if truthy(row.get("success", ""))]
    failed = [row for row in rows if row.get("success", "").strip().lower() in {"false", "0", "no"}]
    pending = [row for row in rows if row.get("success", "").strip().lower() in {"", "pending"}]

    print(f"selected_targets: {len(domains)}")
    print(f"models: {len(models)}")
    print(f"expected_total_runs: {len(rows)}")
    print(f"successful_runs: {len(successful)}")
    print(f"failed_runs: {len(failed)}")
    print(f"pending_runs: {len(pending)}")
    for label, counter in [
        ("target_qc_status", Counter(row.get("target_qc_status", row.get("should_use", "")) for row in rows)),
        ("model", Counter(row.get("model", "") for row in rows)),
        ("casp_round", Counter(row.get("casp_round", "") for row in rows)),
    ]:
        print(label + ":")
        for value, count in counter.most_common():
            print(f"  {value}: {count}")

    status_path = out_root / "metadata" / "prediction_status.csv"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    with status_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {status_path}")


if __name__ == "__main__":
    main()
