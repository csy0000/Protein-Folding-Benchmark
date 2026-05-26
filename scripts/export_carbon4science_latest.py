#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_MODELS = ["esmfold", "omegafold", "boltz2", "chai1"]
SHARED_MODELS = ["colabfold", "openfold", "protenix", "openfold3"]
AF2_MODELS = ["af2"]
MODEL_ORDER = DEFAULT_MODELS + SHARED_MODELS + AF2_MODELS


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Missing required CSV: {path}")
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise SystemExit(f"No rows to write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def model_index(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("model", "")].append(row)
    return dict(grouped)


def score_rows_from_score_dir(scores_dir: Path, wanted: set[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(scores_dir.glob("*_scores.csv")):
        for row in read_csv(path):
            if row.get("model") in wanted:
                rows.append(row)
    return rows


def score_lookup(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], dict[str, str]]:
    return {
        (row.get("target_id", ""), row.get("model", ""), row.get("rank", "")): row
        for row in rows
    }


def default_cost_rows(default_metadata: list[dict[str, str]], default_scores: list[dict[str, str]]) -> list[dict[str, str]]:
    scores = score_lookup(default_scores)
    rows: list[dict[str, str]] = []
    for run in default_metadata:
        if run.get("model") not in DEFAULT_MODELS or run.get("success") != "true":
            continue
        score = scores.get((run.get("target_id", ""), run.get("model", ""), run.get("rank", "")), {})
        model_time = run.get("inference_time_sec", "")
        model_carbon = run.get("carbon_emissions_g", "")
        rows.append(
            {
                "target_id": run.get("target_id", ""),
                "model": run.get("model", ""),
                "msa_runtime_sec": "",
                "msa_carbon_emissions_g": "",
                "model_inference_time_sec": model_time,
                "model_carbon_emissions_g": model_carbon,
                "total_time_with_shared_msa_sec": model_time,
                "total_carbon_with_shared_msa_g": model_carbon,
                "lddt_ca": score.get("lddt_ca", ""),
                "ca_rmsd": score.get("ca_rmsd", ""),
                "tmalign_tm_score_ref": score.get("tmalign_tm_score_ref", ""),
            }
        )
    return rows


def af2_cost_rows(af2_metadata: list[dict[str, str]], af2_scores: list[dict[str, str]]) -> list[dict[str, str]]:
    scores = score_lookup(af2_scores)
    rows: list[dict[str, str]] = []
    for run in af2_metadata:
        if run.get("model") not in AF2_MODELS or run.get("success") != "true":
            continue
        score = scores.get((run.get("target_id", ""), run.get("model", ""), run.get("rank", "")), {})
        rows.append(
            {
                "target_id": run.get("target_id", ""),
                "model": run.get("model", ""),
                "msa_runtime_sec": run.get("msa_feature_runtime_sec", ""),
                "msa_carbon_emissions_g": run.get("msa_feature_carbon_emissions_g", ""),
                "model_inference_time_sec": run.get("af2_inference_runtime_sec", ""),
                "model_carbon_emissions_g": run.get("af2_inference_carbon_emissions_g", ""),
                "total_time_with_shared_msa_sec": run.get("total_runtime_sec", ""),
                "total_carbon_with_shared_msa_g": run.get("total_carbon_emissions_g", ""),
                "lddt_ca": score.get("lddt_ca", ""),
                "ca_rmsd": score.get("ca_rmsd", ""),
                "tmalign_tm_score_ref": score.get("tmalign_tm_score_ref", ""),
            }
        )
    return rows


def ordered(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    order = {model: idx for idx, model in enumerate(MODEL_ORDER)}
    return sorted(rows, key=lambda row: (order.get(row.get("model", ""), 999), row.get("target_id", "")))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export latest protein-folding benchmark results for Carbon4Science.")
    parser.add_argument("--shared-source-dir", default="results/four_msa_models_shared_msa_first5")
    parser.add_argument("--default-source-dir", default="results/default_modes_first5_carbon_metadata")
    parser.add_argument("--af2-source-dir", default="results/af2_first5_split_carbon")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    shared_source = Path(args.shared_source_dir)
    default_source = Path(args.default_source_dir)
    af2_source = Path(args.af2_source_dir)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for path in out.iterdir():
        if path.is_file():
            path.unlink()

    shared_score_rows = read_csv(shared_source / "shared_msa_score_cost_summary.csv")
    shared_metadata_rows = read_csv(shared_source / "run_metadata.csv")
    shared_status_rows = read_csv(shared_source / "run_status.csv")
    shared_msa_rows = read_csv(shared_source / "msa" / "msa_metadata.csv")
    shared_aggregate_rows = read_csv(shared_source / "scores" / "all_targets_model_summary.csv")

    default_metadata_all = read_csv(default_source / "run_metadata.csv")
    default_status_all = read_csv(default_source / "run_status.csv")
    default_aggregate_all = read_csv(default_source / "scores" / "all_targets_model_summary.csv")
    default_score_rows_raw = score_rows_from_score_dir(default_source / "scores", set(DEFAULT_MODELS))

    af2_metadata_rows = read_csv(af2_source / "run_metadata.csv")
    af2_status_rows = read_csv(af2_source / "run_status.csv")
    af2_aggregate_rows = read_csv(af2_source / "scores" / "all_targets_model_summary.csv")
    af2_score_rows_raw = score_rows_from_score_dir(af2_source / "scores", set(AF2_MODELS))
    af2_stage_rows = read_csv(af2_source / "af2_stage_metadata.csv")

    default_metadata_rows = [row for row in default_metadata_all if row.get("model") in DEFAULT_MODELS]
    default_status_rows = [row for row in default_status_all if row.get("model") in DEFAULT_MODELS]
    default_aggregate_rows = [row for row in default_aggregate_all if row.get("model") in DEFAULT_MODELS]
    default_score_rows = default_cost_rows(default_metadata_rows, default_score_rows_raw)
    af2_score_rows = af2_cost_rows(af2_metadata_rows, af2_score_rows_raw)

    score_rows = ordered(default_score_rows + [row for row in shared_score_rows if row.get("model") in SHARED_MODELS] + af2_score_rows)
    metadata_rows = ordered(default_metadata_rows + [row for row in shared_metadata_rows if row.get("model") in SHARED_MODELS] + af2_metadata_rows)
    status_rows = ordered(default_status_rows + [row for row in shared_status_rows if row.get("model") in SHARED_MODELS] + af2_status_rows)
    aggregate_rows = default_aggregate_rows + [row for row in shared_aggregate_rows if row.get("model") in SHARED_MODELS] + af2_aggregate_rows

    write_csv(out / "benchmark-score.csv", score_rows)
    write_csv(out / "benchmark-metadata.csv", metadata_rows)

    aggregate_by_model = {row.get("model", ""): row for row in aggregate_rows}
    metadata_by_model = model_index(metadata_rows)
    status_by_model = model_index(status_rows)
    score_by_model = model_index(score_rows)

    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for model in MODEL_ORDER:
        payload = {
            "model": model,
            "benchmark": "default_first5_plus_unified_shared_msa_first5",
            "exported_at_utc": exported_at,
            "source_repository": "/home/chen/projects/Protein-Folding-Benchmark",
            "source_result_dirs": {
                "default_no_msa_models": str(default_source),
                "unified_shared_msa_models": str(shared_source),
                "official_af2_split_stage": str(af2_source),
            },
            "target_set": "data/targets/targets_first5.csv",
            "top_k": 1,
            "msa_policy": (
                "esmfold, omegafold, boltz2, and chai1 use their default/no-MSA benchmark rows; "
                "colabfold, openfold, protenix, and openfold3 use one shared ColabFold/MMseqs2 MSA generated per target; "
                "af2 uses official AlphaFold2 database search with split MSA/features and JAX inference accounting"
            ),
            "aggregate_summary": aggregate_by_model.get(model, {}),
            "per_target_scores": score_by_model.get(model, []),
            "per_target_runtime_metadata": metadata_by_model.get(model, []),
            "per_target_status": status_by_model.get(model, []),
            "shared_msa_metadata": shared_msa_rows if model in SHARED_MODELS else [],
            "af2_stage_metadata": af2_stage_rows if model in AF2_MODELS else [],
        }
        (out / f"{model}.json").write_text(json.dumps(payload, indent=2) + "\n")

    print(f"Wrote Carbon4Science export to {out}")
    print("Files:")
    for path in sorted(out.iterdir()):
        if path.is_file():
            print(path)


if __name__ == "__main__":
    main()
