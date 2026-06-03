#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

TIMING_COLUMNS = [
    "inference_time_sec",
    "inference_time_sec_per_prediction",
    "prediction_count",
    "trials_run",
    "max_trials",
    "successful_trial",
    "success",
    "return_code",
]


def load_targets(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"target_id", "reference_pdb", "chain_id"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Target CSV is missing required columns: {sorted(missing)}")
        return list(reader)


def run_command(cmd: list[str]) -> tuple[bool, str]:
    print(" ".join(cmd))
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode == 0, completed.stderr.strip() or completed.stdout.strip()


def load_run_metadata(path: Path) -> pd.DataFrame:
    if not path.exists():
        print(f"WARNING: run metadata not found; timing columns will be empty: {path}", file=sys.stderr)
        return pd.DataFrame()
    metadata = pd.read_csv(path)
    if "rank" in metadata:
        metadata["rank"] = pd.to_numeric(metadata["rank"], errors="coerce").astype("Int64")
    if "output_pdb" in metadata:
        metadata["prediction"] = metadata["output_pdb"].map(
            lambda value: Path(str(value)).name if pd.notna(value) and str(value) else ""
        )
    return metadata


def add_rank_and_timing_columns(score_csv: Path, target: dict[str, str], run_metadata: pd.DataFrame) -> None:
    df = pd.read_csv(score_csv)
    if "rank" not in df.columns:
        df["rank"] = df["prediction"].map(extract_rank)
        insert_at = list(df.columns).index("prediction") + 1
        cols = list(df.columns)
        cols.insert(insert_at, cols.pop(cols.index("rank")))
        df = df[cols]
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce").astype("Int64")
    if "pdb_id" not in df.columns:
        insert_at = list(df.columns).index("target_id") + 1
        df.insert(insert_at, "pdb_id", target.get("pdb_id", ""))
    if "chain_id" not in df.columns:
        insert_at = list(df.columns).index("pdb_id") + 1
        df.insert(insert_at, "chain_id", target.get("chain_id", ""))

    for column in TIMING_COLUMNS:
        if column in df.columns:
            df = df.drop(columns=[column])

    if run_metadata.empty:
        for column in TIMING_COLUMNS:
            df[column] = pd.NA
        df.to_csv(score_csv, index=False)
        return

    needed = ["target_id", "model", "rank", *TIMING_COLUMNS]
    available = [column for column in needed if column in run_metadata.columns]
    if {"target_id", "model", "rank"} - set(available):
        print("WARNING: run metadata is missing target_id/model/rank; timing columns will be empty", file=sys.stderr)
        for column in TIMING_COLUMNS:
            df[column] = pd.NA
        df.to_csv(score_csv, index=False)
        return

    timing = run_metadata[available].copy()
    timing = timing.dropna(subset=["rank"])
    timing["rank"] = pd.to_numeric(timing["rank"], errors="coerce").astype("Int64")
    timing = timing.drop_duplicates(["target_id", "model", "rank"], keep="last")
    df = df.merge(timing, on=["target_id", "model", "rank"], how="left")
    missing = df["inference_time_sec"].isna().sum() if "inference_time_sec" in df else len(df)
    if missing:
        print(f"WARNING: {missing} scored prediction row(s) had no matching timing metadata for {score_csv}", file=sys.stderr)
    df.to_csv(score_csv, index=False)


def extract_rank(prediction: object) -> int | None:
    match = re.search(r"rank_(\d+)\.pdb$", str(prediction))
    if not match:
        return None
    return int(match.group(1))


def parse_model_list(models: str) -> list[str]:
    return [name.strip() for name in models.split(",") if name.strip()]


def write_score_metric_definitions(scores_dir: Path) -> None:
    rows = [
        {
            "metric": "lddt_ca",
            "full_name": "Local Distance Difference Test over C-alpha atoms",
            "scale": "0-1; higher is better",
            "description": "Primary local-geometry ranking metric computed from matched C-alpha atoms.",
        },
        {
            "metric": "gdt_ts",
            "full_name": "Global Distance Test - Total Score",
            "scale": "0-1; higher is better",
            "description": "Average of fractions of aligned residues within 1, 2, 4, and 8 Angstrom distance cutoffs after superposition.",
        },
        {
            "metric": "gdt_ts_percent",
            "full_name": "Global Distance Test - Total Score percent",
            "scale": "0-100; higher is better",
            "description": "The same GDT_TS value expressed as a percentage.",
        },
        {
            "metric": "gdt_p1/gdt_p2/gdt_p4/gdt_p8",
            "full_name": "GDT cutoff fractions",
            "scale": "0-1; higher is better",
            "description": "Fractions of aligned residues within 1, 2, 4, and 8 Angstrom cutoffs used to compute GDT_TS.",
        },
        {
            "metric": "tmalign_tm_score_ref",
            "full_name": "TM-score normalized by reference length",
            "scale": "0-1; higher is better",
            "description": "Secondary global topology metric from USalign/TM-align normalized by reference length.",
        },
        {
            "metric": "ca_rmsd",
            "full_name": "C-alpha RMSD",
            "scale": "Angstrom; lower is better",
            "description": "Diagnostic C-alpha RMSD from the benchmark's configured residue matching mode.",
        },
    ]
    csv_path = scores_dir / "score_metric_definitions.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "full_name", "scale", "description"])
        writer.writeheader()
        writer.writerows(rows)
    md_lines = [
        "# Score Metric Definitions",
        "",
        "| Metric | Full name | Scale | Description |",
        "|---|---|---|---|",
    ]
    for row in rows:
        md_lines.append(f"| {row['metric']} | {row['full_name']} | {row['scale']} | {row['description']} |")
    (scores_dir / "score_metric_definitions.md").write_text("\n".join(md_lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score all benchmark targets and generate target/all-target summaries.")
    parser.add_argument("--targets", default="data/targets/targets.csv")
    parser.add_argument("--config", default="configs/models.yaml")
    parser.add_argument("--top-k", type=int, default=5, help="Accepted for workflow symmetry; scoring uses available rank_*.pdb files.")
    parser.add_argument("--predictions-dir", default="data/predictions")
    parser.add_argument("--scores-dir", default="data/scores")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--run-metadata", default="", help="Run metadata CSV with inference timing. Defaults to <results-dir>/run_metadata.csv.")
    parser.add_argument("--match-mode", choices=["sequential", "resseq", "sequence"], default="sequential")
    parser.add_argument("--models", default="", help="Comma-separated enabled model IDs to score.")
    parser.add_argument("--use-tmalign", action="store_true", default=True)
    parser.add_argument("--no-tmalign", action="store_false", dest="use_tmalign")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--use-gdt-ts", action="store_true", default=True)
    parser.add_argument("--no-gdt-ts", action="store_false", dest="use_gdt_ts")
    parser.add_argument("--gdt-ts-method", choices=["auto", "external", "internal"], default="auto")
    parser.add_argument("--gdt-ts-bin", default="auto")
    args = parser.parse_args()

    scores_dir = Path(args.scores_dir)
    scores_dir.mkdir(parents=True, exist_ok=True)
    run_metadata_path = Path(args.run_metadata) if args.run_metadata else Path(args.results_dir) / "run_metadata.csv"
    run_metadata = load_run_metadata(run_metadata_path)
    requested_models = parse_model_list(args.models)
    failures = 0

    for target in load_targets(Path(args.targets)):
        target_id = target["target_id"]
        reference = Path(target["reference_pdb"])
        if not reference.exists():
            message = f"Missing reference PDB for {target_id}: {reference}"
            if args.fail_fast:
                raise SystemExit(message)
            print(f"WARNING: {message}", file=sys.stderr)
            failures += 1
            continue

        score_cmd = [
            sys.executable,
            "scripts/02_score_predictions.py",
            "--target-id",
            target_id,
            "--reference",
            str(reference),
            "--ref-chain",
            target["chain_id"],
            "--pred-chain",
            "A",
            "--match-mode",
            args.match_mode,
            "--config",
            args.config,
            "--only-enabled-models",
            "--pred-root",
            args.predictions_dir,
            "--outdir",
            str(scores_dir),
        ]
        if requested_models:
            score_cmd.extend(["--models", ",".join(requested_models)])
        if args.use_tmalign:
            score_cmd.append("--use-tmalign")
        if args.use_gdt_ts:
            score_cmd.append("--use-gdt-ts")
        else:
            score_cmd.append("--no-gdt-ts")
        score_cmd.extend(["--gdt-ts-method", args.gdt_ts_method, "--gdt-ts-bin", args.gdt_ts_bin])
        ok, error = run_command(score_cmd)
        score_csv = scores_dir / f"{target_id}_scores.csv"
        if ok and score_csv.exists():
            add_rank_and_timing_columns(score_csv, target, run_metadata)
        else:
            failures += 1
            if args.fail_fast:
                raise SystemExit(error)
            continue

        summary_cmd = [
            sys.executable,
            "scripts/03_summarize_scores.py",
            "--scores",
            str(score_csv),
            "--output",
            str(scores_dir / f"{target_id}_model_summary.csv"),
            "--markdown-output",
            str(scores_dir / f"{target_id}_model_summary.md"),
        ]
        ok, error = run_command(summary_cmd)
        if not ok:
            failures += 1
            if args.fail_fast:
                raise SystemExit(error)

    all_ok, error = run_command(
        [
            sys.executable,
            "scripts/05_summarize_all_targets.py",
            "--targets",
            args.targets,
            "--scores-dir",
            str(scores_dir),
            "--out-csv",
            str(scores_dir / "all_targets_model_summary.csv"),
            "--out-md",
            str(scores_dir / "all_targets_model_summary.md"),
        ]
    )
    if not all_ok:
        failures += 1
        if args.fail_fast:
            raise SystemExit(error)

    write_score_metric_definitions(scores_dir)

    if failures:
        raise SystemExit(f"Scoring completed with {failures} failure(s).")
    print("Scoring completed successfully.")
    print(f"Score metric definitions written to: {scores_dir / 'score_metric_definitions.csv'}")


if __name__ == "__main__":
    main()
