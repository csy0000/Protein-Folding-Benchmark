#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise SystemExit(f"Missing required CSV: {path}")
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def f(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def model_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row.get("model", "")].append(row)
    return grouped


def summary_by_model(path: Path) -> dict[str, dict[str, str]]:
    return {row["model"]: row for row in read_csv(path)}


def msa_label(row: dict[str, str], model: str = "") -> str:
    if model == "chai1":
        return "no; native_embedding_no_msa"
    if model in {"colabfold_single", "openfold_single"}:
        return "no; forced_single_sequence_ablation"
    if model in {"colabfold_msa", "openfold_msa"}:
        return "yes; msa_ablation"
    used = row.get("msa_used", "")
    mode = row.get("msa_mode", "")
    if used == "true":
        return f"yes; {mode}"
    if used == "false":
        return f"no; {mode}"
    return mode or used or "unknown"


def default_table(summary_path: Path, metadata_path: Path) -> str:
    summary = summary_by_model(summary_path)
    grouped = model_rows(read_csv(metadata_path))
    order = ["esmfold", "omegafold", "boltz2", "chai1", "colabfold", "openfold"]
    lines = [
        "| Model | Mode / MSA | n_success | Mean lDDT-Ca | Mean TM-score | Mean Ca RMSD (A) | Mean inference time (s) | Mean model CO2e (g) | MSA cost included? | Notes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    notes = {
        "esmfold": "single-sequence language model",
        "omegafold": "single-sequence model",
        "boltz2": "local runner uses explicit no-MSA mode",
        "chai1": "default Chai-1 uses embeddings without MSAs/templates",
        "colabfold": "fresh ColabFold/MMseqs search per target",
        "openfold": "fresh ColabFold/MMseqs A3M passed to OpenFold",
    }
    for model in order:
        sr = summary[model]
        rows = grouped[model]
        first = rows[0]
        lines.append(
            "| {model} | {msa} | {succ} | {lddt} | {tm} | {rmsd} | {time} | {carbon} | {msa_cost} | {note} |".format(
                model=model,
                msa=msa_label(first, model),
                succ=sr["n_targets_success"],
                lddt=fmt(f(sr["mean_best_lddt_ca"])),
                tm=fmt(f(sr["mean_best_tmalign_tm_score_ref"])),
                rmsd=fmt(f(sr["mean_best_ca_rmsd"])),
                time=fmt(mean([f(r["inference_time_sec"]) for r in rows]), 1),
                carbon=fmt(mean([f(r["carbon_emissions_g"]) for r in rows]), 2),
                msa_cost="yes" if first.get("msa_generation_included_in_carbon") == "true" else "no",
                note=notes[model],
            )
        )
    return "\n".join(lines)


def shared_table(summary_path: Path, cost_path: Path) -> str:
    summary = summary_by_model(summary_path)
    grouped = model_rows(read_csv(cost_path))
    order = ["protenix", "openfold3"]
    lines = [
        "| Model | Mode / MSA | n_success | Mean lDDT-Ca | Mean TM-score | Mean Ca RMSD (A) | Mean model time (s) | Mean model CO2e (g) | Mean total time with shared MSA (s) | Mean total CO2e with shared MSA (g) | Notes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    notes = {
        "protenix": "shared A3M converted to Protenix paired/unpaired inputs",
        "openfold3": "shared A3M copied as cfdb_hits.a3m; low-memory experimental run",
    }
    for model in order:
        sr = summary[model]
        rows = grouped[model]
        lines.append(
            "| {model} | yes; shared_precomputed_msa | {succ} | {lddt} | {tm} | {rmsd} | {mtime} | {mcarbon} | {ttime} | {tcarbon} | {note} |".format(
                model=model,
                succ=sr["n_targets_success"],
                lddt=fmt(f(sr["mean_best_lddt_ca"])),
                tm=fmt(f(sr["mean_best_tmalign_tm_score_ref"])),
                rmsd=fmt(f(sr["mean_best_ca_rmsd"])),
                mtime=fmt(mean([f(r["model_inference_time_sec"]) for r in rows]), 1),
                mcarbon=fmt(mean([f(r["model_carbon_emissions_g"]) for r in rows]), 2),
                ttime=fmt(mean([f(r["total_time_with_shared_msa_sec"]) for r in rows]), 1),
                tcarbon=fmt(mean([f(r["total_carbon_with_shared_msa_g"]) for r in rows]), 2),
                note=notes[model],
            )
        )
    return "\n".join(lines)


def ablation_table(summary_path: Path, metadata_path: Path, order: list[str]) -> str:
    summary = summary_by_model(summary_path)
    grouped = model_rows(read_csv(metadata_path))
    lines = [
        "| Model | Mode / MSA | n_success | Mean lDDT-Ca | Mean TM-score | Mean Ca RMSD (A) | Mean inference time (s) | Mean model CO2e (g) |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model in order:
        sr = summary[model]
        rows = grouped[model]
        first = rows[0]
        lines.append(
            "| {model} | {msa} | {succ} | {lddt} | {tm} | {rmsd} | {time} | {carbon} |".format(
                model=model,
                msa=msa_label(first, model),
                succ=sr["n_targets_success"],
                lddt=fmt(f(sr["mean_best_lddt_ca"])),
                tm=fmt(f(sr["mean_best_tmalign_tm_score_ref"])),
                rmsd=fmt(f(sr["mean_best_ca_rmsd"])),
                time=fmt(mean([f(r["inference_time_sec"]) for r in rows]), 1),
                carbon=fmt(mean([f(r["carbon_emissions_g"]) for r in rows]), 2),
            )
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build README benchmark Markdown tables from result CSVs.")
    parser.add_argument("--out", default="results/readme_tables/benchmark_performance.md")
    args = parser.parse_args()

    sections = [
        "<!-- Generated by scripts/make_readme_benchmark_tables.py -->",
        "",
        "### Default/native first-five benchmark",
        "",
        default_table(
            Path("results/default_modes_first5_carbon_metadata/scores/all_targets_model_summary.csv"),
            Path("results/default_modes_first5_carbon_metadata/run_metadata.csv"),
        ),
        "",
        "### Shared-MSA experimental first-five benchmark",
        "",
        shared_table(
            Path("results/protenix_openfold3_shared_msa_first5/scores/all_targets_model_summary.csv"),
            Path("results/protenix_openfold3_shared_msa_first5/shared_msa_score_cost_summary.csv"),
        ),
        "",
        "### ColabFold single-sequence vs MSA ablation",
        "",
        ablation_table(
            Path("results/colabfold_single_vs_msa_first5_carbon/scores/all_targets_model_summary.csv"),
            Path("results/colabfold_single_vs_msa_first5_carbon/run_metadata.csv"),
            ["colabfold_single", "colabfold_msa"],
        ),
        "",
        "### OpenFold single-sequence vs MSA ablation",
        "",
        ablation_table(
            Path("results/openfold_single_vs_msa_first5_carbon/scores/all_targets_model_summary.csv"),
            Path("results/openfold_single_vs_msa_first5_carbon/run_metadata.csv"),
            ["openfold_single", "openfold_msa"],
        ),
        "",
    ]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(sections))
    print(out)


if __name__ == "__main__":
    main()
