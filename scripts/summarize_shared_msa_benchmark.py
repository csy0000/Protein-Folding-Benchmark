#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def f(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Combine shared-MSA cost, model run metadata, and per-target scores.")
    parser.add_argument("--msa-metadata", required=True)
    parser.add_argument("--run-metadata", required=True)
    parser.add_argument("--scores", required=True, help="Per-target score CSV or directory containing *_scores.csv files")
    parser.add_argument("--out-csv", required=True)
    args = parser.parse_args()

    msa_rows = {row["target_id"]: row for row in read_csv(Path(args.msa_metadata))}
    run_rows = read_csv(Path(args.run_metadata))
    score_path = Path(args.scores)
    score_rows: list[dict[str, str]] = []
    if score_path.is_dir():
        for path in sorted(score_path.glob("*_scores.csv")):
            score_rows.extend(read_csv(path))
    else:
        score_rows = read_csv(score_path)
    scores = {(row.get("target_id", ""), row.get("model", ""), row.get("rank", "")): row for row in score_rows}

    rows = []
    for run in run_rows:
        if run.get("success") != "true":
            continue
        key = (run.get("target_id", ""), run.get("model", ""), run.get("rank", ""))
        score = scores.get(key, {})
        msa = msa_rows.get(run.get("target_id", ""), {})
        msa_time = f(msa.get("msa_runtime_sec", ""))
        msa_carbon = f(msa.get("msa_carbon_emissions_g", ""))
        model_time = f(run.get("inference_time_sec", ""))
        model_carbon = f(run.get("carbon_emissions_g", ""))
        rows.append({
            "target_id": run.get("target_id", ""),
            "model": run.get("model", ""),
            "msa_runtime_sec": msa.get("msa_runtime_sec", ""),
            "msa_carbon_emissions_g": msa.get("msa_carbon_emissions_g", ""),
            "model_inference_time_sec": run.get("inference_time_sec", ""),
            "model_carbon_emissions_g": run.get("carbon_emissions_g", ""),
            "total_time_with_shared_msa_sec": f"{msa_time + model_time:.6f}",
            "total_carbon_with_shared_msa_g": f"{msa_carbon + model_carbon:.12g}",
            "lddt_ca": score.get("lddt_ca", ""),
            "ca_rmsd": score.get("ca_rmsd", ""),
            "gdt_ts": score.get("gdt_ts", ""),
            "gdt_ts_percent": score.get("gdt_ts_percent", ""),
            "gdt_p1": score.get("gdt_p1", ""),
            "gdt_p2": score.get("gdt_p2", ""),
            "gdt_p4": score.get("gdt_p4", ""),
            "gdt_p8": score.get("gdt_p8", ""),
            "gdt_ts_method": score.get("gdt_ts_method", ""),
            "gdt_ts_error": score.get("gdt_ts_error", ""),
            "tmalign_tm_score_ref": score.get("tmalign_tm_score_ref", ""),
        })

    out = Path(args.out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "target_id", "model", "msa_runtime_sec", "msa_carbon_emissions_g",
        "model_inference_time_sec", "model_carbon_emissions_g",
        "total_time_with_shared_msa_sec", "total_carbon_with_shared_msa_g",
        "lddt_ca", "ca_rmsd", "gdt_ts", "gdt_ts_percent", "gdt_p1", "gdt_p2", "gdt_p4", "gdt_p8", "gdt_ts_method", "gdt_ts_error", "tmalign_tm_score_ref",
    ]
    with out.open("w", newline="") as fobj:
        writer = csv.DictWriter(fobj, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
