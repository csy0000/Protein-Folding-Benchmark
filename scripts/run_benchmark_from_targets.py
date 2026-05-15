#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime
from shutil import copy2
from pathlib import Path

import yaml


SINGLE_OUTPUT_MODELS = {"esmfold", "omegafold", "openfold"}

GPU_DEFAULT_ENV = {
    "boltz2": {"BOLTZ_ACCELERATOR": "gpu"},
    "chai1": {"CHAI1_DEVICE": "cuda:0"},
    "esmfold": {"ESMFOLD_CPU_ONLY": "0"},
    "openfold": {"OPENFOLD_DEVICE": "cuda:0"},
}


def load_targets(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"target_id", "sequence"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Target CSV is missing required columns: {sorted(missing)}")
        return list(reader)


def enabled_models(config_path: Path, requested: str) -> dict[str, dict[str, object]]:
    with config_path.open() as f:
        config = yaml.safe_load(f)
    models = {name: spec for name, spec in config["models"].items() if spec.get("enabled", False)}
    if requested:
        selected = [name.strip() for name in requested.split(",") if name.strip()]
        unknown = [name for name in selected if name not in config["models"]]
        if unknown:
            raise SystemExit(f"Unknown model(s): {unknown}")
        models = {name: config["models"][name] for name in selected if config["models"][name].get("enabled", False)}
        disabled = [name for name in selected if not config["models"][name].get("enabled", False)]
        if disabled:
            print(f"WARNING: requested disabled model(s) skipped: {', '.join(disabled)}", file=sys.stderr)
    return models


def write_fasta(target_id: str, sequence: str, output: Path) -> None:
    if output.exists():
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    sequence = "".join(sequence.split()).upper()
    wrapped = "\n".join(sequence[i : i + 80] for i in range(0, len(sequence), 80))
    output.write_text(f">{target_id}\n{wrapped}\n")


def count_ranks(model_out: Path) -> int:
    return len(sorted(model_out.glob("rank_*.pdb")))


def write_prediction_metadata(
    model_out: Path,
    target_id: str,
    model: str,
    top_k: int,
    status: str,
    mode: str,
    log_file: Path,
    error: str = "",
) -> None:
    metadata = {
        "target_id": target_id,
        "model": model,
        "requested_top_k": top_k,
        "available_top_k": count_ranks(model_out),
        "mode": mode,
        "status": status,
        "log_file": str(log_file),
        "notes": top_k_note(model),
        "error": error,
    }
    (model_out / "prediction_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def top_k_note(model: str) -> str:
    if model in SINGLE_OUTPUT_MODELS:
        return f"{model} currently produces one standardized prediction in this benchmark setup."
    return f"{model} may produce up to the requested top-k predictions when the runner succeeds."


METADATA_COLUMNS = [
    "target_id",
    "pdb_id",
    "chain_id",
    "model",
    "rank",
    "output_pdb",
    "success",
    "return_code",
    "inference_time_sec",
    "inference_time_sec_per_prediction",
    "prediction_count",
    "started_at",
    "finished_at",
    "command",
    "error_message",
]


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def rank_number(path: Path) -> int | str:
    try:
        return int(path.stem.split("_")[1])
    except (IndexError, ValueError):
        return ""


def append_metadata_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=METADATA_COLUMNS)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in METADATA_COLUMNS})


def timing_rows_for_run(
    target: dict[str, str],
    model: str,
    model_out: Path,
    success: bool,
    return_code: int,
    inference_time_sec: float,
    started_at: str,
    finished_at: str,
    command: list[str],
    error_message: str,
) -> list[dict[str, object]]:
    ranks = sorted(model_out.glob("rank_*.pdb")) if success else []
    prediction_count = len(ranks)
    per_prediction = inference_time_sec / prediction_count if prediction_count else ""
    base = {
        "target_id": target.get("target_id", ""),
        "pdb_id": target.get("pdb_id", ""),
        "chain_id": target.get("chain_id", ""),
        "model": model,
        "success": str(bool(success)).lower(),
        "return_code": return_code,
        "inference_time_sec": f"{inference_time_sec:.6f}",
        "inference_time_sec_per_prediction": f"{per_prediction:.6f}" if per_prediction != "" else "",
        "prediction_count": prediction_count,
        "started_at": started_at,
        "finished_at": finished_at,
        "command": " ".join(shlex.quote(part) for part in command),
        "error_message": error_message,
    }
    if not ranks:
        return [{**base, "rank": "", "output_pdb": ""}]
    return [
        {
            **base,
            "rank": rank_number(path),
            "output_pdb": str(path),
        }
        for path in ranks
    ]


def run_one(
    runner: str,
    fasta: Path,
    model_out: Path,
    top_k: int,
    log_file: Path,
    env: dict[str, str],
) -> tuple[str, str, int, float, str, str, list[str]]:
    cmd = shlex.split(runner) + [str(fasta), str(model_out), str(top_k)]
    started_at = iso_now()
    start = time.perf_counter()
    with log_file.open("w") as log:
        log.write("$ " + " ".join(shlex.quote(part) for part in cmd) + "\n\n")
        completed = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, text=True, check=False, env=env)
    inference_time_sec = time.perf_counter() - start
    finished_at = iso_now()
    if completed.returncode == 0:
        return "success", "", completed.returncode, inference_time_sec, started_at, finished_at, cmd
    return "failed", f"exit code {completed.returncode}; see {log_file}", completed.returncode, inference_time_sec, started_at, finished_at, cmd


def apply_gpu_defaults(model: str, env: dict[str, str]) -> None:
    for key, value in GPU_DEFAULT_ENV.get(model, {}).items():
        env.setdefault(key, value)


def run_mock(
    target: dict[str, str],
    model_out: Path,
    log_file: Path,
    sleep_sec: float,
) -> tuple[str, str, int, float, str, str, list[str]]:
    cmd = ["mock-runner", target["target_id"], str(model_out), str(sleep_sec)]
    started_at = iso_now()
    start = time.perf_counter()
    time.sleep(max(0.0, sleep_sec))
    model_out.mkdir(parents=True, exist_ok=True)
    for old_rank in model_out.glob("rank_*.pdb"):
        old_rank.unlink()
    reference = Path(target.get("reference_pdb", ""))
    with log_file.open("w") as log:
        log.write("$ " + " ".join(shlex.quote(part) for part in cmd) + "\n\n")
        if not reference.exists():
            elapsed = time.perf_counter() - start
            finished_at = iso_now()
            log.write(f"Missing mock reference: {reference}\n")
            return "failed", f"missing mock reference: {reference}", 1, elapsed, started_at, finished_at, cmd
        copy2(reference, model_out / "rank_001.pdb")
        metadata = {
            "model": "mock",
            "environment": "mock",
            "top_k_requested": 1,
            "top_k_generated": 1,
            "top_k_policy": "mock timing smoke test; copied reference as rank_001.pdb",
            "source_files": [str(reference)],
        }
        (model_out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        log.write(f"Copied {reference} to {model_out / 'rank_001.pdb'}\n")
    elapsed = time.perf_counter() - start
    finished_at = iso_now()
    return "success", "", 0, elapsed, started_at, finished_at, cmd


def main() -> None:
    parser = argparse.ArgumentParser(description="Run enabled benchmark models for every target in a target CSV.")
    parser.add_argument("--targets", default="data/targets/targets.csv")
    parser.add_argument("--config", default="configs/models.yaml")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--models", default="", help="Optional comma-separated enabled model subset.")
    parser.add_argument("--predictions-dir", default="data/predictions")
    parser.add_argument("--sequences-dir", default="data/sequences")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--run-metadata", default="", help="Run timing metadata CSV. Defaults to <results-dir>/run_metadata.csv.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--mock-runner", action="store_true", help="Write mock rank_001 predictions from references to test timing plumbing.")
    parser.add_argument("--mock-sleep-sec", type=float, default=0.05)
    parser.add_argument(
        "--openfold-mode",
        choices=["single_sequence", "msa", "config"],
        default="single_sequence",
        help="Default single_sequence avoids requiring full OpenFold MSA databases for the easy pipeline.",
    )
    args = parser.parse_args()

    targets = load_targets(Path(args.targets))
    models = enabled_models(Path(args.config), args.models)
    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_log = logs_dir / f"{datetime.now():%Y%m%d}_run_benchmark_from_targets.log"
    run_metadata = Path(args.run_metadata) if args.run_metadata else Path(args.results_dir) / "run_metadata.csv"
    if not args.dry_run and run_metadata.exists():
        run_metadata.unlink()

    failures = 0
    with run_log.open("w") as aggregate:
        aggregate.write(f"targets={args.targets}\nmodels={','.join(models)}\ntop_k={args.top_k}\nrun_metadata={run_metadata}\n\n")
        for target in targets:
            target_id = target["target_id"]
            fasta = Path(args.sequences_dir) / f"{target_id}.fasta"
            write_fasta(target_id, target["sequence"], fasta)
            aggregate.write(f"[target] {target_id}\n")
            for model_name, model_cfg in models.items():
                model_out = Path(args.predictions_dir) / target_id / model_name
                model_out.mkdir(parents=True, exist_ok=True)
                log_file = logs_dir / f"{datetime.now():%Y%m%d}_{target_id}_{model_name}.log"
                env = os.environ.copy()
                apply_gpu_defaults(model_name, env)
                mode = "default"
                if model_name == "openfold" and args.openfold_mode != "config":
                    env["OPENFOLD_MODE"] = args.openfold_mode
                    mode = args.openfold_mode
                if args.dry_run:
                    cmd = shlex.split(str(model_cfg["runner"])) + [str(fasta), str(model_out), str(args.top_k)]
                    aggregate.write("[dry-run] " + " ".join(shlex.quote(part) for part in cmd) + "\n")
                    print("[dry-run]", " ".join(cmd))
                    continue

                print(f"[run] {target_id} {model_name}")
                if args.mock_runner:
                    status, error, return_code, elapsed, started_at, finished_at, cmd = run_mock(
                        target,
                        model_out,
                        log_file,
                        args.mock_sleep_sec,
                    )
                else:
                    status, error, return_code, elapsed, started_at, finished_at, cmd = run_one(
                        str(model_cfg["runner"]),
                        fasta,
                        model_out,
                        args.top_k,
                        log_file,
                        env,
                    )
                write_prediction_metadata(model_out, target_id, model_name, args.top_k, status, mode, log_file, error)
                append_metadata_rows(
                    run_metadata,
                    timing_rows_for_run(
                        target,
                        model_name,
                        model_out,
                        status == "success",
                        return_code,
                        elapsed,
                        started_at,
                        finished_at,
                        cmd,
                        error,
                    ),
                )
                aggregate.write(f"{target_id},{model_name},{status},{count_ranks(model_out)},{log_file},{error}\n")
                if status != "success":
                    failures += 1
                    print(f"[failed] {target_id} {model_name}: {error}", file=sys.stderr)
                    if args.fail_fast:
                        raise SystemExit(1)
                else:
                    print(f"[done] {target_id} {model_name}: {count_ranks(model_out)} ranks")

    print(f"Benchmark run log: {run_log}")
    if not args.dry_run:
        print(f"Run timing metadata: {run_metadata}")
    if failures:
        print(f"Completed with {failures} model failure(s).")


if __name__ == "__main__":
    main()
