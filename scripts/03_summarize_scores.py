#!/usr/bin/env python3

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd


SUMMARY_COLUMNS = [
    "target_id",
    "model",
    "n_predictions",
    "n_success",
    "n_failed",
    "best_prediction",
    "best_rank_index",
    "best_rank_by_lddt_ca",
    "best_lddt_ca",
    "best_tmalign_tm_score_ref",
    "best_tmalign_tm_score_pred",
    "best_tmalign_rmsd",
    "best_tmalign_aligned_length",
    "best_gdt_ts",
    "best_GDT_TS",
    "best_gdt_ts_percent",
    "best_GDT_TS_percent",
    "best_ca_rmsd",
    "mean_lddt_ca",
    "std_lddt_ca",
    "mean_tmalign_tm_score_ref",
    "std_tmalign_tm_score_ref",
    "mean_tmalign_rmsd",
    "std_tmalign_rmsd",
    "mean_gdt_ts",
    "mean_GDT_TS",
    "std_gdt_ts",
    "std_GDT_TS",
    "mean_gdt_ts_percent",
    "mean_GDT_TS_percent",
    "std_gdt_ts_percent",
    "std_GDT_TS_percent",
    "mean_ca_rmsd",
    "std_ca_rmsd",
    "mean_n_aligned_ca",
    "max_n_aligned_ca",
    "ranking_primary_metric",
    "ranking_secondary_metric",
    "ranking_tertiary_metric",
    "ranking_quaternary_metric",
    "ranking_note",
]


def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df:
        return pd.Series(np.nan, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def is_empty_error(value: object) -> bool:
    if pd.isna(value):
        return True
    return str(value).strip() == ""


def rank_index(prediction: object) -> float:
    if pd.isna(prediction):
        return np.nan
    match = re.search(r"rank_(\d+)\.pdb$", str(prediction))
    if not match:
        return np.nan
    return int(match.group(1))


def sample_std(series: pd.Series) -> float:
    valid = series.dropna()
    if len(valid) < 2:
        return np.nan
    return float(valid.std(ddof=1))


def mean_value(series: pd.Series) -> float:
    valid = series.dropna()
    if valid.empty:
        return np.nan
    return float(valid.mean())


def max_value(series: pd.Series) -> float:
    valid = series.dropna()
    if valid.empty:
        return np.nan
    return float(valid.max())


def select_best_row(
    success_df: pd.DataFrame,
    primary_metric: str,
    secondary_metric: str,
    tertiary_metric: str,
    quaternary_metric: str,
) -> tuple[pd.Series | None, str, str, str, str, str]:
    if success_df.empty:
        return None, primary_metric, secondary_metric, tertiary_metric, quaternary_metric, "no successful predictions"

    primary = numeric_series(success_df, primary_metric)
    use_primary = primary_metric in success_df and primary.notna().any()

    sortable = success_df.copy()
    if use_primary:
        sortable["_primary"] = primary
        sortable["_secondary"] = numeric_series(success_df, secondary_metric)
        sortable["_tertiary"] = numeric_series(success_df, tertiary_metric)
        sortable["_quaternary"] = numeric_series(success_df, quaternary_metric)
        sortable = sortable.sort_values(
            ["_primary", "_secondary", "_tertiary", "_quaternary", "prediction"],
            ascending=[False, False, True, True, True],
            na_position="last",
        )
        note = (
            f"ranked by highest {primary_metric}, then highest {secondary_metric}, "
            f"then lowest {tertiary_metric}, then lowest {quaternary_metric}"
        )
        return sortable.iloc[0], primary_metric, secondary_metric, tertiary_metric, quaternary_metric, note

    fallback_metric = "ca_rmsd"
    sortable["_primary"] = numeric_series(success_df, fallback_metric)
    sortable = sortable.sort_values(["_primary", "prediction"], ascending=[True, True], na_position="last")
    note = f"{primary_metric} unavailable; ranked by lowest {fallback_metric}"
    return sortable.iloc[0], fallback_metric, "", "", "", note


def summarize_model(
    model: str,
    group: pd.DataFrame,
    primary_metric: str,
    secondary_metric: str,
    tertiary_metric: str,
    quaternary_metric: str,
) -> dict[str, object]:
    ranking_values = pd.concat(
        [
            numeric_series(group, primary_metric),
            numeric_series(group, secondary_metric),
            numeric_series(group, tertiary_metric),
            numeric_series(group, "ca_rmsd"),
        ],
        axis=1,
    )
    has_ranking_value = ranking_values.notna().any(axis=1)
    error_ok = group["error"].map(is_empty_error) if "error" in group else pd.Series(True, index=group.index)
    success = group[error_ok & has_ranking_value].copy()

    best, used_primary, used_secondary, used_tertiary, used_quaternary, note = select_best_row(
        success,
        primary_metric,
        secondary_metric,
        tertiary_metric,
        quaternary_metric,
    )

    target_id = ""
    if "target_id" in group and group["target_id"].notna().any():
        target_id = str(group["target_id"].dropna().iloc[0])

    row: dict[str, object] = {
        "target_id": target_id,
        "model": model,
        "n_predictions": int(len(group)),
        "n_success": int(len(success)),
        "n_failed": int(len(group) - len(success)),
        "best_prediction": "",
        "best_rank_index": np.nan,
        "best_rank_by_lddt_ca": np.nan,
        "best_lddt_ca": np.nan,
        "best_tmalign_tm_score_ref": np.nan,
        "best_tmalign_tm_score_pred": np.nan,
        "best_tmalign_rmsd": np.nan,
        "best_tmalign_aligned_length": np.nan,
        "best_gdt_ts": np.nan,
        "best_GDT_TS": np.nan,
        "best_gdt_ts_percent": np.nan,
        "best_GDT_TS_percent": np.nan,
        "best_ca_rmsd": np.nan,
        "mean_lddt_ca": mean_value(numeric_series(success, "lddt_ca")),
        "std_lddt_ca": sample_std(numeric_series(success, "lddt_ca")),
        "mean_tmalign_tm_score_ref": mean_value(numeric_series(success, "tmalign_tm_score_ref")),
        "std_tmalign_tm_score_ref": sample_std(numeric_series(success, "tmalign_tm_score_ref")),
        "mean_tmalign_rmsd": mean_value(numeric_series(success, "tmalign_rmsd")),
        "std_tmalign_rmsd": sample_std(numeric_series(success, "tmalign_rmsd")),
        "mean_gdt_ts": mean_value(numeric_series(success, "gdt_ts")),
        "mean_GDT_TS": mean_value(numeric_series(success, "gdt_ts")),
        "std_gdt_ts": sample_std(numeric_series(success, "gdt_ts")),
        "std_GDT_TS": sample_std(numeric_series(success, "gdt_ts")),
        "mean_gdt_ts_percent": mean_value(numeric_series(success, "gdt_ts_percent")),
        "mean_GDT_TS_percent": mean_value(numeric_series(success, "gdt_ts_percent")),
        "std_gdt_ts_percent": sample_std(numeric_series(success, "gdt_ts_percent")),
        "std_GDT_TS_percent": sample_std(numeric_series(success, "gdt_ts_percent")),
        "mean_ca_rmsd": mean_value(numeric_series(success, "ca_rmsd")),
        "std_ca_rmsd": sample_std(numeric_series(success, "ca_rmsd")),
        "mean_n_aligned_ca": mean_value(numeric_series(success, "n_aligned_ca")),
        "max_n_aligned_ca": max_value(numeric_series(success, "n_aligned_ca")),
        "ranking_primary_metric": used_primary,
        "ranking_secondary_metric": used_secondary,
        "ranking_tertiary_metric": used_tertiary,
        "ranking_quaternary_metric": used_quaternary,
        "ranking_note": note,
    }

    if best is not None:
        row.update(
            {
                "best_prediction": best.get("prediction", ""),
                "best_rank_index": rank_index(best.get("prediction", "")),
                "best_rank_by_lddt_ca": rank_index(best.get("prediction", "")),
                "best_lddt_ca": pd.to_numeric(best.get("lddt_ca", np.nan), errors="coerce"),
                "best_tmalign_tm_score_ref": pd.to_numeric(best.get("tmalign_tm_score_ref", np.nan), errors="coerce"),
                "best_tmalign_tm_score_pred": pd.to_numeric(best.get("tmalign_tm_score_pred", np.nan), errors="coerce"),
                "best_tmalign_rmsd": pd.to_numeric(best.get("tmalign_rmsd", np.nan), errors="coerce"),
                "best_tmalign_aligned_length": pd.to_numeric(best.get("tmalign_aligned_length", np.nan), errors="coerce"),
                "best_gdt_ts": pd.to_numeric(best.get("gdt_ts", np.nan), errors="coerce"),
                "best_GDT_TS": pd.to_numeric(best.get("gdt_ts", np.nan), errors="coerce"),
                "best_gdt_ts_percent": pd.to_numeric(best.get("gdt_ts_percent", np.nan), errors="coerce"),
                "best_GDT_TS_percent": pd.to_numeric(best.get("gdt_ts_percent", np.nan), errors="coerce"),
                "best_ca_rmsd": pd.to_numeric(best.get("ca_rmsd", np.nan), errors="coerce"),
            }
        )

    return row


def write_markdown(summary: pd.DataFrame, output: Path) -> None:
    headers = [
        "model",
        "n_success/n_predictions",
        "best_prediction",
        "best_lddt_ca",
        "best_tmalign_tm_score_ref",
        "best_tmalign_rmsd",
        "best_gdt_ts (Global Distance Test - Total Score)",
        "best_ca_rmsd",
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
        "GDT_TS: Global Distance Test - Total Score, reported on a 0-1 scale; gdt_ts_percent is the same score on a 0-100 scale.",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in summary.iterrows():
        values = [
            row["model"],
            f"{int(row['n_success'])}/{int(row['n_predictions'])}",
            row["best_prediction"],
            row["best_lddt_ca"],
            row["best_tmalign_tm_score_ref"],
            row["best_tmalign_rmsd"],
            row["best_gdt_ts"],
            row["best_ca_rmsd"],
        ]
        lines.append("| " + " | ".join(fmt(value) for value in values) + " |")

    output.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize per-prediction structure scores into per-model rankings.")
    parser.add_argument("--scores", required=True, help="Input per-prediction score CSV.")
    parser.add_argument("--output", required=True, help="Output per-model summary CSV.")
    parser.add_argument("--primary-metric", default="lddt_ca")
    parser.add_argument("--secondary-metric", default="tmalign_tm_score_ref")
    parser.add_argument("--tertiary-metric", default="tmalign_rmsd")
    parser.add_argument("--quaternary-metric", default="ca_rmsd")
    parser.add_argument("--markdown-output", help="Optional compact Markdown summary output path.")
    args = parser.parse_args()

    scores_path = Path(args.scores)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(scores_path)
    if "model" not in df:
        raise SystemExit("Input scores CSV must contain a 'model' column")

    rows = [
        summarize_model(
            model,
            group,
            args.primary_metric,
            args.secondary_metric,
            args.tertiary_metric,
            args.quaternary_metric,
        )
        for model, group in df.groupby("model", sort=True)
    ]
    summary = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    summary = summary.sort_values(
        ["best_lddt_ca", "best_tmalign_tm_score_ref", "best_gdt_ts", "best_tmalign_rmsd", "best_ca_rmsd", "model"],
        ascending=[False, False, False, True, True, True],
        na_position="last",
    )
    summary.to_csv(output_path, index=False)

    if args.markdown_output:
        write_markdown(summary, Path(args.markdown_output))

    print(summary)
    print(f"Model summary written to: {output_path}")
    if args.markdown_output:
        print(f"Markdown summary written to: {args.markdown_output}")


if __name__ == "__main__":
    main()
