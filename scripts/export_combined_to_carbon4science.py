#!/usr/bin/env python3
"""Export combined 8-model CASP15/CASP16 benchmark results to carbon4science format.

Reads from:
  <run-dir>/metadata/prediction_manifest.csv
  <run-dir>/metadata/scoring_targets.csv
  <run-dir>/scores/*_scores.csv
  <run-dir>/scores/all_targets_model_summary.csv
  <run-dir>/predictions/<target>/<model>/carbon/*.csv   (CodeCarbon detail)

Writes to <out-dir>/ (default: ../carbon4science.github.io/results/):
  {model}.json × 8
  benchmark-score.csv
  benchmark-metadata.csv
  benchmark_metadata_all_models.csv
  benchmark_scores_all_models.csv
  benchmark_model_summary_all_models.csv
  benchmark-dataset.csv
  benchmark_collection_manifest.csv
  score_metric_definitions.csv  (if present in scores dir)
  score_metric_definitions.md   (if present in scores dir)

With --replicate-dirs, each {model}.json additionally carries the per-replicate
aggregate scores and cost totals, plus mean/std across replicates. Per-protein blocks
still come from the primary replicate only.

Usage (from repo root):
    python scripts/export_combined_to_carbon4science.py
    python scripts/export_combined_to_carbon4science.py --out-dir /tmp/c4s-preview
    python scripts/export_combined_to_carbon4science.py \
        --run-dir results/2026-06-09-combine-8models-gpu \
        --replicate-dirs results/2026-06-09-combine-8models-gpu \
                         results/20260802_082154_combine-8models-gpu_rep2 \
                         results/20260803_005751_combine-8models-gpu_rep3 \
        --replicate-labels rep1 rep2 rep3
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BENCHMARK_NAME = "casp15_casp16_unique_lt1000_combined_8models_20260606"
MODEL_ORDER = ["esmfold", "omegafold", "boltz2", "chai1", "colabfold", "openfold", "protenix", "af2"]

# Models that build no MSA themselves.
MSA_FREE = {"esmfold", "omegafold", "chai1"}
# Models using a colabfold/MMseqs2 MSA (msa_build_* columns).
# boltz2 reuses the shared ColabFold/MMseqs2 A3M and is charged the same MSA-build
# cost as openfold/protenix so that all four shared-MSA models are apples-to-apples.
MSA_COLABFOLD = {"colabfold", "openfold", "protenix", "boltz2"}
# af2 uses split msa_feature_* + af2_inference_* columns.
AF2_SET = {"af2"}

# MSA cross-mode variants (2026-07 run): single-sequence variants build no MSA;
# chai1_msa reuses the shared ColabFold A3M (like the MSA_COLABFOLD group).
MSA_FREE |= {"boltz2_nomsa", "colabfold_nomsa", "openfold_nomsa"}
MSA_COLABFOLD |= {"chai1_msa"}

SCORE_METRIC_NOTE = (
    "GDT_TS is on 0-1 scale; GDT_TS_percent is on 0-100 scale (same value × 100). "
    "lddt_ca (lDDT-Cα) is the primary benchmark metric. "
    "Scoring used --match-mode sequence (Needleman-Wunsch Cα alignment). "
    "References extracted from mmCIF using the manifest chain_id and residue range."
)


# ── I/O helpers ───────────────────────────────────────────────────────────────

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        print(f"  WARNING: no rows for {path.name}", file=sys.stderr)
        path.write_text("")
        return
    cols: list[str] = []
    for row in rows:
        for k in row:
            if k not in cols:
                cols.append(k)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in cols})


def read_carbon_inference_csv(carbon_dir: Path) -> dict[str, str]:
    """Read the inference CodeCarbon CSV from a prediction's carbon/ dir."""
    if not carbon_dir.is_dir():
        return {}
    # Prefer files named *inference* and not *msa_features*.
    candidates = sorted(carbon_dir.glob("*.csv"))
    inference = [f for f in candidates if "inference" in f.name and "msa_features" not in f.name]
    chosen = inference[0] if inference else (candidates[0] if candidates else None)
    if not chosen:
        return {}
    rows = read_csv(chosen)
    return rows[0] if rows else {}


# ── Field-mapping helpers ─────────────────────────────────────────────────────

def timing_fields(model: str, mrow: dict[str, str]) -> dict[str, str]:
    """Map manifest row → benchmark-score timing columns."""
    if model in MSA_FREE:
        return {
            "msa_runtime_sec": "",
            "msa_carbon_emissions_g": "",
            "model_inference_time_sec": mrow.get("inference_runtime_sec", ""),
            "model_carbon_emissions_g": mrow.get("inference_carbon_emissions_g", ""),
            "total_time_with_shared_msa_sec": mrow.get("total_runtime_sec", ""),
            "total_carbon_with_shared_msa_g": mrow.get("total_carbon_emissions_g", ""),
        }
    if model in MSA_COLABFOLD:
        return {
            "msa_runtime_sec": mrow.get("msa_build_runtime_sec", ""),
            "msa_carbon_emissions_g": mrow.get("msa_build_carbon_emissions_g", ""),
            "model_inference_time_sec": mrow.get("inference_runtime_sec", ""),
            "model_carbon_emissions_g": mrow.get("inference_carbon_emissions_g", ""),
            "total_time_with_shared_msa_sec": mrow.get("total_runtime_sec", ""),
            "total_carbon_with_shared_msa_g": mrow.get("total_carbon_emissions_g", ""),
        }
    # af2
    return {
        "msa_runtime_sec": mrow.get("msa_feature_runtime_sec", ""),
        "msa_carbon_emissions_g": mrow.get("msa_feature_carbon_emissions_g", ""),
        "model_inference_time_sec": mrow.get("af2_inference_runtime_sec", ""),
        "model_carbon_emissions_g": mrow.get("af2_inference_carbon_emissions_g", ""),
        "total_time_with_shared_msa_sec": mrow.get("total_runtime_sec", ""),
        "total_carbon_with_shared_msa_g": mrow.get("total_carbon_emissions_g", ""),
    }


def carbon_detail_fields(cc_row: dict[str, str]) -> dict[str, str]:
    """Map CodeCarbon CSV row → carbon_* fields for benchmark-metadata."""
    if not cc_row:
        return {
            "carbon_tracking_enabled": "",
            "carbon_method": "", "carbon_country_iso_code": "",
            "carbon_region": "", "carbon_intensity_mode": "",
            "carbon_intensity_g_per_kwh": "", "carbon_intensity_source": "",
            "carbon_emissions_kg": "", "carbon_emissions_g": "",
            "carbon_energy_consumed_kwh": "",
            "carbon_cpu_power_w": "", "carbon_gpu_power_w": "", "carbon_ram_power_w": "",
            "carbon_cpu_energy_kwh": "", "carbon_gpu_energy_kwh": "", "carbon_ram_energy_kwh": "",
            "carbon_duration_sec": "", "carbon_output_file": "", "carbon_error": "",
        }
    emissions_kg_raw = cc_row.get("emissions", "") or ""
    energy_kwh_raw = cc_row.get("energy_consumed", "") or ""
    try:
        emissions_kg = float(emissions_kg_raw)
        energy_kwh = float(energy_kwh_raw)
        intensity = round(emissions_kg * 1000 / energy_kwh, 2) if energy_kwh else ""
    except (ValueError, TypeError):
        emissions_kg = ""
        intensity = ""
    return {
        "carbon_tracking_enabled": "true",
        "carbon_method": "offline",
        "carbon_country_iso_code": cc_row.get("country_iso_code", "WORLD"),
        "carbon_region": cc_row.get("region", "world"),
        "carbon_intensity_mode": "constant",
        "carbon_intensity_g_per_kwh": str(intensity) if intensity != "" else "",
        "carbon_intensity_source": "configurable_default_world_average",
        "carbon_emissions_kg": str(emissions_kg) if emissions_kg != "" else "",
        "carbon_emissions_g": str(float(emissions_kg) * 1000) if emissions_kg != "" else "",
        "carbon_energy_consumed_kwh": energy_kwh_raw,
        "carbon_cpu_power_w": cc_row.get("cpu_power", ""),
        "carbon_gpu_power_w": cc_row.get("gpu_power", ""),
        "carbon_ram_power_w": cc_row.get("ram_power", ""),
        "carbon_cpu_energy_kwh": cc_row.get("cpu_energy", ""),
        "carbon_gpu_energy_kwh": cc_row.get("gpu_energy", ""),
        "carbon_ram_energy_kwh": cc_row.get("ram_energy", ""),
        "carbon_duration_sec": cc_row.get("duration", ""),
        "carbon_output_file": "",
        "carbon_error": "",
    }


def score_vals_from_row(srow: dict[str, str]) -> dict[str, str]:
    """Extract and alias all structural score fields from a scores CSV row."""
    SCORE_COLS = [
        "lddt_ca", "ca_rmsd",
        "gdt_ts", "gdt_ts_percent",
        "gdt_p1", "gdt_p2", "gdt_p4", "gdt_p8",
        "gdt_ts_method", "gdt_ts_error",
        "tmalign_tm_score_ref",
    ]
    vals = {c: srow.get(c, "") for c in SCORE_COLS}
    # Uppercase GDT aliases expected by carbon4science.
    vals["GDT_TS"] = vals["gdt_ts"]
    vals["GDT_TS_percent"] = vals["gdt_ts_percent"]
    return vals


def aggregate_with_aliases(row: dict[str, str]) -> dict:
    """Parse aggregate row from all_targets_model_summary.csv, add GDT uppercase aliases."""
    out: dict = {}
    for k, v in row.items():
        try:
            out[k] = float(v)
        except (ValueError, TypeError):
            out[k] = v
    for base in ("gdt_ts", "gdt_ts_percent"):
        upper = base.replace("gdt_ts", "GDT_TS")
        for pfx in ("mean_best_", "std_best_"):
            if pfx + base in out:
                out[pfx + upper] = out[pfx + base]
    return out


# ── Replicates ────────────────────────────────────────────────────────────────

# Per-model cost totals summed over targets, for one replicate. Note these are
# *attributed* costs: the shared ColabFold MSA is charged to every model that reuses
# it, so they compare models to each other but are not additive across models.
REPLICATE_COST_COLS = [
    "total_runtime_sec",
    "inference_runtime_sec",
    "msa_build_runtime_sec",
    "total_energy_consumed_kwh",
    "inference_energy_consumed_kwh",
    "total_carbon_emissions_g",
    "inference_carbon_emissions_g",
]


# CodeCarbon writes one CSV per (target, model, stage); the stage is only recoverable
# from the filename. This is the pipeline's only device-resolved measurement -- the
# prediction manifest records no device -- and it splits *energy*, not wall time.
CARBON_STAGE_SUFFIXES = (
    ("msa_build_emissions.csv", "msa_build"),
    ("msa_features_emissions.csv", "msa_features"),
    ("inference_emissions.csv", "inference"),
)


def replicate_device_energy(run_dir: Path) -> dict[str, dict[str, float]]:
    """Sum CPU/GPU/RAM energy and stage wall time over every CodeCarbon CSV, per model.

    `codecarbon_wall_time_sec` is CodeCarbon's own stage timer, measured independently
    of the manifest runtime columns, so the two cross-check each other. Note it covers
    only stages the model runs itself: models that consume the shared ColabFold MSA
    rather than building it have no msa_build stage of their own, so their CodeCarbon
    wall time is inference-only and is smaller than their attributed manifest total.
    """
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for path in sorted(run_dir.glob("predictions/*/*/carbon/*.csv")):
        if not any(path.name.endswith(suffix) for suffix, _ in CARBON_STAGE_SUFFIXES):
            continue
        model = path.parent.parent.name
        for row in read_csv(path):
            for src, dst in (("cpu_energy", "cpu_energy_kwh"),
                             ("gpu_energy", "gpu_energy_kwh"),
                             ("ram_energy", "ram_energy_kwh"),
                             ("duration", "codecarbon_wall_time_sec")):
                try:
                    totals[model][dst] += float(row.get(src) or 0.0)
                except (TypeError, ValueError):
                    continue
    for model, vals in totals.items():
        device_total = sum(vals.get(k, 0.0) for k in
                           ("cpu_energy_kwh", "gpu_energy_kwh", "ram_energy_kwh"))
        if device_total:
            vals["gpu_share_pct"] = 100.0 * vals.get("gpu_energy_kwh", 0.0) / device_total
    return {m: dict(v) for m, v in totals.items()}


def replicate_cost_totals(run_dir: Path) -> dict[str, dict[str, float]]:
    """Sum the cost columns over targets, per model, for one replicate.

    Includes the CPU/GPU/RAM energy split from CodeCarbon alongside the manifest
    runtime/energy/carbon columns.
    """
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in read_csv(run_dir / "metadata" / "prediction_manifest.csv"):
        model = row.get("model", "")
        if not model:
            continue
        for col in REPLICATE_COST_COLS:
            try:
                totals[model][col] += float(row.get(col) or 0.0)
            except (TypeError, ValueError):
                continue
    device = replicate_device_energy(run_dir)
    out = {m: dict(v) for m, v in totals.items()}
    for model, vals in device.items():
        out.setdefault(model, {}).update(vals)
    return out


def across_rep_stats(by_label: dict[str, dict]) -> dict:
    """mean/std/n across replicates for every numeric metric present.

    std is the sample standard deviation (ddof=1), matching
    scripts/06_summarize_across_reps.py; it is null when only one replicate has
    the metric. `values` keeps the individual per-replicate numbers so a consumer
    can recompute or plot them.
    """
    metrics = sorted({k for row in by_label.values() for k in row})
    out: dict = {}
    for metric in metrics:
        values = {
            label: row[metric]
            for label, row in by_label.items()
            if isinstance(row.get(metric), (int, float)) and not isinstance(row.get(metric), bool)
        }
        if not values:
            continue
        nums = list(values.values())
        out[metric] = {
            "mean": statistics.fmean(nums),
            "std": statistics.stdev(nums) if len(nums) > 1 else None,
            "n_reps": len(nums),
            "values": values,
        }
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--run-dir",
        default="results/2026-06-06-combine-8models",
        help="Combined run folder (relative to repo root). Default: %(default)s",
    )
    ap.add_argument(
        "--out-dir",
        default=str(REPO_ROOT.parent / "carbon4science.github.io" / "results"),
        help="Output directory. Default: %(default)s",
    )
    ap.add_argument(
        "--models",
        default=",".join(MODEL_ORDER),
        help=(
            "Comma-separated models to export (overrides the default 8-model order). "
            "Use with --json-only to add new-method JSONs without touching the shared "
            "8-model CSVs. Default: %(default)s"
        ),
    )
    ap.add_argument(
        "--replicate-dirs",
        nargs="*",
        default=[],
        help=(
            "Combine run folders for each replicate of the same benchmark. When given, "
            "every {model}.json gains a `replicates` block (per-rep aggregate scores and "
            "cost totals) and `aggregate_summary_across_reps` (mean/std/n over reps). "
            "Per-protein blocks still come from --run-dir only."
        ),
    )
    ap.add_argument(
        "--replicate-labels",
        nargs="*",
        default=[],
        help="Labels for --replicate-dirs (default: directory names). Must be unique.",
    )
    ap.add_argument(
        "--json-only",
        action="store_true",
        help=(
            "Write only per-model JSON files; skip the shared benchmark-*.csv / "
            "collection-manifest outputs so an existing 8-model export is not clobbered."
        ),
    )
    args = ap.parse_args()

    model_order = [m.strip() for m in args.models.split(",") if m.strip()]

    run_dir = REPO_ROOT / args.run_dir
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Source : {run_dir}")
    print(f"Output : {out_dir}")

    # ── Replicate aggregates (optional) ───────────────────────────────────────
    rep_dirs = [REPO_ROOT / d for d in args.replicate_dirs]
    for d in rep_dirs:
        if not d.is_dir():
            raise SystemExit(f"Replicate directory not found: {d}")
    if args.replicate_labels:
        if len(args.replicate_labels) != len(rep_dirs):
            raise SystemExit("--replicate-labels must have the same length as --replicate-dirs")
        rep_labels = list(args.replicate_labels)
    else:
        rep_labels = [d.name for d in rep_dirs]
    if len(set(rep_labels)) != len(rep_labels):
        raise SystemExit(f"Replicate labels must be unique, got: {rep_labels}")

    # label -> model -> {scores aggregate, cost totals}
    rep_scores: dict[str, dict[str, dict]] = {}
    rep_costs: dict[str, dict[str, dict[str, float]]] = {}
    primary_label = ""
    if rep_dirs:
        for label, d in zip(rep_labels, rep_dirs):
            rep_scores[label] = {
                r["model"]: aggregate_with_aliases(r)
                for r in read_csv(d / "scores" / "all_targets_model_summary.csv")
            }
            rep_costs[label] = replicate_cost_totals(d)
        # The replicate whose per-protein detail is exported in the main blocks.
        primary = run_dir.resolve()
        primary_label = next(
            (lab for lab, d in zip(rep_labels, rep_dirs) if d.resolve() == primary),
            "",
        )
        if not primary_label:
            print(f"WARNING: --run-dir {run_dir.name} is not among --replicate-dirs; "
                  "per-protein blocks and the replicate stats come from different runs.",
                  file=sys.stderr)
        print(f"Replicates: {', '.join(rep_labels)}"
              + (f" (primary: {primary_label})" if primary_label else ""))

    # ── Load source data ──────────────────────────────────────────────────────
    manifest_rows = read_csv(run_dir / "metadata" / "prediction_manifest.csv")
    targets_rows  = read_csv(run_dir / "metadata" / "scoring_targets.csv")
    agg_rows      = read_csv(run_dir / "scores" / "all_targets_model_summary.csv")

    man_key    = {(r["target_id"], r["model"]): r for r in manifest_rows}
    tgt_by_id  = {r["target_id"]: r for r in targets_rows}
    agg_by_mod = {r["model"]: r for r in agg_rows}

    # Best-rank score row per (target_id, model) — prefer rank_001.
    best_score: dict[tuple[str, str], dict[str, str]] = {}
    for score_csv in sorted((run_dir / "scores").glob("*_scores.csv")):
        for row in read_csv(score_csv):
            key = (row.get("target_id", ""), row.get("model", ""))
            pred = row.get("prediction", "")
            if "rank_001" in pred or key not in best_score:
                best_score[key] = row

    all_tids = sorted(tgt_by_id.keys())
    source_result_dir = str(run_dir.relative_to(REPO_ROOT))
    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # ── Build output rows ─────────────────────────────────────────────────────
    score_rows:    list[dict] = []   # benchmark-score.csv / per_protein_scores
    metadata_rows: list[dict] = []   # benchmark-metadata.csv / per_protein_runtime_metadata
    all_score_rows: list[dict] = []  # benchmark_scores_all_models.csv / per_prediction_scores
    status_rows:   list[dict] = []   # per_protein_status

    for model in model_order:
        for tid in all_tids:
            mrow = man_key.get((tid, model), {})
            trow = tgt_by_id.get(tid, {})
            srow = best_score.get((tid, model), {})

            success   = mrow.get("success", "") == "true"
            pdb_id    = mrow.get("pdb_id", trow.get("pdb_id", ""))
            pdb_chain = mrow.get("chain_id", "A")    # actual PDB chain (e.g. "P" for T1212)
            rank      = srow.get("rank", "1") or mrow.get("rank", "1")
            output_pdb = mrow.get("output_pdb", "")
            ref_pdb    = trow.get("reference_pdb", "")
            scored    = bool(srow and srow.get("lddt_ca"))

            timing = timing_fields(model, mrow)
            svals  = score_vals_from_row(srow) if srow else score_vals_from_row({})

            # CodeCarbon detail (inference CSV only).
            carbon_dir = run_dir / "predictions" / tid / model / "carbon"
            cc_row = read_carbon_inference_csv(carbon_dir)
            cfields = carbon_detail_fields(cc_row)

            # benchmark-score.csv (successful + scored only)
            if success and scored:
                score_rows.append({
                    "target_id": tid, "model": model,
                    **timing, **svals,
                })

            # benchmark_scores_all_models.csv
            if scored:
                tmalign_ref = srow.get("tmalign_tm_score_ref", "")
                all_score_rows.append({
                    "target_id": tid, "pdb_id": pdb_id, "chain": pdb_chain,
                    "model": model, "rank": rank,
                    "source_result_dir": source_result_dir,
                    "prediction_pdb": output_pdb,
                    "reference_pdb": ref_pdb,
                    **svals,
                    "tmalign_available": "True" if tmalign_ref else "False",
                    "tmalign_tm_score_pred":   srow.get("tmalign_tm_score_pred", ""),
                    "tmalign_rmsd":            srow.get("tmalign_rmsd", ""),
                    "tmalign_aligned_length":  srow.get("tmalign_aligned_length", ""),
                    "score_status": "failed" if srow.get("error") else "success",
                    "score_notes": srow.get("error", ""),
                })

            # benchmark-metadata.csv (all targets × models)
            metadata_rows.append({
                "target_id": tid, "pdb_id": pdb_id, "chain_id": pdb_chain,
                "model": model, "rank": rank,
                "output_pdb": output_pdb,
                "success": mrow.get("success", ""),
                "return_code": mrow.get("return_code", ""),
                "inference_time_sec": mrow.get("inference_runtime_sec", ""),
                "inference_time_sec_per_prediction": mrow.get("inference_runtime_sec", ""),
                "prediction_count": "1" if mrow else "",
                "trials_run": "", "max_trials": "", "successful_trial": "",
                "command": mrow.get("command", ""),
                "error_message": mrow.get("error_message", ""),
                "msa_used": mrow.get("msa_used", ""),
                "msa_source": mrow.get("msa_source", ""),
                "msa_mode": mrow.get("msa_mode", ""),
                "msa_database": mrow.get("msa_database", ""),
                "msa_database_path": mrow.get("msa_database_path", ""),
                "msa_generation_included_in_timing": mrow.get("msa_build_included_in_runtime", ""),
                "msa_generation_included_in_carbon": mrow.get("msa_build_included_in_carbon", ""),
                "msa_reused": mrow.get("msa_reused", ""),
                "shared_msa_metadata_file": "",
                "shared_msa_dir": mrow.get("shared_msa_dir", ""),
                "shared_msa_a3m_file": mrow.get("shared_msa_a3m_file", ""),
                "msa_generation_time_sec": mrow.get("msa_build_runtime_sec", ""),
                "msa_notes": mrow.get("stage_metadata_note", ""),
                "msa_feature_runtime_sec": mrow.get("msa_feature_runtime_sec", ""),
                "msa_feature_carbon_emissions_g": mrow.get("msa_feature_carbon_emissions_g", ""),
                "msa_feature_energy_consumed_kwh": mrow.get("msa_feature_energy_consumed_kwh", ""),
                "af2_inference_runtime_sec": mrow.get("af2_inference_runtime_sec", ""),
                "af2_inference_carbon_emissions_g": mrow.get("af2_inference_carbon_emissions_g", ""),
                "af2_inference_energy_consumed_kwh": mrow.get("af2_inference_energy_consumed_kwh", ""),
                "total_runtime_sec": mrow.get("total_runtime_sec", ""),
                "total_carbon_emissions_g": mrow.get("total_carbon_emissions_g", ""),
                "total_energy_consumed_kwh": mrow.get("total_energy_consumed_kwh", ""),
                "af2_db_preset": mrow.get("af2_db_preset", ""),
                "af2_model_preset": mrow.get("af2_model_preset", ""),
                "af2_params_dir": mrow.get("af2_params_dir", ""),
                "af2_data_dir": mrow.get("af2_data_dir", ""),
                "af2_features_dir": mrow.get("af2_features_dir", ""),
                **cfields,
            })

            # per_protein_status
            status_rows.append({
                "target_id": tid, "pdb_id": pdb_id, "chain": pdb_chain,
                "model": model,
                "status": "success" if success else "failed",
                "exit_code": mrow.get("return_code", ""),
                "runtime_sec": mrow.get("total_runtime_sec", ""),
                "log_file": mrow.get("log_file", ""),
                "reason": "" if success else mrow.get("error_message", "prediction failed"),
            })

    # ── benchmark-dataset.csv ─────────────────────────────────────────────────
    dataset_rows: list[dict] = []
    for tid in all_tids:
        trow = tgt_by_id[tid]
        # Use any manifest row for this target for additional metadata.
        mrow = (
            man_key.get((tid, "af2"))
            or man_key.get((tid, "esmfold"))
            or next((r for r in manifest_rows if r["target_id"] == tid), {})
        )
        dataset_rows.append({
            "target_id": tid,
            "pdb_id": mrow.get("pdb_id", ""),
            "chain_id": mrow.get("chain_id", "A"),
            "sequence": trow.get("sequence", ""),
            "reference_pdb": trow.get("reference_pdb", ""),
            "notes": (
                f"casp_round={mrow.get('casp_round', '')}; "
                f"target_id={tid}; "
                f"target_length={mrow.get('target_length', '')}; "
                f"stoichiometry={mrow.get('stoichiometry', 'A1')}; "
                f"src_chain={mrow.get('chain_id', '')}; "
                f"residues={mrow.get('residue_start', '')}-{mrow.get('residue_end', '')}"
            ),
        })

    # ── benchmark_model_summary_all_models.csv ────────────────────────────────
    summary_rows: list[dict] = []
    for model in model_order:
        if model in agg_by_mod:
            summary_rows.append(aggregate_with_aliases(agg_by_mod[model]))

    # ── Write CSVs (skipped in --json-only so an existing export is not clobbered) ─
    if args.json_only:
        print("\n[--json-only] Skipping shared benchmark-*.csv / collection-manifest writes.")
    else:
        write_csv(out_dir / "benchmark-score.csv", score_rows)
        write_csv(out_dir / "benchmark-metadata.csv", metadata_rows)
        write_csv(out_dir / "benchmark_metadata_all_models.csv", metadata_rows)   # alias
        write_csv(out_dir / "benchmark_scores_all_models.csv", all_score_rows)
        write_csv(out_dir / "benchmark_model_summary_all_models.csv", summary_rows)
        write_csv(out_dir / "benchmark-dataset.csv", dataset_rows)

        # benchmark_collection_manifest.csv
        manifest_entries = [
            ("exported_at_utc", exported_at),
            ("benchmark_name", BENCHMARK_NAME),
            ("source_result_dir", source_result_dir),
            ("target_set", str((run_dir / "metadata" / "scoring_targets.csv").relative_to(REPO_ROOT))),
            ("dataset_file", "results/benchmark-dataset.csv"),
            ("n_dataset_rows", str(len(dataset_rows))),
            ("n_targets", str(len(all_tids))),
            ("n_models", str(len(model_order))),
            ("n_model_json_files", str(len(model_order))),
            ("n_score_rows", str(len(score_rows))),
            ("n_metadata_rows_all", str(len(metadata_rows))),
            ("match_mode", "sequence"),
            ("score_scale_GDT_TS", "0-1; higher is better"),
            ("score_scale_GDT_TS_percent", "0-100; higher is better"),
        ]
        with (out_dir / "benchmark_collection_manifest.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["key", "value"], lineterminator="\n")
            w.writeheader()
            for k, v in manifest_entries:
                w.writerow({"key": k, "value": v})

        # score_metric_definitions (copy from scores dir if present, else skip)
        for ext in ("csv", "md"):
            src = run_dir / "scores" / f"score_metric_definitions.{ext}"
            if src.exists():
                shutil.copy2(src, out_dir / f"score_metric_definitions.{ext}")

        print(f"\nCSVs written:")
        for p in sorted(out_dir.glob("*.csv")):
            print(f"  {p.name} ({p.stat().st_size:,} bytes)")

    # ── Per-model JSON files ──────────────────────────────────────────────────
    score_by_model:    dict[str, list] = defaultdict(list)
    all_sc_by_model:   dict[str, list] = defaultdict(list)
    meta_by_model:     dict[str, list] = defaultdict(list)
    status_by_model_d: dict[str, list] = defaultdict(list)

    for row in score_rows:
        score_by_model[row["model"]].append(row)
    for row in all_score_rows:
        all_sc_by_model[row["model"]].append(row)
    for row in metadata_rows:
        meta_by_model[row["model"]].append(row)
    for row in status_rows:
        status_by_model_d[row["model"]].append(row)

    print(f"\nPer-model JSON files:")
    for model in model_order:
        agg = aggregate_with_aliases(agg_by_mod.get(model, {}))
        n_success = sum(1 for r in status_by_model_d[model] if r["status"] == "success")
        payload = {
            "model": model,
            "benchmark": BENCHMARK_NAME,
            "included_in_this_export": True,
            "exported_at_utc": exported_at,
            "source_repository": str(REPO_ROOT),
            "source_result_dir": source_result_dir,
            "target_set": str((run_dir / "metadata" / "scoring_targets.csv").relative_to(REPO_ROOT)),
            "n_targets": len(all_tids),
            "n_targets_success": n_success,
            "top_k": 1,
            "score_metric_note": SCORE_METRIC_NOTE,
            "aggregate_summary": agg,
            "per_protein_scores": score_by_model.get(model, []),
            "per_prediction_scores": all_sc_by_model.get(model, []),
            "per_protein_runtime_metadata": meta_by_model.get(model, []),
            "per_protein_status": status_by_model_d.get(model, []),
        }

        # Per-replicate results + across-replicate mean/std. Kept alongside the
        # existing keys rather than replacing them, so consumers of the single-run
        # schema keep working; `aggregate_summary` above is the primary replicate.
        if rep_dirs:
            replicates = []
            score_by_label: dict[str, dict] = {}
            cost_by_label: dict[str, dict] = {}
            for label, d in zip(rep_labels, rep_dirs):
                agg_rep = rep_scores[label].get(model, {})
                cost_rep = rep_costs[label].get(model, {})
                if not agg_rep and not cost_rep:
                    continue
                replicates.append({
                    "replicate": label,
                    "is_primary": label == primary_label,
                    "source_result_dir": str(d.relative_to(REPO_ROOT)),
                    "aggregate_summary": agg_rep,
                    "cost_totals": cost_rep,
                })
                if agg_rep:
                    score_by_label[label] = agg_rep
                if cost_rep:
                    cost_by_label[label] = cost_rep
            payload["n_replicates"] = len(replicates)
            payload["primary_replicate"] = primary_label
            payload["replicates"] = replicates
            payload["aggregate_summary_across_reps"] = across_rep_stats(score_by_label)
            payload["cost_totals_across_reps"] = across_rep_stats(cost_by_label)

        out_path = out_dir / f"{model}.json"
        out_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"  {model}.json  (n_success={n_success}/{len(all_tids)})")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"Export complete → {out_dir}")
    print(f"\nAggregate (mean lDDT-Cα):")
    for model in model_order:
        agg = agg_by_mod.get(model, {})
        lddt = agg.get("mean_best_lddt_ca", "")
        try:
            print(f"  {model:12s}  lDDT-Cα={float(lddt):.4f}")
        except (ValueError, TypeError):
            print(f"  {model:12s}  lDDT-Cα=N/A")


if __name__ == "__main__":
    main()
