#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path


MODELS = ["esmfold", "omegafold", "boltz2", "chai1", "colabfold", "openfold", "protenix", "openfold3", "af2"]

SOURCE_PRIORITIES = {
    "esmfold": ["results/default_modes_first5_carbon_metadata", "results/six_backend_first5_carbon_smoke"],
    "omegafold": ["results/default_modes_first5_carbon_metadata", "results/six_backend_first5_carbon_smoke"],
    "boltz2": ["results/default_modes_first5_carbon_metadata", "results/six_backend_first5_carbon_smoke"],
    "chai1": ["results/default_modes_first5_carbon_metadata", "results/six_backend_first5_carbon_smoke"],
    "colabfold": ["results/four_msa_models_shared_msa_first5", "results/default_modes_first5_carbon_metadata"],
    "openfold": ["results/four_msa_models_shared_msa_first5", "results/default_modes_first5_carbon_metadata"],
    "protenix": ["results/four_msa_models_shared_msa_first5", "results/protenix_openfold3_shared_msa_first5"],
    "openfold3": [
        "results/four_msa_models_shared_msa_first5",
        "results/protenix_openfold3_shared_msa_first5",
        "results/openfold3_first5_lowmem_carbon",
    ],
    "af2": ["results/af2_first5_split_carbon"],
}

PREFERRED_SOURCES = [
    "results/default_modes_first5_carbon_metadata",
    "results/four_msa_models_shared_msa_first5",
    "results/protenix_openfold3_shared_msa_first5",
    "results/af2_first5_split_carbon",
    "results/six_backend_first5_carbon_smoke",
    "results/openfold3_first5_lowmem_carbon",
]

METADATA_COLUMNS = [
    "target_id",
    "pdb_id",
    "chain",
    "model",
    "rank",
    "source_result_dir",
    "prediction_pdb",
    "status",
    "success",
    "sequence_length",
    "uses_msa",
    "msa_used",
    "msa_source",
    "msa_mode",
    "msa_reused",
    "msa_database",
    "msa_database_path",
    "shared_msa_metadata_file",
    "shared_msa_dir",
    "shared_msa_a3m_file",
    "msa_generation_included_in_timing",
    "msa_generation_included_in_carbon",
    "msa_feature_runtime_sec",
    "msa_feature_carbon_emissions_g",
    "msa_feature_energy_consumed_kwh",
    "inference_time_sec",
    "model_inference_time_sec",
    "model_carbon_emissions_g",
    "model_energy_consumed_kwh",
    "total_runtime_sec",
    "total_carbon_emissions_g",
    "total_energy_consumed_kwh",
    "carbon_country_iso_code",
    "carbon_intensity_mode",
    "carbon_intensity_g_per_kwh",
    "hardware_gpu_name",
    "hardware_gpu_count",
    "hardware_gpu_memory_mb",
    "runner",
    "environment",
    "notes",
]

SCORE_COLUMNS = [
    "target_id",
    "pdb_id",
    "chain",
    "model",
    "rank",
    "source_result_dir",
    "prediction_pdb",
    "reference_pdb",
    "lddt_ca",
    "ca_rmsd",
    "tmalign_available",
    "tmalign_tm_score_ref",
    "tmalign_tm_score_pred",
    "tmalign_rmsd",
    "tmalign_aligned_length",
    "score_status",
    "score_notes",
]

SUMMARY_COLUMNS = [
    "model",
    "source_result_dir",
    "n_targets",
    "n_success",
    "best_lddt_ca",
    "mean_lddt_ca",
    "median_lddt_ca",
    "mean_ca_rmsd",
    "mean_tmalign_tm_score_ref",
    "mean_model_inference_time_sec",
    "mean_total_runtime_sec",
    "mean_total_carbon_emissions_g",
    "mean_model_carbon_emissions_g",
    "uses_msa",
    "msa_mode",
    "msa_reused",
    "notes",
]

MANIFEST_COLUMNS = [
    "path",
    "kind",
    "model",
    "target_id",
    "selected_for_consolidation",
    "source_result_dir",
    "cleanup_action",
    "cleanup_reason",
    "safe_to_remove",
]

KEEP_RESULT_DIRS = {
    "results/consolidated",
    "results/readme_tables",
    "results/default_modes_first5_carbon_metadata",
    "results/four_msa_models_shared_msa_first5",
    "results/protenix_openfold3_shared_msa_first5",
    "results/af2_first5_split_carbon",
    "results/six_backend_first5_carbon_smoke",
    "results/shared_msa_colabfold_first5",
    "results/colabfold_single_vs_msa_first5_carbon",
    "results/openfold_single_vs_msa_first5_carbon",
}

ARCHIVE_RESULT_DIRS = {
    "results/backend_smoke",
    "results/real_backend_smoke",
    "results/msa_mode_smoke",
    "results/timing_smoke",
    "results/shared_msa_colabfold_7ROA",
    "results/carbon_test",
    "results/carbon_smoke_one_target",
    "results/carbon_country_override_che_smoke",
    "results/default_modes_one_target_carbon_metadata_smoke",
    "results/af2_one_target_split_carbon",
    "results/four_backend_first5_real_smoke",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "success", "completed"}


def as_float(value: object) -> float | None:
    try:
        text = str(value).strip()
        if text == "":
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}"


def median(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def rank_text(value: object) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return "1"


def load_targets(path: Path) -> dict[str, dict[str, str]]:
    targets: dict[str, dict[str, str]] = {}
    for row in read_csv(path):
        sequence = "".join((row.get("sequence") or "").split())
        notes = row.get("notes") or ""
        length = len(sequence) if sequence else ""
        match = re.search(r"target_length=([0-9]+)", notes)
        if match:
            length = match.group(1)
        targets[row.get("target_id", "")] = {
            "pdb_id": row.get("pdb_id", ""),
            "chain": row.get("chain_id", row.get("chain", "")),
            "sequence_length": str(length),
            "reference_pdb": row.get("reference_pdb", ""),
            "notes": notes,
        }
    return targets


def load_status(source: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_csv(source / "run_status.csv")
    return {(row.get("target_id", ""), row.get("model", "")): row for row in rows}


def load_score_rows(source: Path) -> dict[tuple[str, str, str], dict[str, str]]:
    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    for score_file in sorted((source / "scores").glob("*_scores.csv")):
        for row in read_csv(score_file):
            key = (row.get("target_id", ""), row.get("model", ""), rank_text(row.get("rank")))
            rows[key] = row
    return rows


def load_shared_summary(source: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_csv(source / "shared_msa_score_cost_summary.csv")
    return {(row.get("target_id", ""), row.get("model", "")): row for row in rows}


def load_shared_msa_metadata(source: Path) -> dict[str, dict[str, str]]:
    rows = read_csv(source / "shared_msa_metadata.csv")
    return {row.get("target_id", ""): row for row in rows}


def model_notes(model: str, meta: dict[str, object]) -> str:
    notes = []
    if model in {"colabfold", "openfold", "protenix", "openfold3"} and str(meta.get("msa_reused", "")).lower() == "true":
        notes.append("shared ColabFold/MMseqs2 MSA")
    if model == "openfold3":
        notes.append("OpenFold3 experimental backend")
    if model == "af2":
        notes.append("official AlphaFold2 split MSA/features and inference")
    raw = str(meta.get("notes", "")).strip()
    if raw:
        notes.append(raw)
    return "; ".join(dict.fromkeys(notes))


def metadata_from_run_row(
    source: Path,
    row: dict[str, str],
    status_row: dict[str, str],
    target: dict[str, str],
    shared_summary: dict[str, str] | None,
    shared_msa: dict[str, str] | None,
) -> dict[str, object]:
    model = row.get("model", "")
    success = truthy(row.get("success"))
    inference_time = as_float(row.get("inference_time_sec"))
    carbon_g = as_float(row.get("carbon_emissions_g"))
    energy_kwh = as_float(row.get("carbon_energy_consumed_kwh"))

    msa_feature_runtime = as_float(row.get("msa_feature_runtime_sec"))
    msa_feature_carbon = as_float(row.get("msa_feature_carbon_emissions_g"))
    msa_feature_energy = as_float(row.get("msa_feature_energy_consumed_kwh"))
    model_inference = as_float(row.get("af2_inference_runtime_sec"))
    model_carbon = as_float(row.get("af2_inference_carbon_emissions_g"))
    model_energy = as_float(row.get("af2_inference_energy_consumed_kwh"))
    total_runtime = as_float(row.get("total_runtime_sec"))
    total_carbon = as_float(row.get("total_carbon_emissions_g"))
    total_energy = as_float(row.get("total_energy_consumed_kwh"))

    if shared_summary:
        msa_feature_runtime = as_float(shared_summary.get("msa_runtime_sec"))
        msa_feature_carbon = as_float(shared_summary.get("msa_carbon_emissions_g"))
        model_inference = as_float(shared_summary.get("model_inference_time_sec"))
        model_carbon = as_float(shared_summary.get("model_carbon_emissions_g"))
        total_runtime = as_float(shared_summary.get("total_time_with_shared_msa_sec"))
        total_carbon = as_float(shared_summary.get("total_carbon_with_shared_msa_g"))
        model_energy = energy_kwh
    elif total_runtime is None:
        total_runtime = inference_time
        total_carbon = carbon_g
        total_energy = energy_kwh
        model_inference = inference_time
        model_carbon = carbon_g
        model_energy = energy_kwh

    shared_dir = ""
    shared_a3m = ""
    shared_file = ""
    if shared_msa:
        shared_file = str(source / "shared_msa_metadata.csv")
        shared_dir = shared_msa.get("msa_dir", shared_msa.get("shared_msa_dir", ""))
        shared_a3m = shared_msa.get("a3m_file", shared_msa.get("shared_msa_a3m_file", ""))

    output_pdb = row.get("output_pdb", "")
    notes = row.get("msa_notes", "")
    out = {
        "target_id": row.get("target_id", ""),
        "pdb_id": row.get("pdb_id", target.get("pdb_id", "")),
        "chain": row.get("chain_id", target.get("chain", "")),
        "model": model,
        "rank": rank_text(row.get("rank")),
        "source_result_dir": str(source),
        "prediction_pdb": output_pdb,
        "status": status_row.get("status", "success" if success else "failed"),
        "success": str(success).lower(),
        "sequence_length": target.get("sequence_length", ""),
        "uses_msa": row.get("msa_used", ""),
        "msa_used": row.get("msa_used", ""),
        "msa_source": row.get("msa_source", ""),
        "msa_mode": row.get("msa_mode", ""),
        "msa_reused": row.get("msa_reused", ""),
        "msa_database": row.get("msa_database", ""),
        "msa_database_path": row.get("msa_database_path", ""),
        "shared_msa_metadata_file": shared_file,
        "shared_msa_dir": shared_dir,
        "shared_msa_a3m_file": shared_a3m,
        "msa_generation_included_in_timing": row.get("msa_generation_included_in_timing", ""),
        "msa_generation_included_in_carbon": row.get("msa_generation_included_in_carbon", ""),
        "msa_feature_runtime_sec": fmt(msa_feature_runtime),
        "msa_feature_carbon_emissions_g": fmt(msa_feature_carbon),
        "msa_feature_energy_consumed_kwh": fmt(msa_feature_energy),
        "inference_time_sec": fmt(inference_time),
        "model_inference_time_sec": fmt(model_inference),
        "model_carbon_emissions_g": fmt(model_carbon),
        "model_energy_consumed_kwh": fmt(model_energy),
        "total_runtime_sec": fmt(total_runtime),
        "total_carbon_emissions_g": fmt(total_carbon),
        "total_energy_consumed_kwh": fmt(total_energy),
        "carbon_country_iso_code": row.get("carbon_country_iso_code", ""),
        "carbon_intensity_mode": row.get("carbon_intensity_mode", ""),
        "carbon_intensity_g_per_kwh": row.get("carbon_intensity_g_per_kwh", ""),
        "hardware_gpu_name": "NVIDIA RTX A5000",
        "hardware_gpu_count": "3",
        "hardware_gpu_memory_mb": "24564",
        "runner": runner_name(row.get("command", "")),
        "environment": environment_name(row.get("command", ""), model),
        "notes": notes,
    }
    out["notes"] = model_notes(model, out)
    return out


def runner_name(command: str) -> str:
    match = re.search(r"bash\s+(runners/[^ ]+)", command)
    return match.group(1) if match else ""


def environment_name(command: str, model: str) -> str:
    known = {
        "esmfold": "esmfold",
        "omegafold": "omegafold",
        "boltz2": "boltz",
        "chai1": "chai1",
        "colabfold": "colabfold",
        "openfold": "openfold",
        "protenix": "protenix",
        "openfold3": "openfold3",
        "af2": "alphafold2",
    }
    if "conda run -n" in command:
        match = re.search(r"conda run -n ([^ ]+)", command)
        if match:
            return match.group(1)
    return known.get(model, "")


def score_from_row(source: Path, score: dict[str, str], meta: dict[str, object], target: dict[str, str]) -> dict[str, object]:
    status = score.get("score_status", "")
    notes = score.get("error", "") or score.get("score_notes", "")
    if not status:
        status = "success" if not notes else "failed"
    return {
        "target_id": score.get("target_id", meta.get("target_id", "")),
        "pdb_id": score.get("pdb_id", meta.get("pdb_id", "")),
        "chain": score.get("chain", score.get("chain_id", meta.get("chain", ""))),
        "model": score.get("model", meta.get("model", "")),
        "rank": rank_text(score.get("rank", meta.get("rank", ""))),
        "source_result_dir": str(source),
        "prediction_pdb": score.get("prediction_pdb", score.get("output_pdb", meta.get("prediction_pdb", ""))),
        "reference_pdb": score.get("reference_pdb", target.get("reference_pdb", "")),
        "lddt_ca": score.get("lddt_ca", ""),
        "ca_rmsd": score.get("ca_rmsd", ""),
        "tmalign_available": score.get("tmalign_available", ""),
        "tmalign_tm_score_ref": score.get("tmalign_tm_score_ref", ""),
        "tmalign_tm_score_pred": score.get("tmalign_tm_score_pred", ""),
        "tmalign_rmsd": score.get("tmalign_rmsd", ""),
        "tmalign_aligned_length": score.get("tmalign_aligned_length", ""),
        "score_status": status,
        "score_notes": notes,
    }


def collect(args: argparse.Namespace) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    targets = load_targets(Path(args.targets))
    selected_meta: dict[tuple[str, str, str], dict[str, object]] = {}
    selected_score: dict[tuple[str, str, str], dict[str, object]] = {}
    selected_source: dict[tuple[str, str, str], Path] = {}
    manifest: list[dict[str, object]] = []

    for model in MODELS:
        for source_name in SOURCE_PRIORITIES[model]:
            source = Path(source_name)
            run_rows = [row for row in read_csv(source / "run_metadata.csv") if row.get("model") == model]
            if not run_rows:
                continue
            status = load_status(source)
            scores = load_score_rows(source)
            shared_summary = load_shared_summary(source)
            shared_msa = load_shared_msa_metadata(source)
            selected_count = 0
            for row in run_rows:
                key = (row.get("target_id", ""), model, rank_text(row.get("rank")))
                if key in selected_meta:
                    continue
                target = targets.get(row.get("target_id", ""), {})
                meta = metadata_from_run_row(
                    source,
                    row,
                    status.get((row.get("target_id", ""), model), {}),
                    target,
                    shared_summary.get((row.get("target_id", ""), model)),
                    shared_msa.get(row.get("target_id", "")),
                )
                selected_meta[key] = meta
                selected_source[key] = source
                selected_count += 1
                score = scores.get(key)
                if score:
                    selected_score[key] = score_from_row(source, score, meta, target)
            add_source_manifest(manifest, source, model, selected_count > 0)

    for source_name in PREFERRED_SOURCES:
        add_source_manifest(manifest, Path(source_name), "", False)
    add_cleanup_manifest(manifest)

    meta_rows = sorted(selected_meta.values(), key=lambda r: (str(r.get("model")), str(r.get("target_id")), str(r.get("rank"))))
    score_rows = sorted(selected_score.values(), key=lambda r: (str(r.get("model")), str(r.get("target_id")), str(r.get("rank"))))
    summary_rows = summarize(meta_rows, score_rows)
    return meta_rows, score_rows, summary_rows, manifest


def add_source_manifest(manifest: list[dict[str, object]], source: Path, model: str, selected: bool) -> None:
    if not source.exists():
        return
    files = [
        source / "run_metadata.csv",
        source / "run_status.csv",
        source / "shared_msa_metadata.csv",
        source / "shared_msa_score_cost_summary.csv",
        source / "af2_stage_metadata.csv",
    ]
    files.extend(sorted((source / "scores").glob("*_scores.csv")))
    for path in files:
        if path.exists():
            manifest.append(
                {
                    "path": str(path),
                    "kind": "source_file",
                    "model": model,
                    "target_id": "",
                    "selected_for_consolidation": str(selected).lower(),
                    "source_result_dir": str(source),
                    "cleanup_action": "keep",
                    "cleanup_reason": "source file for consolidated benchmark" if selected else "preferred source retained for traceability",
                    "safe_to_remove": "false",
                }
            )


def add_cleanup_manifest(manifest: list[dict[str, object]]) -> None:
    results = Path("results")
    if not results.exists():
        return
    seen = {row["path"] for row in manifest}
    for path in sorted(p for p in results.iterdir() if p.is_dir()):
        path_text = str(path)
        if path_text in seen:
            continue
        if path_text.startswith("results/_archived_test_artifacts_"):
            continue
        if path_text in ARCHIVE_RESULT_DIRS:
            action = "archive"
            reason = "test-only or superseded smoke artifact; consolidated files preserve benchmark data"
            safe = "true"
        elif path_text in KEEP_RESULT_DIRS:
            action = "keep"
            reason = "canonical source, documentation table source, or documented ablation source"
            safe = "false"
        else:
            action = "review"
            reason = "not classified automatically"
            safe = "false"
        manifest.append(
            {
                "path": path_text,
                "kind": "result_dir",
                "model": "",
                "target_id": "",
                "selected_for_consolidation": "false",
                "source_result_dir": path_text,
                "cleanup_action": action,
                "cleanup_reason": reason,
                "safe_to_remove": safe,
            }
        )


def summarize(meta_rows: list[dict[str, object]], score_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    metas_by_model: dict[str, list[dict[str, object]]] = defaultdict(list)
    scores_by_model: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in meta_rows:
        metas_by_model[str(row.get("model", ""))].append(row)
    for row in score_rows:
        scores_by_model[str(row.get("model", ""))].append(row)

    rows = []
    for model in MODELS:
        metas = metas_by_model.get(model, [])
        scores = scores_by_model.get(model, [])
        lddt = [v for v in (as_float(row.get("lddt_ca")) for row in scores) if v is not None]
        rmsd = [v for v in (as_float(row.get("ca_rmsd")) for row in scores) if v is not None]
        tm_ref = [v for v in (as_float(row.get("tmalign_tm_score_ref")) for row in scores) if v is not None]
        model_time = [v for v in (as_float(row.get("model_inference_time_sec")) for row in metas) if v is not None]
        total_time = [v for v in (as_float(row.get("total_runtime_sec")) for row in metas) if v is not None]
        total_carbon = [v for v in (as_float(row.get("total_carbon_emissions_g")) for row in metas) if v is not None]
        model_carbon = [v for v in (as_float(row.get("model_carbon_emissions_g")) for row in metas) if v is not None]
        rows.append(
            {
                "model": model,
                "source_result_dir": ";".join(sorted({str(row.get("source_result_dir", "")) for row in metas if row.get("source_result_dir")})),
                "n_targets": len({row.get("target_id") for row in scores}),
                "n_success": sum(1 for row in scores if str(row.get("score_status", "")).lower() in {"", "success"}),
                "best_lddt_ca": fmt(max(lddt) if lddt else None),
                "mean_lddt_ca": fmt(mean(lddt)),
                "median_lddt_ca": fmt(median(lddt)),
                "mean_ca_rmsd": fmt(mean(rmsd)),
                "mean_tmalign_tm_score_ref": fmt(mean(tm_ref)),
                "mean_model_inference_time_sec": fmt(mean(model_time)),
                "mean_total_runtime_sec": fmt(mean(total_time)),
                "mean_total_carbon_emissions_g": fmt(mean(total_carbon)),
                "mean_model_carbon_emissions_g": fmt(mean(model_carbon)),
                "uses_msa": ";".join(sorted({str(row.get("uses_msa", "")) for row in metas if row.get("uses_msa") != ""})),
                "msa_mode": ";".join(sorted({str(row.get("msa_mode", "")) for row in metas if row.get("msa_mode")})),
                "msa_reused": ";".join(sorted({str(row.get("msa_reused", "")) for row in metas if row.get("msa_reused") != ""})),
                "notes": "; ".join(sorted({str(row.get("notes", "")) for row in metas if row.get("notes")})),
            }
        )
    return rows


def write_notes(path: Path, meta_rows: list[dict[str, object]], score_rows: list[dict[str, object]], summary_rows: list[dict[str, object]]) -> None:
    source_dirs = sorted({str(row.get("source_result_dir", "")) for row in meta_rows if row.get("source_result_dir")})
    lines = [
        "# Consolidated Protein Folding Benchmark Notes",
        "",
        "This collection consolidates the latest first-five benchmark outputs for all currently reported models.",
        "",
        "## Source Selection",
        "",
    ]
    lines.extend(f"- {source}" for source in source_dirs)
    lines.extend(
        [
            "",
            "Single-target smoke-test folders were not selected as benchmark sources. They are listed in the cleanup manifest for archival when they are superseded by first-five runs.",
            "",
            "## MSA Accounting",
            "",
            "ColabFold, OpenFold, Protenix, and OpenFold3 use the shared ColabFold/MMseqs2 MSA source in this consolidated table when those shared-MSA first-five rows are available.",
            "Default single-sequence models record `msa_used=false`. AF2 records split MSA/features and inference timing fields from the official AlphaFold2 pipeline.",
            "",
            "## Experimental Caveats",
            "",
            "OpenFold3 is retained as an experimental backend. Its rows are useful for tracking runtime and carbon behavior, but should be interpreted separately from production-stable runners.",
            "",
            "## Coverage",
            "",
            f"- Metadata rows: {len(meta_rows)}",
            f"- Score rows: {len(score_rows)}",
            f"- Models: {', '.join(row['model'] for row in summary_rows)}",
        ]
    )
    path.write_text("\n".join(lines) + "\n")


def copy_to_carbon4science(out_dir: Path, carbon_results: Path) -> None:
    carbon_results.mkdir(parents=True, exist_ok=True)
    for name in [
        "benchmark_metadata_all_models.csv",
        "benchmark_scores_all_models.csv",
        "benchmark_model_summary_all_models.csv",
        "benchmark_collection_manifest.csv",
    ]:
        shutil.copy2(out_dir / name, carbon_results / name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate first-five protein folding benchmark outputs.")
    parser.add_argument("--targets", default="data/targets/targets_first5.csv")
    parser.add_argument("--output-dir", default="results/consolidated")
    parser.add_argument("--copy-to-carbon4science", action="store_true")
    parser.add_argument("--carbon-results-dir", default="/home/chen/projects/carbon4science.github.io/results")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    meta_rows, score_rows, summary_rows, manifest = collect(args)
    write_csv(out_dir / "benchmark_metadata_all_models.csv", METADATA_COLUMNS, meta_rows)
    write_csv(out_dir / "benchmark_scores_all_models.csv", SCORE_COLUMNS, score_rows)
    write_csv(out_dir / "benchmark_model_summary_all_models.csv", SUMMARY_COLUMNS, summary_rows)
    write_csv(out_dir / "benchmark_collection_manifest.csv", MANIFEST_COLUMNS, manifest)
    write_csv(out_dir / "test_artifact_cleanup_manifest.csv", MANIFEST_COLUMNS, manifest)
    write_notes(out_dir / "benchmark_collection_notes.md", meta_rows, score_rows, summary_rows)

    if args.copy_to_carbon4science:
        copy_to_carbon4science(out_dir, Path(args.carbon_results_dir))

    print(f"Wrote {len(meta_rows)} metadata rows")
    print(f"Wrote {len(score_rows)} score rows")
    print(f"Wrote {len(summary_rows)} model summary rows")
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
