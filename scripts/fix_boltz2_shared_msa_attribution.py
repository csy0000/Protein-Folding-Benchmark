#!/usr/bin/env python3
"""Restore shared-MSA build attribution to Boltz-2 GPU rerun rows.

The GPU rerun of Boltz-2 fed a pre-copied A3M to the runner, so no MSA-build
stage was recorded and total_runtime_sec = inference only (~47-66 s/target).
Every other shared-MSA model (colabfold, openfold, protenix) is charged the
same ColabFold/MMseqs2 build cost (~480-560 s/target), and the *original* Boltz-2
CPU run also carried it (T1104: total 590.7 = 108.7 inference + 482 MSA).

This script restores that attribution so Boltz-2 is apples-to-apples with the
other shared-MSA models:

  For each Boltz-2 target row in the GPU rerun manifest:
    msa_build_{runtime_sec, carbon_emissions_g, energy_consumed_kwh}
        <- colabfold's row for the same target (identical per-target MSA cost)
    msa_build_included_in_runtime / _carbon  <- "true"
    total_runtime_sec  = inference_runtime_sec + msa_build_runtime_sec
    total_carbon_emissions_g = inference_carbon_emissions_g + msa_build_carbon_emissions_g
    total_energy_consumed_kwh = inference_energy_consumed_kwh + msa_build_energy_consumed_kwh

The inference_* columns keep their GPU-measured values; msa_reused, msa_mode,
msa_source remain unchanged.

A .bak copy of the manifest is written before modification; running the script
again is idempotent (totals are recomputed from inference + msa_build each time).

Replicates: pass --run-dir <combine_dir>. A combine directory holds both the
colabfold and boltz2 rows in one manifest, so each rep is charged the MSA cost
*it actually measured*. Never borrow MSA cost from a different run -- that would
turn an accounting difference into apparent rep-to-rep variance.
"""

import argparse
import csv
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BOLTZ_GPU_MANIFEST = (
    REPO_ROOT
    / "results/20260609_gpu_rerun_colabfold/metadata/prediction_manifest.csv"
)

COLABFOLD_ORIG_MANIFEST = (
    REPO_ROOT
    / "results/20260603_142659_casp15_casp16_unique_lt1000_all_default_colabfold"
    / "metadata/prediction_manifest.csv"
)

MSA_COLS = [
    "msa_build_runtime_sec",
    "msa_build_carbon_emissions_g",
    "msa_build_energy_consumed_kwh",
]


def resolve_manifests(args: argparse.Namespace) -> tuple[Path, Path]:
    """Return (manifest_to_patch, msa_source_manifest)."""
    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.is_absolute():
            run_dir = REPO_ROOT / run_dir
        manifest = run_dir / "metadata" / "prediction_manifest.csv"
        # A combine dir carries colabfold and boltz2 rows in the same manifest.
        return manifest, Path(args.msa_source_manifest) if args.msa_source_manifest else manifest
    manifest = Path(args.manifest) if args.manifest else BOLTZ_GPU_MANIFEST
    source = Path(args.msa_source_manifest) if args.msa_source_manifest else COLABFOLD_ORIG_MANIFEST
    return manifest, source


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--run-dir",
        default="",
        help="Combine run directory; patches its metadata/prediction_manifest.csv using "
             "the colabfold rows in that same manifest. Use this for replicates.",
    )
    ap.add_argument("--manifest", default="", help="Manifest to patch (overrides the legacy default).")
    ap.add_argument(
        "--msa-source-manifest",
        default="",
        help="Manifest to read colabfold MSA-build cost from (defaults to the manifest being patched "
             "under --run-dir, or the June colabfold run otherwise).",
    )
    ap.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")
    args = ap.parse_args()

    manifest_path, source_path = resolve_manifests(args)

    if not manifest_path.exists():
        raise SystemExit(f"Manifest to patch not found: {manifest_path}")
    if not source_path.exists():
        raise SystemExit(f"MSA source manifest not found: {source_path}")

    print(f"Patching:   {manifest_path}")
    print(f"MSA source: {source_path}")

    # Load ColabFold MSA-build values keyed by target_id.
    cf_msa: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(source_path.open(newline="")):
        if row.get("model") == "colabfold":
            cf_msa[row["target_id"]] = {c: row.get(c, "") for c in MSA_COLS}
    if not cf_msa:
        raise SystemExit(f"No colabfold rows found in {source_path}; cannot attribute MSA cost.")

    # Backup.
    if not args.dry_run:
        bak = manifest_path.with_suffix(".csv.bak")
        shutil.copy2(manifest_path, bak)
        print(f"Backup: {bak}")

    # Read existing manifest.
    with manifest_path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    patched = 0
    for row in rows:
        if row.get("model") != "boltz2":
            continue
        tid = row.get("target_id", "")
        cf = cf_msa.get(tid)
        if cf is None:
            print(f"  WARN: no colabfold row for {tid}", file=sys.stderr)
            continue

        # Copy MSA-build cost.
        for c in MSA_COLS:
            row[c] = cf[c]
        row["msa_build_included_in_runtime"] = "true"
        row["msa_build_included_in_carbon"]  = "true"

        # Recompute totals.
        try:
            inf_rt  = float(row.get("inference_runtime_sec") or 0)
            msa_rt  = float(row.get("msa_build_runtime_sec") or 0)
            inf_co2 = float(row.get("inference_carbon_emissions_g") or 0)
            msa_co2 = float(row.get("msa_build_carbon_emissions_g") or 0)
            inf_kwh = float(row.get("inference_energy_consumed_kwh") or 0)
            msa_kwh = float(row.get("msa_build_energy_consumed_kwh") or 0)
        except (ValueError, TypeError) as e:
            print(f"  WARN: {tid} numeric conversion error: {e}", file=sys.stderr)
            continue

        row["total_runtime_sec"]          = str(inf_rt  + msa_rt)
        row["total_carbon_emissions_g"]   = str(inf_co2 + msa_co2)
        row["total_energy_consumed_kwh"]  = str(inf_kwh + msa_kwh)
        patched += 1

        print(
            f"  {tid}: inf={inf_rt:.1f}s  msa={msa_rt:.0f}s  "
            f"total={inf_rt+msa_rt:.1f}s  |  "
            f"co2 {inf_co2:.4f}+{msa_co2:.4f}={inf_co2+msa_co2:.4f} g"
        )

    # Write back.
    if args.dry_run:
        print(f"\n[dry-run] would patch {patched} Boltz-2 rows → {manifest_path}")
        return

    with manifest_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, restval="")
        w.writeheader()
        w.writerows(rows)

    print(f"\nPatched {patched} Boltz-2 rows → {manifest_path}")


if __name__ == "__main__":
    main()
