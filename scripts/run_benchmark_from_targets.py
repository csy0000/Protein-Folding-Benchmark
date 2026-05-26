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

from carbon_tracking import CARBON_METADATA_COLUMNS, CarbonRunTracker, empty_carbon_metadata
from msa_metadata import MSA_METADATA_COLUMNS, infer_msa_metadata, shared_msa_metadata


SINGLE_OUTPUT_MODELS = {"esmfold", "omegafold", "openfold", "openfold_single", "openfold_msa"}
MODEL_ORDER_PRIORITY = ["colabfold", "colabfold_single", "colabfold_msa", "openfold", "openfold_single", "openfold_msa", "af2"]

GPU_DEFAULT_ENV = {
    "af2": {"AF2_CARBON_COUNTRY_ISO_CODE": "WORLD"},
    "boltz2": {"BOLTZ_ACCELERATOR": "gpu"},
    "chai1": {"CHAI1_DEVICE": "cuda:0"},
    "esmfold": {"ESMFOLD_CPU_ONLY": "0"},
    "openfold": {"OPENFOLD_DEVICE": "cuda:0"},
    "openfold_single": {"OPENFOLD_DEVICE": "cuda:0"},
    "openfold_msa": {"OPENFOLD_DEVICE": "cuda:0"},
}

CONSERVATIVE_GPU_ENV = {
    "XLA_PYTHON_CLIENT_PREALLOCATE": "false",
    "TF_FORCE_GPU_ALLOW_GROWTH": "true",
}

RUNNER_METADATA_COLUMNS = [
    "msa_feature_runtime_sec",
    "msa_feature_carbon_emissions_g",
    "msa_feature_energy_consumed_kwh",
    "af2_inference_runtime_sec",
    "af2_inference_carbon_emissions_g",
    "af2_inference_energy_consumed_kwh",
    "total_runtime_sec",
    "total_carbon_emissions_g",
    "total_energy_consumed_kwh",
    "af2_db_preset",
    "af2_model_preset",
    "af2_params_dir",
    "af2_data_dir",
    "af2_features_dir",
]


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


def order_models(models: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    priority = {name: index for index, name in enumerate(MODEL_ORDER_PRIORITY)}
    original_order = {name: index for index, name in enumerate(models)}
    return dict(
        sorted(
            models.items(),
            key=lambda item: (priority.get(item[0], len(priority)), original_order[item[0]]),
        )
    )


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
    trials_run: int,
    max_trials: int,
    successful_trial: int | str,
    error: str = "",
    msa_metadata: dict[str, str] | None = None,
    runner_metadata: dict[str, object] | None = None,
) -> None:
    metadata = {
        "target_id": target_id,
        "model": model,
        "requested_top_k": top_k,
        "available_top_k": count_ranks(model_out),
        "mode": mode,
        "status": status,
        "log_file": str(log_file),
        "trials_run": trials_run,
        "max_trials": max_trials,
        "successful_trial": successful_trial,
        "notes": top_k_note(model),
        "error": error,
    }
    if msa_metadata:
        metadata.update({key: value for key, value in msa_metadata.items() if key.startswith("msa_") or key.startswith("shared_msa_")})
    if runner_metadata:
        metadata.update({key: value for key, value in runner_metadata.items() if key in RUNNER_METADATA_COLUMNS})
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
    "trials_run",
    "max_trials",
    "successful_trial",
    "command",
    "error_message",
    *MSA_METADATA_COLUMNS,
    *RUNNER_METADATA_COLUMNS,
    *CARBON_METADATA_COLUMNS,
]

RUN_STATUS_COLUMNS = [
    "target_id",
    "pdb_id",
    "chain",
    "model",
    "status",
    "exit_code",
    "runtime_sec",
    "log_file",
    "reason",
]


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


def append_run_status_row(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RUN_STATUS_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in RUN_STATUS_COLUMNS})


def timing_rows_for_run(
    target: dict[str, str],
    model: str,
    model_out: Path,
    success: bool,
    return_code: int,
    inference_time_sec: float,
    trials_run: int,
    max_trials: int,
    successful_trial: int | str,
    command: list[str],
    error_message: str,
    carbon_metadata: dict[str, object] | None = None,
    msa_metadata: dict[str, object] | None = None,
    runner_metadata: dict[str, object] | None = None,
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
        "trials_run": trials_run,
        "max_trials": max_trials,
        "successful_trial": successful_trial,
        "command": " ".join(shlex.quote(part) for part in command),
        "error_message": error_message,
    }
    if msa_metadata is None:
        msa_metadata = {column: "" for column in MSA_METADATA_COLUMNS}
    base.update(msa_metadata)
    if runner_metadata is None:
        runner_metadata = {column: "" for column in RUNNER_METADATA_COLUMNS}
    base.update({column: runner_metadata.get(column, "") for column in RUNNER_METADATA_COLUMNS})
    if carbon_metadata is None:
        carbon_metadata = empty_carbon_metadata(False)
    base.update(carbon_metadata)
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



def load_shared_msa_metadata(path: Path) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    if not path.exists():
        raise SystemExit(f"Shared MSA metadata file does not exist: {path}")
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if "target_id" not in (reader.fieldnames or []):
            raise SystemExit(f"Shared MSA metadata is missing target_id column: {path}")
        return {row.get("target_id", ""): row for row in reader}


def uses_shared_msa(model_cfg: dict[str, object]) -> bool:
    value = model_cfg.get("use_shared_msa", False)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def target_shared_msa_row(
    target_id: str,
    shared_rows: dict[str, dict[str, str]],
    shared_root: Path,
) -> tuple[dict[str, str], Path, Path]:
    row = shared_rows.get(target_id)
    if not row:
        raise SystemExit(f"No shared MSA metadata row for target_id={target_id}")
    msa_dir = Path(row.get("msa_dir") or shared_root / target_id)
    a3m_file = Path(row.get("a3m_file") or msa_dir / f"{target_id}.a3m")
    if not a3m_file.exists():
        raise SystemExit(f"Shared MSA A3M does not exist for {target_id}: {a3m_file}")
    return row, msa_dir, a3m_file


def load_runner_metadata(model_out: Path) -> dict[str, object]:
    metadata_path = model_out / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        with metadata_path.open() as f:
            metadata = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"runner_metadata_error": repr(exc)}
    return {column: metadata.get(column, "") for column in RUNNER_METADATA_COLUMNS}


def run_status_row_for_run(
    target: dict[str, str],
    model: str,
    status: str,
    return_code: int,
    inference_time_sec: float,
    log_file: Path,
    error_message: str,
) -> dict[str, object]:
    return {
        "target_id": target.get("target_id", ""),
        "pdb_id": target.get("pdb_id", ""),
        "chain": target.get("chain_id", ""),
        "model": model,
        "status": status,
        "exit_code": return_code,
        "runtime_sec": f"{inference_time_sec:.6f}",
        "log_file": str(log_file),
        "reason": error_message,
    }


def run_one(
    runner: str,
    fasta: Path,
    model_out: Path,
    top_k: int,
    log_file: Path,
    env: dict[str, str],
    trial: int,
    max_trials: int,
) -> tuple[str, str, int, float, list[str]]:
    cmd = shlex.split(runner) + [str(fasta), str(model_out), str(top_k)]
    start = time.perf_counter()
    with log_file.open("a") as log:
        log.write(f"[trial {trial}/{max_trials}]\n")
        log.write("$ " + " ".join(shlex.quote(part) for part in cmd) + "\n\n")
        completed = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, text=True, check=False, env=env)
        log.write(f"\n[trial {trial}/{max_trials} exit_code={completed.returncode}]\n")
    inference_time_sec = time.perf_counter() - start
    if completed.returncode == 0:
        return "success", "", completed.returncode, inference_time_sec, cmd
    return "failed", f"exit code {completed.returncode}; see {log_file}", completed.returncode, inference_time_sec, cmd


def run_with_retries(
    runner: str,
    fasta: Path,
    model_out: Path,
    top_k: int,
    log_file: Path,
    env: dict[str, str],
    max_trials: int,
) -> tuple[str, str, int, float, int, int | str, list[str]]:
    log_file.write_text("")
    total_elapsed = 0.0
    final_status = "failed"
    final_error = ""
    final_return_code = 1
    final_cmd: list[str] = []
    for trial in range(1, max_trials + 1):
        status, error, return_code, elapsed, cmd = run_one(
            runner,
            fasta,
            model_out,
            top_k,
            log_file,
            env,
            trial,
            max_trials,
        )
        total_elapsed += elapsed
        final_status = status
        final_error = error
        final_return_code = return_code
        final_cmd = cmd
        if status == "success":
            return status, error, return_code, total_elapsed, trial, trial, cmd
    return final_status, final_error, final_return_code, total_elapsed, max_trials, "", final_cmd


def apply_gpu_defaults(model: str, env: dict[str, str]) -> None:
    for key, value in CONSERVATIVE_GPU_ENV.items():
        env.setdefault(key, value)
    for key, value in GPU_DEFAULT_ENV.get(model, {}).items():
        env.setdefault(key, value)


def post_model_gpu_cleanup(sleep_sec: float, aggregate, target_id: str, model: str) -> None:
    if sleep_sec <= 0:
        return
    aggregate.write(f"[gpu-cleanup] {target_id},{model},sleep_sec={sleep_sec:g}\n")
    aggregate.flush()
    time.sleep(sleep_sec)


def run_mock(
    target: dict[str, str],
    model_out: Path,
    log_file: Path,
    sleep_sec: float,
) -> tuple[str, str, int, float, list[str]]:
    cmd = ["mock-runner", target["target_id"], str(model_out), str(sleep_sec)]
    start = time.perf_counter()
    time.sleep(max(0.0, sleep_sec))
    model_out.mkdir(parents=True, exist_ok=True)
    for old_rank in model_out.glob("rank_*.pdb"):
        old_rank.unlink()
    reference = Path(target.get("reference_pdb", ""))
    with log_file.open("a") as log:
        log.write("$ " + " ".join(shlex.quote(part) for part in cmd) + "\n\n")
        if not reference.exists():
            elapsed = time.perf_counter() - start
            log.write(f"Missing mock reference: {reference}\n")
            return "failed", f"missing mock reference: {reference}", 1, elapsed, cmd
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
    return "success", "", 0, elapsed, cmd


def run_mock_with_retries(
    target: dict[str, str],
    model_out: Path,
    log_file: Path,
    sleep_sec: float,
    max_trials: int,
) -> tuple[str, str, int, float, int, int | str, list[str]]:
    log_file.write_text("")
    total_elapsed = 0.0
    final_status = "failed"
    final_error = ""
    final_return_code = 1
    final_cmd: list[str] = []
    for trial in range(1, max_trials + 1):
        with log_file.open("a") as log:
            log.write(f"[trial {trial}/{max_trials}]\n")
        status, error, return_code, elapsed, cmd = run_mock(target, model_out, log_file, sleep_sec)
        with log_file.open("a") as log:
            log.write(f"\n[trial {trial}/{max_trials} exit_code={return_code}]\n")
        total_elapsed += elapsed
        final_status = status
        final_error = error
        final_return_code = return_code
        final_cmd = cmd
        if status == "success":
            return status, error, return_code, total_elapsed, trial, trial, cmd
    return final_status, final_error, final_return_code, total_elapsed, max_trials, "", final_cmd


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
    parser.add_argument("--run-status", default="", help="Compact run status CSV. Defaults to data/run_status.csv.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--max-trials", type=int, default=5, help="Maximum run attempts per target/model before marking it failed.")
    parser.add_argument(
        "--gpu-cleanup-sleep-sec",
        type=float,
        default=5.0,
        help="Cooldown after each target/model run so exited CUDA/JAX/PyTorch processes can release GPU memory. Set 0 to disable.",
    )
    parser.add_argument("--mock-runner", action="store_true", help="Write mock rank_001 predictions from references to test timing plumbing.")
    parser.add_argument("--mock-sleep-sec", type=float, default=0.05)
    parser.add_argument(
        "--openfold-mode",
        choices=["single_sequence", "msa", "config"],
        default="config",
        help="Use config by default. Set single_sequence for explicit OpenFold no-MSA smoke runs, or msa for native OpenFold database mode.",
    )
    parser.add_argument("--track-carbon", action="store_true", help="Track per-target/model emissions with CodeCarbon.")
    parser.add_argument("--carbon-country-iso-code", default="WORLD", help="Country ISO code for CodeCarbon offline tracking, or WORLD for benchmark world-average carbon intensity.")
    parser.add_argument(
        "--carbon-output-dir",
        default="",
        help="Directory for raw CodeCarbon CSVs. Defaults to <results-dir>/carbon.",
    )
    parser.add_argument("--carbon-project-name", default="protein_folding_benchmark")
    parser.add_argument("--carbon-measure-power-secs", type=float, default=1.0)
    parser.add_argument("--shared-msa-metadata", default="", help="Shared MSA metadata CSV generated by generate_colabfold_msas_from_targets.py.")
    parser.add_argument("--shared-msa-root", default="", help="Root directory containing per-target shared MSA directories.")
    args = parser.parse_args()
    if args.max_trials < 1:
        raise SystemExit("--max-trials must be at least 1")
    if args.gpu_cleanup_sleep_sec < 0:
        raise SystemExit("--gpu-cleanup-sleep-sec must be non-negative")
    if args.carbon_measure_power_secs <= 0:
        raise SystemExit("--carbon-measure-power-secs must be positive")

    targets = load_targets(Path(args.targets))
    models = order_models(enabled_models(Path(args.config), args.models))
    logs_dir = Path(args.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_log = logs_dir / f"{datetime.now():%Y%m%d}_run_benchmark_from_targets.log"
    run_metadata = Path(args.run_metadata) if args.run_metadata else Path(args.results_dir) / "run_metadata.csv"
    run_status = Path(args.run_status) if args.run_status else Path("data/run_status.csv")
    carbon_output_dir = Path(args.carbon_output_dir) if args.carbon_output_dir else Path(args.results_dir) / "carbon"
    shared_msa_metadata_path = Path(args.shared_msa_metadata) if args.shared_msa_metadata else None
    shared_msa_root = Path(args.shared_msa_root) if args.shared_msa_root else Path("")
    shared_msa_rows = load_shared_msa_metadata(shared_msa_metadata_path) if shared_msa_metadata_path else {}
    if not args.dry_run and run_metadata.exists():
        run_metadata.unlink()
    if not args.dry_run and run_status.exists():
        run_status.unlink()

    failures = 0
    with run_log.open("w") as aggregate:
        aggregate.write(
            f"targets={args.targets}\n"
            f"models={','.join(models)}\n"
            f"model_order_priority={','.join(MODEL_ORDER_PRIORITY)}\n"
            f"top_k={args.top_k}\n"
            f"max_trials={args.max_trials}\n"
            f"gpu_cleanup_sleep_sec={args.gpu_cleanup_sleep_sec:g}\n"
            f"run_metadata={run_metadata}\n"
            f"run_status={run_status}\n"
            f"track_carbon={str(bool(args.track_carbon)).lower()}\n"
            f"carbon_country_iso_code={args.carbon_country_iso_code}\n"
            f"carbon_output_dir={carbon_output_dir}\n"
            f"shared_msa_metadata={shared_msa_metadata_path or ''}\n"
            f"shared_msa_root={shared_msa_root if args.shared_msa_root else ''}\n"
            f"carbon_default_note=Use WORLD for benchmark world-average carbon intensity; pass a country code such as CHE to override.\n\n"
        )
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
                msa_metadata = infer_msa_metadata(model_name, model_cfg)
                shared_row: dict[str, str] | None = None
                if shared_msa_rows and uses_shared_msa(model_cfg):
                    shared_row, shared_msa_dir, shared_msa_a3m = target_shared_msa_row(target_id, shared_msa_rows, shared_msa_root)
                    env["SHARED_MSA_METADATA_FILE"] = str(shared_msa_metadata_path)
                    env["SHARED_MSA_DIR"] = str(shared_msa_dir)
                    env["SHARED_MSA_A3M_FILE"] = str(shared_msa_a3m)
                    env["SHARED_MSA_TARGET_ID"] = target_id
                    env["SHARED_MSA_PAIRING_A3M_FILE"] = shared_row.get("pairing_a3m_file", "")
                    env["SHARED_MSA_NON_PAIRING_A3M_FILE"] = shared_row.get("non_pairing_a3m_file", "")
                    msa_metadata = shared_msa_metadata(
                        str(shared_msa_metadata_path),
                        str(shared_msa_dir),
                        str(shared_msa_a3m),
                        shared_row.get("msa_runtime_sec", ""),
                    )
                mode = "default"
                if model_name == "openfold" and args.openfold_mode != "config":
                    env["OPENFOLD_MODE"] = args.openfold_mode
                    mode = args.openfold_mode
                if model_name == "af2":
                    env["AF2_TARGET_PDB_ID"] = target.get("pdb_id", "")
                    env["AF2_TARGET_CHAIN_ID"] = target.get("chain_id", "")
                    env.setdefault("AF2_STAGE_METADATA_CSV", str(Path(args.results_dir) / "af2_stage_metadata.csv"))
                if args.dry_run:
                    cmd = shlex.split(str(model_cfg["runner"])) + [str(fasta), str(model_out), str(args.top_k)]
                    aggregate.write("[dry-run] " + " ".join(shlex.quote(part) for part in cmd) + "\n")
                    print("[dry-run]", " ".join(cmd))
                    continue

                print(f"[run] {target_id} {model_name}")
                carbon_tracker = CarbonRunTracker(
                    enabled=args.track_carbon,
                    output_dir=carbon_output_dir,
                    country_iso_code=args.carbon_country_iso_code,
                    project_name=args.carbon_project_name,
                    measure_power_secs=args.carbon_measure_power_secs,
                    run_label=f"{target_id}_{model_name}",
                )
                carbon_tracker.start()
                if args.mock_runner:
                    status, error, return_code, elapsed, trials_run, successful_trial, cmd = run_mock_with_retries(
                        target,
                        model_out,
                        log_file,
                        args.mock_sleep_sec,
                        args.max_trials,
                    )
                else:
                    status, error, return_code, elapsed, trials_run, successful_trial, cmd = run_with_retries(
                        str(model_cfg["runner"]),
                        fasta,
                        model_out,
                        args.top_k,
                        log_file,
                        env,
                        args.max_trials,
                    )
                carbon_metadata = carbon_tracker.stop()
                runner_metadata = load_runner_metadata(model_out)
                write_prediction_metadata(
                    model_out,
                    target_id,
                    model_name,
                    args.top_k,
                    status,
                    mode,
                    log_file,
                    trials_run,
                    args.max_trials,
                    successful_trial,
                    error,
                    msa_metadata,
                    runner_metadata,
                )
                append_metadata_rows(
                    run_metadata,
                    timing_rows_for_run(
                        target,
                        model_name,
                        model_out,
                        status == "success",
                        return_code,
                        elapsed,
                        trials_run,
                        args.max_trials,
                        successful_trial,
                        cmd,
                        error,
                        carbon_metadata,
                        msa_metadata,
                        runner_metadata,
                    ),
                )
                append_run_status_row(
                    run_status,
                    run_status_row_for_run(
                        target,
                        model_name,
                        status,
                        return_code,
                        elapsed,
                        log_file,
                        error,
                    ),
                )
                aggregate.write(f"{target_id},{model_name},{status},{count_ranks(model_out)},{trials_run},{successful_trial},{log_file},{error}\n")
                post_model_gpu_cleanup(args.gpu_cleanup_sleep_sec, aggregate, target_id, model_name)
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
        print(f"Run status: {run_status}")
    if failures:
        print(f"Completed with {failures} model failure(s).")


if __name__ == "__main__":
    main()
