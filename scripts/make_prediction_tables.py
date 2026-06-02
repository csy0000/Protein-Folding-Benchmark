#!/usr/bin/env python
"""Build readable CASP prediction result tables from manifest metadata and scores."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Iterable

METRICS = ["gdt_ts", "lddt_ca", "tm_score", "rmsd_ca", "gdc_sc", "global_lddt", "molprobity"]
OUTPUT_COLUMNS = [
    "model","domain_id","target_id","casp_round","pdb_id","chain_id","should_use","target_qc_status",
    "qc_reason","reference_coverage","mapping_identity","mapping_coverage","resolved_ca_count",
    "expected_mapped_residue_count","chain_assignment_confidence","target_length","residue_start",
    "residue_end","sequence_start","sequence_end","success","score_success","gdt_ts","lddt_ca",
    "tm_score","rmsd_ca","gdc_sc","global_lddt","molprobity","runtime_sec","carbon_emissions_g",
    "energy_consumed_kwh","input_fasta","output_structure","log_file","error_message","score_error",
]
MODEL_INPUT_MODE = {
    "esmfold": "single-sequence / MSA-free",
    "omegafold": "single-sequence / MSA-free",
    "boltz": "MSA-free workflow",
    "boltz2": "MSA-free workflow",
    "chai1": "MSA-free workflow",
    "af3": "MSA-free or internal pipeline",
    "colabfold": "MSA-based",
    "openfold": "MSA-based",
    "af2": "MSA-based",
    "alphafold2": "MSA-based",
}
ALIASES = {
    "gdt_ts": "gdt_ts", "gdt-ts": "gdt_ts", "gdtts": "gdt_ts",
    "lddt-ca": "lddt_ca", "lddt_ca": "lddt_ca", "lddt_calpha": "lddt_ca", "lddtca": "lddt_ca",
    "tmscore": "tm_score", "tm_score": "tm_score", "tm-score": "tm_score",
    "rmsd_ca": "rmsd_ca", "rmsd-ca": "rmsd_ca", "gdc-sc": "gdc_sc", "gdc_sc": "gdc_sc",
    "global_lddt": "global_lddt", "global lddt": "global_lddt", "molprobity": "molprobity",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-root", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--prediction-metadata", type=Path, required=True)
    p.add_argument("--scores", type=Path)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--primary-metric", default="lddt_ca")
    p.add_argument("--secondary-metric", default="gdt_ts")
    p.add_argument("--sort-by", default="casp_round,domain_id")
    p.add_argument("--include-failed", action="store_true")
    p.add_argument("--round-digits", type=int, default=3)
    return p.parse_args()


def clean(name: str) -> str:
    return name.strip().replace(" ", "_").replace("/", "_").lower()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return [{clean(k): (v if v is not None else "") for k, v in row.items()} for row in rows]


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: format_cell(row.get(col, "")) for col in columns})


def f(value: object) -> float:
    try:
        text = str(value).strip()
        return float(text) if text else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def fmt(value: object, digits: int = 3) -> str:
    value_f = f(value)
    if math.isnan(value_f):
        return ""
    return f"{value_f:.{digits}f}"


def format_cell(value: object) -> object:
    if isinstance(value, float) and math.isnan(value):
        return ""
    return value


def mean(values: Iterable[object]) -> float:
    nums = [f(v) for v in values]
    nums = [v for v in nums if not math.isnan(v)]
    return sum(nums) / len(nums) if nums else float("nan")


def med(values: Iterable[object]) -> float:
    nums = [f(v) for v in values]
    nums = [v for v in nums if not math.isnan(v)]
    return median(nums) if nums else float("nan")


def success(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "success", "succeeded"}


def normalize_score_rows(path: Path | None) -> tuple[list[dict[str, str]], list[str], list[str], str]:
    if not path or not path.exists():
        return [], [], METRICS[:], "missing score file" if path else "scores not provided"
    raw = read_csv(path)
    rows = []
    for row in raw:
        out = {}
        for key, value in row.items():
            out[ALIASES.get(key, key)] = value
        rows.append(out)
    available = [m for m in METRICS if any(r.get(m, "") for r in rows)]
    missing = [m for m in METRICS if m not in available]
    return rows, available, missing, ""


def normalize_carbon(row: dict[str, object]) -> None:
    carbon = f(row.get("carbon_emissions_g", ""))
    if math.isnan(carbon):
        carbon = f(row.get("total_carbon_emissions_g", ""))
    if math.isnan(carbon):
        kg = f(row.get("carbon_emissions_kg", ""))
        carbon = kg * 1000 if not math.isnan(kg) else float("nan")
    row["carbon_emissions_g"] = carbon
    energy = f(row.get("carbon_energy_consumed_kwh", ""))
    if math.isnan(energy):
        energy = f(row.get("total_energy_consumed_kwh", ""))
    if math.isnan(energy):
        energy = f(row.get("energy_consumed_kwh", ""))
    row["energy_consumed_kwh"] = energy


def merge_rows(args: argparse.Namespace) -> tuple[list[dict[str, object]], list[str], list[str], str]:
    metadata = read_csv(args.prediction_metadata)
    manifest_by_domain = {r.get("domain_id", ""): r for r in read_csv(args.manifest)}
    score_rows, available, missing, score_note = normalize_score_rows(args.scores)
    scores_by_domain_model = {(r.get("domain_id", ""), r.get("model", "")): r for r in score_rows}
    scores_by_target_model = {(r.get("target_id", ""), r.get("model", "")): r for r in score_rows}
    merged = []
    for row in metadata:
        out: dict[str, object] = dict(row)
        manifest = manifest_by_domain.get(row.get("domain_id", ""), {})
        for key, value in manifest.items():
            if key not in out or out.get(key, "") == "":
                out[key] = value
        if not out.get("qc_reason"):
            out["qc_reason"] = out.get("reason", "")
        if not out.get("target_qc_status"):
            out["target_qc_status"] = out.get("should_use", "")
        if not out.get("output_structure"):
            out["output_structure"] = out.get("output_pdb", "")
        score = scores_by_domain_model.get((out.get("domain_id", ""), out.get("model", "")))
        if score is None:
            score = scores_by_target_model.get((out.get("target_id", ""), out.get("model", "")), {})
        for metric in METRICS:
            out[metric] = score.get(metric, "")
        out["score_success"] = score.get("score_success", "")
        out["score_error"] = score.get("score_error", "") or (score_note if not score else "missing score")
        normalize_carbon(out)
        out["prediction_success_bool"] = success(out.get("success", ""))
        out["score_present_bool"] = any(not math.isnan(f(out.get(metric, ""))) for metric in METRICS)
        out["scored_success_bool"] = out["prediction_success_bool"] and out["score_present_bool"]
        merged.append(out)
    sort_cols = [c.strip() for c in args.sort_by.split(",") if c.strip()]
    merged.sort(key=lambda r: tuple(str(r.get(c, "")) for c in ["model", *sort_cols]))
    return merged, available, missing, score_note


def status(row: dict[str, object]) -> str:
    if not row.get("prediction_success_bool"):
        return "failed"
    if not row.get("score_present_bool"):
        return "missing_score"
    return "success"


def markdown_table(rows: list[dict[str, object]], columns: list[tuple[str, str]], digits: int) -> str:
    lines = ["| " + " | ".join(label for label, _ in columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        vals = []
        for _, key in columns:
            value = row.get(key, "")
            if key in {"reference_coverage", "mapping_identity", "mapping_coverage", *METRICS, "runtime_sec", "carbon_emissions_g"}:
                value = fmt(value, digits)
            vals.append(str(format_cell(value)))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def write_per_model_md(path: Path, rows: list[dict[str, object]], digits: int) -> None:
    by_model = defaultdict(list)
    for row in rows:
        item = dict(row)
        item["table_status"] = status(row)
        by_model[item.get("model", "")].append(item)
    columns = [("Target", "domain_id"), ("CASP", "casp_round"), ("PDB", "pdb_id"), ("Chain", "chain_id"), ("QC", "should_use"), ("Ref. cov.", "reference_coverage"), ("Map ID", "mapping_identity"), ("Map cov.", "mapping_coverage"), ("GDT-TS", "gdt_ts"), ("lDDT-Ca", "lddt_ca"), ("TM-score", "tm_score"), ("RMSD-Ca", "rmsd_ca"), ("Runtime (s)", "runtime_sec"), ("CO2 (g)", "carbon_emissions_g"), ("Status", "table_status")]
    lines = ["# Per-model Prediction Metrics", ""]
    for model in sorted(by_model):
        group = by_model[model]
        scored = [r for r in group if r.get("scored_success_bool")]
        yes = [r for r in scored if r.get("should_use") == "Yes"]
        yes_check = [r for r in scored if r.get("should_use") in {"Yes", "Check"}]
        all_qc = [r for r in scored if r.get("should_use") in {"Yes", "Check", "No"}]
        lines += [f"## {model}", "", markdown_table(group, columns, digits), ""]
        lines += [
            f"Mean over Yes targets: {fmt(mean(r.get('lddt_ca') for r in yes), digits)} lDDT-Ca; {fmt(mean(r.get('gdt_ts') for r in yes), digits)} GDT-TS",
            f"Mean over Yes+Check targets: {fmt(mean(r.get('lddt_ca') for r in yes_check), digits)} lDDT-Ca; {fmt(mean(r.get('gdt_ts') for r in yes_check), digits)} GDT-TS",
            f"Mean over all targets: {fmt(mean(r.get('lddt_ca') for r in all_qc), digits)} lDDT-Ca; {fmt(mean(r.get('gdt_ts') for r in all_qc), digits)} GDT-TS",
            f"Median over Yes targets: {fmt(med(r.get('lddt_ca') for r in yes), digits)} lDDT-Ca; {fmt(med(r.get('gdt_ts') for r in yes), digits)} GDT-TS",
            f"Number of successful predictions: {sum(1 for r in group if r.get('prediction_success_bool'))}",
            f"Number of failed predictions: {sum(1 for r in group if not r.get('prediction_success_bool'))}",
            f"Number of missing scores: {sum(1 for r in group if r.get('prediction_success_bool') and not r.get('score_present_bool'))}",
            "",
        ]
    path.write_text("\n".join(lines))


def model_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_model = defaultdict(list)
    for r in rows:
        by_model[r.get("model", "")].append(r)
    out = []
    for model, group in sorted(by_model.items()):
        yes = [r for r in group if r.get("should_use") == "Yes"]
        check = [r for r in group if r.get("should_use") == "Check"]
        no = [r for r in group if r.get("should_use") == "No"]
        yes_check = [r for r in group if r.get("should_use") in {"Yes", "Check"}]
        subsets = {"yes": yes, "yes_check": yes_check, "all": [r for r in group if r.get("should_use") in {"Yes", "Check", "No"}]}
        row = {
            "model": model, "input_mode": MODEL_INPUT_MODE.get(model, "unknown"),
            "n_total_targets": len({r.get("domain_id") for r in group}), "n_yes_targets": len({r.get("domain_id") for r in yes}),
            "n_check_targets": len({r.get("domain_id") for r in check}), "n_no_targets": len({r.get("domain_id") for r in no}),
            "n_success_all": sum(1 for r in group if r.get("prediction_success_bool")), "n_success_yes": sum(1 for r in yes if r.get("prediction_success_bool")),
            "n_success_yes_check": sum(1 for r in yes_check if r.get("prediction_success_bool")), "n_failed": sum(1 for r in group if not r.get("prediction_success_bool")),
            "mean_runtime_sec_all": mean(r.get("runtime_sec") for r in group), "mean_runtime_sec_yes": mean(r.get("runtime_sec") for r in yes),
            "mean_carbon_emissions_g_all": mean(r.get("carbon_emissions_g") for r in group), "mean_carbon_emissions_g_yes": mean(r.get("carbon_emissions_g") for r in yes),
            "total_carbon_emissions_g_all": sum(v for v in [f(r.get("carbon_emissions_g")) for r in group] if not math.isnan(v)) or float("nan"),
            "total_energy_consumed_kwh_all": sum(v for v in [f(r.get("energy_consumed_kwh")) for r in group] if not math.isnan(v)) or float("nan"),
        }
        for subset_name, subset in subsets.items():
            scored = [r for r in subset if r.get("scored_success_bool")]
            for metric in ["lddt_ca", "gdt_ts", "tm_score"]:
                row[f"mean_{metric}_{subset_name}"] = mean(r.get(metric) for r in scored)
                row[f"median_{metric}_{subset_name}"] = med(r.get(metric) for r in scored)
        out.append(row)
    columns = ["model","input_mode","n_total_targets","n_yes_targets","n_check_targets","n_no_targets","n_success_all","n_success_yes","n_success_yes_check","n_failed","mean_lddt_ca_yes","mean_gdt_ts_yes","mean_tm_score_yes","mean_lddt_ca_yes_check","mean_gdt_ts_yes_check","mean_tm_score_yes_check","mean_lddt_ca_all","mean_gdt_ts_all","mean_tm_score_all","median_lddt_ca_yes","median_gdt_ts_yes","median_tm_score_yes","mean_runtime_sec_all","mean_runtime_sec_yes","mean_carbon_emissions_g_all","mean_carbon_emissions_g_yes","total_carbon_emissions_g_all","total_energy_consumed_kwh_all"]
    return [{c: r.get(c, "") for c in columns} for r in out]


def target_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_target = defaultdict(list)
    for r in rows:
        by_target[r.get("domain_id", "")].append(r)
    out = []
    for domain_id, group in sorted(by_target.items()):
        first = group[0]
        row = {k: first.get(k, "") for k in ["domain_id","target_id","casp_round","pdb_id","chain_id","should_use","qc_reason","reference_coverage","mapping_identity","mapping_coverage","target_length"]}
        row["n_models_attempted"] = len({r.get("model") for r in group})
        row["n_models_success"] = sum(1 for r in group if r.get("prediction_success_bool"))
        scored = [r for r in group if r.get("scored_success_bool")]
        for metric in ["lddt_ca", "gdt_ts", "tm_score"]:
            valid = [r for r in scored if not math.isnan(f(r.get(metric)))]
            if valid:
                best = max(valid, key=lambda r: f(r.get(metric)))
                row[f"best_model_by_{metric}"] = best.get("model", "")
                row[f"best_{metric}"] = best.get(metric, "")
                row[f"mean_{metric}_across_models"] = mean(r.get(metric) for r in valid)
            else:
                row[f"best_model_by_{metric}"] = ""
                row[f"best_{metric}"] = ""
                row[f"mean_{metric}_across_models"] = ""
        out.append(row)
    return out


def markdown_summary(rows: list[dict[str, object]], columns: list[str], digits: int) -> str:
    table_rows = []
    for row in rows:
        table_rows.append({c: fmt(row[c], digits) if c.startswith(("mean_", "median_", "total_")) else row.get(c, "") for c in columns})
    return markdown_table(table_rows, [(c, c) for c in columns], digits)


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows, available, missing, score_note = merge_rows(args)
    write_csv(args.out_dir / "per_model_metrics.csv", rows, OUTPUT_COLUMNS)
    write_per_model_md(args.out_dir / "per_model_metrics.md", rows, args.round_digits)
    summary = model_summary(rows)
    summary_cols = list(summary[0].keys()) if summary else []
    write_csv(args.out_dir / "model_summary.csv", summary, summary_cols)
    (args.out_dir / "model_summary.md").write_text("# Model Summary\n\n" + markdown_summary(summary, summary_cols, args.round_digits) + "\n")
    targets = target_summary(rows)
    target_cols = list(targets[0].keys()) if targets else []
    write_csv(args.out_dir / "target_summary.csv", targets, target_cols)
    failed_cols = ["domain_id","model","casp_round","pdb_id","chain_id","should_use","reference_coverage","success","return_code","error_message","log_file","command"]
    failed = [{c: r.get(c, "") for c in failed_cols} for r in rows if not r.get("prediction_success_bool")]
    write_csv(args.out_dir / "failed_predictions.csv", failed, failed_cols)
    qc = defaultdict(int)
    seen = set()
    for r in rows:
        if r.get("domain_id") not in seen:
            qc[r.get("should_use", "")] += 1
            seen.add(r.get("domain_id"))
    report = [
        f"merged_rows: {len(rows)}", f"models: {len({r.get('model') for r in rows})}", f"targets: {len(seen)}",
        "qc_counts: " + ", ".join(f"{k}={v}" for k, v in sorted(qc.items())),
        "available_score_metrics: " + (",".join(available) if available else "none"),
        "missing_score_metrics: " + (",".join(missing) if missing else "none"),
        "score_note: " + (score_note or "scores loaded"), f"out_dir: {args.out_dir}",
    ]
    (args.out_dir / "table_generation_report.txt").write_text("\n".join(report) + "\n")
    print("\n".join(report))


if __name__ == "__main__":
    main()
