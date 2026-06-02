#!/usr/bin/env python
"""Export CASP15-style per-model Markdown tables from benchmark score CSVs."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean

SCORE_COLUMNS = ["GDT-TS", "GDC-SC", "TMscore", "Global LDDT", "MolProbity"]
DEFAULT_MODEL_ORDER = [
    "af2",
    "boltz",
    "boltz2",
    "chai1",
    "colabfold",
    "esmfold",
    "omegafold",
    "openfold",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True, help="Score CSV, e.g. scores/domain_scores.csv")
    parser.add_argument("--manifest", type=Path, help="Optional target manifest for target order/QC metadata")
    parser.add_argument("--out-md", type=Path, required=True, help="Markdown report to write")
    parser.add_argument("--out-csv", type=Path, help="Optional long-form CSV matching the Markdown rows")
    parser.add_argument(
        "--qc-status",
        default="Yes,Check,No",
        help="Comma-separated manifest should_use statuses to include when --manifest is provided",
    )
    parser.add_argument(
        "--model-order",
        default=",".join(DEFAULT_MODEL_ORDER),
        help="Comma-separated preferred model section order",
    )
    parser.add_argument("--round-digits", type=int, default=2, help="Digits for GDT-TS/GDC-SC percent metrics")
    parser.add_argument("--score-digits", type=int, default=2, help="Digits for TMscore/LDDT/MolProbity metrics")
    return parser.parse_args()


def clean(name: str) -> str:
    return name.strip().replace(" ", "_").replace("-", "_").replace("/", "_").lower()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return [{clean(k): (v or "") for k, v in row.items()} for row in csv.DictReader(handle)]


def to_float(value: object) -> float:
    try:
        text = str(value).strip()
        return float(text) if text else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def fmt(value: object, digits: int) -> str:
    value_f = to_float(value)
    if math.isnan(value_f):
        return ""
    return f"{value_f:.{digits}f}"


def percent_metric(value: object) -> float:
    value_f = to_float(value)
    if math.isnan(value_f):
        return value_f
    return value_f * 100.0 if value_f <= 1.0 else value_f


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "success", "succeeded"}


def manifest_index(path: Path | None, qc_statuses: set[str]) -> tuple[dict[str, dict[str, str]], dict[str, int]]:
    if not path:
        return {}, {}
    rows = read_csv(path)
    selected = {}
    order = {}
    for idx, row in enumerate(rows):
        domain_id = row.get("domain_id") or row.get("target_id")
        if not domain_id:
            continue
        if row.get("should_use", "") not in qc_statuses:
            continue
        selected[domain_id] = row
        order[domain_id] = idx
    return selected, order


def normalize_score_row(row: dict[str, str], manifest: dict[str, dict[str, str]]) -> dict[str, object] | None:
    domain_id = row.get("domain_id") or row.get("target_id")
    model = row.get("model", "")
    if not domain_id or not model:
        return None
    if manifest and domain_id not in manifest:
        return None
    if row.get("score_success") and not truthy(row.get("score_success")):
        return None
    merged = dict(manifest.get(domain_id, {}))
    merged.update(row)
    merged["domain_id"] = domain_id
    merged["target_name"] = f"{domain_id}.pdb"
    merged["gdt_ts_report"] = percent_metric(row.get("gdt_ts"))
    merged["gdc_sc_report"] = percent_metric(row.get("gdc_sc"))
    merged["tm_score_report"] = to_float(row.get("tm_score") or row.get("tmscore"))
    merged["global_lddt_report"] = to_float(row.get("global_lddt") or row.get("lddt_ca"))
    merged["molprobity_report"] = to_float(row.get("molprobity"))
    return merged


def model_sort_key(model: str, order: list[str]) -> tuple[int, str]:
    try:
        return (order.index(model), model)
    except ValueError:
        return (len(order), model)


def target_sort_key(row: dict[str, object], order: dict[str, int]) -> tuple[int, str]:
    domain_id = str(row.get("domain_id", ""))
    return (order.get(domain_id, 10**9), domain_id)


def markdown_table(rows: list[dict[str, object]], round_digits: int, score_digits: int) -> str:
    lines = [
        "Target  | GDT-TS  | GDC-SC  | TMscore  | Global LDDT  | MolProbity",
        "--- | --- | --- | --- | --- | ---",
    ]
    for row in rows:
        lines.append(
            "  | ".join(
                [
                    str(row.get("target_name", "")),
                    fmt(row.get("gdt_ts_report"), round_digits),
                    fmt(row.get("gdc_sc_report"), round_digits),
                    fmt(row.get("tm_score_report"), score_digits),
                    fmt(row.get("global_lddt_report"), score_digits),
                    fmt(row.get("molprobity_report"), score_digits),
                ]
            )
        )
    metric_keys = ["gdt_ts_report", "gdc_sc_report", "tm_score_report", "global_lddt_report", "molprobity_report"]
    mean_values = []
    for idx, key in enumerate(metric_keys):
        values = [to_float(row.get(key)) for row in rows]
        values = [value for value in values if not math.isnan(value)]
        digits = round_digits if idx < 2 else score_digits
        mean_values.append(f"{mean(values):.{digits}f}" if values else "")
    lines.append("  | ".join(["Mean", *mean_values]))
    return "\n".join(lines)


def write_long_csv(path: Path, by_model: dict[str, list[dict[str, object]]], model_order: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["Model", "Target", *SCORE_COLUMNS]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for model in sorted(by_model, key=lambda item: model_sort_key(item, model_order)):
            for row in by_model[model]:
                writer.writerow(
                    {
                        "Model": model,
                        "Target": row.get("target_name", ""),
                        "GDT-TS": row.get("gdt_ts_report", ""),
                        "GDC-SC": row.get("gdc_sc_report", ""),
                        "TMscore": row.get("tm_score_report", ""),
                        "Global LDDT": row.get("global_lddt_report", ""),
                        "MolProbity": row.get("molprobity_report", ""),
                    }
                )


def main() -> None:
    args = parse_args()
    qc_statuses = {item.strip() for item in args.qc_status.split(",") if item.strip()}
    model_order = [item.strip() for item in args.model_order.split(",") if item.strip()]
    manifest, target_order = manifest_index(args.manifest, qc_statuses)
    score_rows = read_csv(args.scores)

    by_model: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in score_rows:
        normalized = normalize_score_row(row, manifest)
        if not normalized:
            continue
        by_model[str(normalized["model"])].append(normalized)

    for rows in by_model.values():
        rows.sort(key=lambda row: target_sort_key(row, target_order))

    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CASP15-Style Benchmark Tables",
        "",
        "This report follows the per-model Markdown table layout used by Bhattacharya-Lab/CASP15.",
        "GDT-TS and GDC-SC are reported as percentages; TMscore, Global LDDT, and MolProbity are reported on their native scales.",
        "",
    ]
    for model in sorted(by_model, key=lambda item: model_sort_key(item, model_order)):
        lines.extend([f"## {model}", "", markdown_table(by_model[model], args.round_digits, args.score_digits), ""])
    args.out_md.write_text("\n".join(lines))
    if args.out_csv:
        write_long_csv(args.out_csv, by_model, model_order)
    print(f"models: {len(by_model)}")
    print(f"rows: {sum(len(rows) for rows in by_model.values())}")
    print(f"out_md: {args.out_md}")
    if args.out_csv:
        print(f"out_csv: {args.out_csv}")


if __name__ == "__main__":
    main()
