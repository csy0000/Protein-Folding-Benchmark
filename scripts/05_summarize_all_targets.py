#!/usr/bin/env python3

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import pandas as pd


OUTPUT_COLUMNS = [
    "model",
    "n_targets",
    "n_targets_success",
    "n_total_predictions",
    "mean_best_lddt_ca",
    "std_best_lddt_ca",
    "mean_best_tmalign_tm_score_ref",
    "std_best_tmalign_tm_score_ref",
    "mean_best_tmalign_rmsd",
    "std_best_tmalign_rmsd",
    "mean_best_gdt_ts",
    "mean_best_GDT_TS",
    "std_best_gdt_ts",
    "std_best_GDT_TS",
    "mean_best_gdt_ts_percent",
    "mean_best_GDT_TS_percent",
    "std_best_gdt_ts_percent",
    "std_best_GDT_TS_percent",
    "mean_best_ca_rmsd",
    "std_best_ca_rmsd",
    "mean_n_success",
]


def read_targets(path: Path) -> list[str]:
    with path.open(newline="") as f:
        return [row["target_id"] for row in csv.DictReader(f)]


def mean_value(series: pd.Series) -> float:
    valid = pd.to_numeric(series, errors="coerce").dropna()
    if valid.empty:
        return np.nan
    return float(valid.mean())


def sample_std(series: pd.Series) -> float:
    valid = pd.to_numeric(series, errors="coerce").dropna()
    if len(valid) < 2:
        return np.nan
    return float(valid.std(ddof=1))


def write_markdown(summary: pd.DataFrame, output: Path) -> None:
    headers = [
        "model",
        "n_targets_success/n_targets",
        "n_total_predictions",
        "mean_best_lddt_ca",
        "mean_best_tmalign_tm_score_ref",
        "mean_best_tmalign_rmsd",
        "mean_best_gdt_ts (Global Distance Test - Total Score)",
        "mean_best_ca_rmsd",
    ]

    def fmt(value: object) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, (float, np.floating)):
            return f"{value:.5f}"
        return str(value)

    lines = [
        "Primary metric: lDDT-C-alpha",
        "",
        "Secondary metric: TM-score normalized by reference length",
        "",
        "GDT_TS: Global Distance Test - Total Score, reported on a 0-1 scale; mean_best_gdt_ts_percent is the same score on a 0-100 scale.",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in summary.iterrows():
        values = [
            row["model"],
            f"{int(row['n_targets_success'])}/{int(row['n_targets'])}",
            int(row["n_total_predictions"]),
            row["mean_best_lddt_ca"],
            row["mean_best_tmalign_tm_score_ref"],
            row["mean_best_tmalign_rmsd"],
            row["mean_best_gdt_ts"],
            row["mean_best_ca_rmsd"],
        ]
        lines.append("| " + " | ".join(fmt(value) for value in values) + " |")
    output.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate per-target model summaries across benchmark targets.")
    parser.add_argument("--targets", default="data/targets/targets.csv")
    parser.add_argument("--scores-dir", default="data/scores")
    parser.add_argument("--out-csv", default="data/scores/all_targets_model_summary.csv")
    parser.add_argument("--out-md", default="data/scores/all_targets_model_summary.md")
    args = parser.parse_args()

    scores_dir = Path(args.scores_dir)
    frames: list[pd.DataFrame] = []
    for target_id in read_targets(Path(args.targets)):
        summary_path = scores_dir / f"{target_id}_model_summary.csv"
        if not summary_path.exists():
            print(f"WARNING: missing target summary: {summary_path}", file=sys.stderr)
            continue
        df = pd.read_csv(summary_path)
        df["target_id"] = target_id
        frames.append(df)

    if not frames:
        raise SystemExit("No target summary files found")

    combined = pd.concat(frames, ignore_index=True)
    rows: list[dict[str, object]] = []
    for model, group in combined.groupby("model", sort=True):
        n_success = pd.to_numeric(group.get("n_success", np.nan), errors="coerce")
        rows.append(
            {
                "model": model,
                "n_targets": int(group["target_id"].nunique()),
                "n_targets_success": int((n_success > 0).sum()),
                "n_total_predictions": int(pd.to_numeric(group["n_predictions"], errors="coerce").fillna(0).sum()),
                "mean_best_lddt_ca": mean_value(group["best_lddt_ca"]),
                "std_best_lddt_ca": sample_std(group["best_lddt_ca"]),
                "mean_best_tmalign_tm_score_ref": mean_value(group["best_tmalign_tm_score_ref"]),
                "std_best_tmalign_tm_score_ref": sample_std(group["best_tmalign_tm_score_ref"]),
                "mean_best_tmalign_rmsd": mean_value(group["best_tmalign_rmsd"]),
                "std_best_tmalign_rmsd": sample_std(group["best_tmalign_rmsd"]),
                "mean_best_gdt_ts": mean_value(group["best_gdt_ts"]) if "best_gdt_ts" in group else np.nan,
                "mean_best_GDT_TS": mean_value(group["best_gdt_ts"]) if "best_gdt_ts" in group else np.nan,
                "std_best_gdt_ts": sample_std(group["best_gdt_ts"]) if "best_gdt_ts" in group else np.nan,
                "std_best_GDT_TS": sample_std(group["best_gdt_ts"]) if "best_gdt_ts" in group else np.nan,
                "mean_best_gdt_ts_percent": mean_value(group["best_gdt_ts_percent"]) if "best_gdt_ts_percent" in group else np.nan,
                "mean_best_GDT_TS_percent": mean_value(group["best_gdt_ts_percent"]) if "best_gdt_ts_percent" in group else np.nan,
                "std_best_gdt_ts_percent": sample_std(group["best_gdt_ts_percent"]) if "best_gdt_ts_percent" in group else np.nan,
                "std_best_GDT_TS_percent": sample_std(group["best_gdt_ts_percent"]) if "best_gdt_ts_percent" in group else np.nan,
                "mean_best_ca_rmsd": mean_value(group["best_ca_rmsd"]),
                "std_best_ca_rmsd": sample_std(group["best_ca_rmsd"]),
                "mean_n_success": mean_value(group["n_success"]),
            }
        )

    summary = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    summary = summary.sort_values(
        ["mean_best_lddt_ca", "mean_best_tmalign_tm_score_ref", "mean_best_gdt_ts", "mean_best_tmalign_rmsd", "mean_best_ca_rmsd", "model"],
        ascending=[False, False, False, True, True, True],
        na_position="last",
    )

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_csv, index=False)
    write_markdown(summary, Path(args.out_md))

    print(summary)
    print(f"All-target summary written to: {out_csv}")
    print(f"All-target Markdown summary written to: {args.out_md}")


if __name__ == "__main__":
    main()
