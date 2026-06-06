#!/usr/bin/env python3
"""Score all predictions in the combined 8-model CASP15/CASP16 run folder.

Orchestrates per-target scoring, per-target summaries, an all-target aggregate
summary, and writes one JSON file per model into the run folder.

Usage (from repo root, inside folding-benchmark env):
    python scripts/score_combined_8models.py [--run-dir results/2026-06-06-combine-8models]

The scoring_targets.csv (45 CASP targets with reference_pdb and chain_id) is
copied from the colabfold companion run if not already present in the run folder.

All 8 model subdirs (chai1, esmfold, omegafold, boltz2, colabfold, openfold,
protenix, af2) are scored regardless of whether they are enabled in
configs/models.yaml (--only-enabled-models is NOT passed to 02_score_predictions).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source for the scoring_targets.csv (45 CASP targets, all references verified present).
SCORING_TARGETS_SOURCE = (
    REPO_ROOT
    / "results"
    / "20260603_142659_casp15_casp16_unique_lt1000_all_default_colabfold"
    / "metadata"
    / "scoring_targets.csv"
)

# Canonical model order for JSON output.
MODEL_ORDER = ["chai1", "esmfold", "omegafold", "boltz2", "colabfold", "openfold", "protenix", "af2"]

# Timing/carbon columns to pull from prediction_manifest.csv and merge into scores CSVs.
MANIFEST_TIMING_COLS = [
    "runtime_sec",
    "msa_build_runtime_sec",
    "msa_build_carbon_emissions_g",
    "msa_build_energy_consumed_kwh",
    "msa_build_included_in_runtime",
    "msa_build_included_in_carbon",
    "inference_runtime_sec",
    "inference_carbon_emissions_g",
    "inference_energy_consumed_kwh",
    "total_runtime_sec",
    "total_carbon_emissions_g",
    "total_energy_consumed_kwh",
]


def run_command(cmd: list[str], label: str = "") -> bool:
    desc = label or " ".join(cmd[:4])
    print(f"  >> {desc}")
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.stdout:
        for line in result.stdout.splitlines():
            print(f"     {line}")
    if result.stderr:
        for line in result.stderr.splitlines():
            print(f"     STDERR: {line}", file=sys.stderr)
    if result.returncode != 0:
        print(f"  !! FAILED (exit {result.returncode}): {desc}", file=sys.stderr)
    return result.returncode == 0


def load_scoring_targets(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    required = {"target_id", "reference_pdb", "chain_id"}
    missing = required - set(rows[0].keys() if rows else [])
    if missing:
        raise SystemExit(f"scoring_targets.csv missing required columns: {sorted(missing)}")
    return rows


def load_manifest(run_dir: Path) -> pd.DataFrame:
    path = run_dir / "metadata" / "prediction_manifest.csv"
    if not path.exists():
        print(f"WARNING: manifest not found: {path}", file=sys.stderr)
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def merge_timing_into_scores(score_csv: Path, manifest: pd.DataFrame) -> None:
    """Add timing/carbon columns from the prediction_manifest into a per-target scores CSV."""
    if score_csv.stat().st_size == 0:
        return
    df = pd.read_csv(score_csv)
    if manifest.empty:
        for col in MANIFEST_TIMING_COLS:
            df[col] = pd.NA
        df.to_csv(score_csv, index=False)
        return

    avail_cols = [c for c in MANIFEST_TIMING_COLS if c in manifest.columns]
    key_cols = ["target_id", "model"]
    avail = [c for c in [*key_cols, *avail_cols] if c in manifest.columns]
    timing = (
        manifest[avail]
        .drop_duplicates(key_cols, keep="last")
        .copy()
    )

    # Drop existing timing cols so we don't duplicate on re-run.
    drop = [c for c in MANIFEST_TIMING_COLS if c in df.columns]
    if drop:
        df = df.drop(columns=drop)

    df = df.merge(timing, on=key_cols, how="left")
    missing_rows = df["inference_runtime_sec"].isna().sum() if "inference_runtime_sec" in df else 0
    if missing_rows:
        print(
            f"  WARNING: {missing_rows} scored row(s) had no matching timing in manifest for {score_csv.name}",
            file=sys.stderr,
        )
    df.to_csv(score_csv, index=False)


def safe_float(value: object) -> float | None:
    try:
        f = float(value)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def build_per_target_json_row(
    target_id: str,
    manifest_row: dict | None,
    score_row: dict | None,
) -> dict:
    """Build one per_target entry for a model JSON."""
    # Determine success from manifest (authoritative on prediction outcome).
    success = False
    if manifest_row:
        success = str(manifest_row.get("success", "false")).strip().lower() == "true"

    entry: dict = {"target_id": target_id, "success": success}

    # Structure scores (from scoring output).
    for src_col, json_key in [
        ("lddt_ca", "lddt_ca"),
        ("tmalign_tm_score_ref", "tmalign_tm_score_ref"),
        ("tmalign_tm_score_pred", "tmalign_tm_score_pred"),
        ("tmalign_rmsd", "tmalign_rmsd"),
        ("tmalign_aligned_length", "tmalign_aligned_length"),
        ("gdt_ts", "gdt_ts"),
        ("gdt_ts_percent", "gdt_ts_percent"),
        ("ca_rmsd", "ca_rmsd"),
    ]:
        entry[json_key] = safe_float(score_row.get(src_col)) if score_row else None

    # Runtime/carbon from manifest.
    if manifest_row:
        for col in MANIFEST_TIMING_COLS:
            raw = manifest_row.get(col, "")
            # Booleans come as strings from CSV.
            if raw in ("true", "True", "True"):
                entry[col] = True
            elif raw in ("false", "False"):
                entry[col] = False
            else:
                v = safe_float(raw)
                entry[col] = v if v is not None else (raw if raw else None)
    else:
        for col in MANIFEST_TIMING_COLS:
            entry[col] = None

    return entry


def write_model_json(
    model: str,
    run_dir: Path,
    targets: list[dict[str, str]],
    manifest: pd.DataFrame,
    aggregate_summary: pd.DataFrame,
    match_mode: str,
) -> None:
    scores_dir = run_dir / "scores"

    # Build (target_id, model) → score row lookup from per-target score CSVs.
    score_lookup: dict[str, dict] = {}
    for target in targets:
        tid = target["target_id"]
        score_csv = scores_dir / f"{tid}_scores.csv"
        if not score_csv.exists():
            continue
        df = pd.read_csv(score_csv)
        model_rows = df[df["model"] == model] if "model" in df.columns else pd.DataFrame()
        if model_rows.empty:
            continue
        # Take rank_001 (or the best row by lddt_ca if no rank col).
        if "prediction" in model_rows.columns:
            rank1 = model_rows[model_rows["prediction"].str.contains("rank_001", na=False)]
            best = rank1.iloc[0].to_dict() if not rank1.empty else model_rows.iloc[0].to_dict()
        else:
            best = model_rows.iloc[0].to_dict()
        score_lookup[tid] = best

    # Build manifest lookup for this model.
    manifest_lookup: dict[str, dict] = {}
    if not manifest.empty and "model" in manifest.columns:
        model_manifest = manifest[manifest["model"] == model]
        for _, row in model_manifest.iterrows():
            manifest_lookup[row["target_id"]] = row.to_dict()

    # Aggregate summary row for this model.
    agg: dict = {}
    if not aggregate_summary.empty and "model" in aggregate_summary.columns:
        rows = aggregate_summary[aggregate_summary["model"] == model]
        if not rows.empty:
            agg = {k: (None if pd.isna(v) else v) for k, v in rows.iloc[0].to_dict().items()}

    n_success = sum(
        1 for t in targets
        if str(manifest_lookup.get(t["target_id"], {}).get("success", "false")).strip().lower() == "true"
    )
    n_failed = len(targets) - n_success

    per_target = [
        build_per_target_json_row(
            t["target_id"],
            manifest_lookup.get(t["target_id"]),
            score_lookup.get(t["target_id"]),
        )
        for t in targets
    ]

    payload = {
        "model": model,
        "benchmark": "casp15_casp16_unique_lt1000_combined_8models",
        "exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_folder": str(run_dir.relative_to(REPO_ROOT)),
        "match_mode": match_mode,
        "n_targets": len(targets),
        "n_success": n_success,
        "n_failed": n_failed,
        "aggregate_summary": agg,
        "per_target": per_target,
    }

    out = run_dir / f"{model}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"  wrote {out.name}  (n_success={n_success}, n_failed={n_failed})")


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
        "--match-mode",
        choices=["sequential", "resseq", "sequence"],
        default="sequence",
        help="Cα residue matching mode passed to 02_score_predictions.py. Default: %(default)s",
    )
    ap.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Skip 02/03/05 scoring steps; only regenerate JSON from existing scores.",
    )
    ap.add_argument(
        "--fail-fast",
        action="store_true",
        help="Abort on the first scoring failure instead of continuing.",
    )
    args = ap.parse_args()

    run_dir = REPO_ROOT / args.run_dir
    if not run_dir.is_dir():
        raise SystemExit(f"Run dir not found: {run_dir}")

    scores_dir = run_dir / "scores"
    scores_dir.mkdir(exist_ok=True)

    # ── 1. Ensure scoring_targets.csv is present ──────────────────────────────
    scoring_targets_path = run_dir / "metadata" / "scoring_targets.csv"
    if not scoring_targets_path.exists():
        if not SCORING_TARGETS_SOURCE.exists():
            raise SystemExit(f"Source scoring_targets.csv not found: {SCORING_TARGETS_SOURCE}")
        shutil.copy2(SCORING_TARGETS_SOURCE, scoring_targets_path)
        print(f"Copied scoring_targets.csv → {scoring_targets_path}")
    else:
        print(f"Using existing scoring_targets.csv: {scoring_targets_path}")

    targets = load_scoring_targets(scoring_targets_path)
    print(f"Targets: {len(targets)}")

    # ── 2. Load manifest for timing/carbon merge ──────────────────────────────
    manifest = load_manifest(run_dir)
    print(f"Manifest rows: {len(manifest)}")

    script_02 = REPO_ROOT / "scripts" / "02_score_predictions.py"
    script_03 = REPO_ROOT / "scripts" / "03_summarize_scores.py"
    script_05 = REPO_ROOT / "scripts" / "05_summarize_all_targets.py"

    failures = 0

    if not args.skip_scoring:
        # ── 3. Score per target ───────────────────────────────────────────────
        print(f"\n── Scoring {len(targets)} targets (match-mode={args.match_mode}) ──")
        for i, target in enumerate(targets, 1):
            tid = target["target_id"]
            ref = target["reference_pdb"]
            chain = target["chain_id"]
            print(f"\n[{i:2d}/{len(targets)}] {tid}  ref={ref}  chain={chain}")

            if not Path(ref).exists():
                print(f"  WARN: reference not found, skipping: {ref}", file=sys.stderr)
                failures += 1
                if args.fail_fast:
                    raise SystemExit("fail-fast: missing reference")
                continue

            # 02: score predictions → <target>_scores.csv
            cmd_02 = [
                sys.executable, str(script_02),
                "--target-id", tid,
                "--reference", ref,
                "--ref-chain", chain,
                "--pred-chain", "A",
                "--pred-root", str(run_dir / "predictions"),
                "--outdir", str(scores_dir),
                "--match-mode", args.match_mode,
                "--use-tmalign",
                "--use-gdt-ts",
            ]
            ok = run_command(cmd_02, label=f"02_score_predictions  {tid}")
            if not ok:
                failures += 1
                if args.fail_fast:
                    raise SystemExit(f"fail-fast: 02 failed for {tid}")
                continue

            # Merge timing/carbon from manifest into scores CSV.
            score_csv = scores_dir / f"{tid}_scores.csv"
            if score_csv.exists():
                merge_timing_into_scores(score_csv, manifest)

            # 03: per-target model summary
            if score_csv.exists() and score_csv.stat().st_size > 0:
                cmd_03 = [
                    sys.executable, str(script_03),
                    "--scores", str(score_csv),
                    "--output", str(scores_dir / f"{tid}_model_summary.csv"),
                    "--markdown-output", str(scores_dir / f"{tid}_model_summary.md"),
                ]
                ok3 = run_command(cmd_03, label=f"03_summarize_scores  {tid}")
                if not ok3:
                    failures += 1
                    if args.fail_fast:
                        raise SystemExit(f"fail-fast: 03 failed for {tid}")

        # ── 4. All-target aggregate summary ──────────────────────────────────
        print("\n── Aggregate summary (05_summarize_all_targets) ──")
        cmd_05 = [
            sys.executable, str(script_05),
            "--targets", str(scoring_targets_path),
            "--scores-dir", str(scores_dir),
            "--out-csv", str(scores_dir / "all_targets_model_summary.csv"),
            "--out-md", str(scores_dir / "all_targets_model_summary.md"),
        ]
        ok5 = run_command(cmd_05, label="05_summarize_all_targets")
        if not ok5:
            failures += 1

    # ── 5. Per-model JSON files ───────────────────────────────────────────────
    print("\n── Writing per-model JSON files ──")
    agg_summary_path = scores_dir / "all_targets_model_summary.csv"
    aggregate_summary = pd.read_csv(agg_summary_path) if agg_summary_path.exists() else pd.DataFrame()

    # Reload manifest fresh (in case this is --skip-scoring and manifest was updated).
    manifest = load_manifest(run_dir)

    models_present = sorted(
        {p.name for t in targets for p in (run_dir / "predictions" / t["target_id"]).iterdir()
         if (run_dir / "predictions" / t["target_id"]).is_dir() and p.is_dir()}
        if any((run_dir / "predictions" / t["target_id"]).is_dir() for t in targets)
        else MODEL_ORDER
    )
    # Respect canonical order; include any extra models found in predictions.
    ordered_models = [m for m in MODEL_ORDER if m in models_present]
    ordered_models += [m for m in models_present if m not in MODEL_ORDER]

    for model in ordered_models:
        print(f"\n  {model}.json")
        write_model_json(
            model=model,
            run_dir=run_dir,
            targets=targets,
            manifest=manifest,
            aggregate_summary=aggregate_summary,
            match_mode=args.match_mode,
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"Done. Scoring failures: {failures}")
    print(f"Scores dir : {scores_dir}")
    json_files = sorted(run_dir.glob("*.json"))
    print(f"JSON files : {len(json_files)} → {[f.name for f in json_files]}")
    if aggregate_summary_path := (scores_dir / "all_targets_model_summary.csv"):
        if aggregate_summary_path.exists():
            df = pd.read_csv(aggregate_summary_path)
            print("\nAggregate summary (mean best lDDT-Cα per model):")
            for _, row in df.iterrows():
                lddt = row.get("mean_best_lddt_ca", float("nan"))
                tm = row.get("mean_best_tmalign_tm_score_ref", float("nan"))
                print(f"  {row['model']:12s}  lDDT-Cα={lddt:.4f}  TM-score={tm:.4f}")


if __name__ == "__main__":
    main()
