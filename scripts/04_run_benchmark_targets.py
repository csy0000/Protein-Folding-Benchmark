#!/usr/bin/env python3

import argparse
import csv
import subprocess
import sys
from pathlib import Path

import pandas as pd


def run_command(cmd: list[str]) -> tuple[str, str]:
    print(" ".join(cmd))
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    status = "passed" if completed.returncode == 0 else "failed"
    error = "" if completed.returncode == 0 else (completed.stderr.strip() or completed.stdout.strip())
    return status, error


def write_fasta(target_id: str, sequence: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    sequence = "".join(sequence.split()).upper()
    wrapped = "\n".join(sequence[i : i + 80] for i in range(0, len(sequence), 80))
    output.write_text(f">{target_id}\n{wrapped}\n")


def load_targets(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run predictions, scoring, and summaries for all benchmark targets.")
    parser.add_argument("--targets", default="data/targets/targets.csv")
    parser.add_argument("--config", default="configs/models.yaml")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--only-enabled-models", action="store_true")
    parser.add_argument("--use-tmalign", action="store_true")
    parser.add_argument("--match-mode", choices=["sequential", "resseq"], default="sequential")
    parser.add_argument("--status-csv", default="data/scores/benchmark_run_status.csv")
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    for target in load_targets(Path(args.targets)):
        target_id = target["target_id"]
        chain_id = target["chain_id"]
        sequence = target["sequence"]
        reference = Path(target["reference_pdb"])
        fasta = Path("data/sequences") / f"{target_id}.fasta"
        score_csv = Path("data/scores") / f"{target_id}_scores.csv"
        summary_csv = Path("data/scores") / f"{target_id}_model_summary.csv"
        summary_md = Path("data/scores") / f"{target_id}_model_summary.md"

        row = {
            "target_id": target_id,
            "prediction_status": "not_run",
            "scoring_status": "not_run",
            "summary_status": "not_run",
            "score_csv": str(score_csv),
            "summary_csv": str(summary_csv),
            "error": "",
        }

        try:
            if not fasta.exists():
                write_fasta(target_id, sequence, fasta)
            if not reference.exists():
                raise FileNotFoundError(f"Missing reference PDB: {reference}")
        except Exception as exc:
            row["error"] = str(exc)
            rows.append(row)
            print(f"[target failed] {target_id}: {exc}", file=sys.stderr)
            continue

        print(f"\n[target] {target_id}")
        predict_cmd = [
            sys.executable,
            "scripts/01_predict_top5.py",
            "--target-id",
            target_id,
            "--fasta",
            str(fasta),
            "--config",
            args.config,
            "--top-k",
            str(args.top_k),
        ]
        row["prediction_status"], prediction_error = run_command(predict_cmd)

        score_cmd = [
            sys.executable,
            "scripts/02_score_predictions.py",
            "--target-id",
            target_id,
            "--reference",
            str(reference),
            "--ref-chain",
            chain_id,
            "--pred-chain",
            "A",
            "--config",
            args.config,
            "--match-mode",
            args.match_mode,
        ]
        if args.only_enabled_models:
            score_cmd.append("--only-enabled-models")
        if args.use_tmalign:
            score_cmd.append("--use-tmalign")
        row["scoring_status"], scoring_error = run_command(score_cmd)

        summary_cmd = [
            sys.executable,
            "scripts/03_summarize_scores.py",
            "--scores",
            str(score_csv),
            "--output",
            str(summary_csv),
            "--markdown-output",
            str(summary_md),
        ]
        if row["scoring_status"] == "passed" and score_csv.exists():
            row["summary_status"], summary_error = run_command(summary_cmd)
        else:
            row["summary_status"] = "skipped"
            summary_error = "scoring failed or score CSV missing"

        errors = [message for message in [prediction_error, scoring_error, summary_error] if message]
        row["error"] = " | ".join(errors)
        rows.append(row)

    status = pd.DataFrame(rows)
    status_path = Path(args.status_csv)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status.to_csv(status_path, index=False)
    print(status)
    print(f"Benchmark status written to: {status_path}")


if __name__ == "__main__":
    main()
