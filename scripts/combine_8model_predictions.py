#!/usr/bin/env python3
"""Combine essential prediction outputs from three CASP15/CASP16 benchmark runs.

The full CASP15/CASP16 (<1000 residue, unique) benchmark was run per backend
group in separate result directories:

  - msa-free            : chai1, esmfold, omegafold
  - shared-MSA colabfold: boltz2, colabfold, openfold, protenix
  - official af2        : af2

This script merges the 8 model predictions for the targets common to all three
runs (45 targets) into a single self-contained folder so the scoring driver can
process every model in one pass.

Only essential per-prediction outputs are copied (rank_*.pdb, metadata.json,
runner_carbon.json, af2_stage_metadata.csv, and the carbon/ CSV dir); large
intermediates (features.pkl, result_*.pkl, tmp_* dirs, MSAs) are skipped.

The merged metadata/prediction_manifest.csv (and manifest_used.csv) have their
per-run path prefixes rewritten to point inside the combined folder.
"""

import argparse
import csv
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source run dir (relative to repo root) -> models contributed by that run.
RUNS = {
    "results/20260601_104732_casp15_casp16_unique_lt1000_all_default_msa-free": [
        "chai1",
        "esmfold",
        "omegafold",
    ],
    "results/20260603_142659_casp15_casp16_unique_lt1000_all_default_colabfold": [
        "boltz2",
        "colabfold",
        "openfold",
        "protenix",
    ],
    "results/20260604_134750_casp15_casp16_unique_lt1000_all_default-af2": [
        "af2",
    ],
}

# Per-prediction files to copy verbatim when present (single files).
ESSENTIAL_FILES = ["metadata.json", "runner_carbon.json", "af2_stage_metadata.csv"]
# Per-prediction sub-directories to copy verbatim when present.
ESSENTIAL_DIRS = ["carbon"]
# Glob patterns of structure outputs to copy.
ESSENTIAL_GLOBS = ["rank_*.pdb"]

# Manifest with the canonical (superset) column order; other runs are a subset.
CANONICAL_MANIFEST_RUN = "results/20260604_134750_casp15_casp16_unique_lt1000_all_default-af2"


def common_targets(run_dirs):
    """Return the sorted set of target_ids present in every run's predictions/."""
    sets = []
    for run in run_dirs:
        pred = REPO_ROOT / run / "predictions"
        sets.append({p.name for p in pred.iterdir() if p.is_dir()})
    common = set.intersection(*sets)
    return sorted(common)


def rewrite_paths(value, dest_rel):
    """Rewrite any source-run path prefix in a string to the combined folder."""
    if not value:
        return value
    for run in RUNS:
        value = value.replace(run, dest_rel)
    return value


def copy_predictions(targets, dest_root, dest_rel):
    copied = 0
    for run, models in RUNS.items():
        src_pred = REPO_ROOT / run / "predictions"
        for target in targets:
            for model in models:
                src = src_pred / target / model
                if not src.is_dir():
                    print(f"  WARN missing prediction: {target}/{model} in {run}", file=sys.stderr)
                    continue
                dst = dest_root / "predictions" / target / model
                dst.mkdir(parents=True, exist_ok=True)
                for name in ESSENTIAL_FILES:
                    f = src / name
                    if f.is_file():
                        shutil.copy2(f, dst / name)
                for pattern in ESSENTIAL_GLOBS:
                    for f in sorted(src.glob(pattern)):
                        shutil.copy2(f, dst / f.name)
                for d in ESSENTIAL_DIRS:
                    sd = src / d
                    if sd.is_dir():
                        shutil.copytree(sd, dst / d, dirs_exist_ok=True)
                copied += 1
    return copied


def copy_sequences(targets, dest_root):
    dst = dest_root / "sequences"
    dst.mkdir(parents=True, exist_ok=True)
    # Sequences are identical across runs; take them from the canonical run.
    src = REPO_ROOT / CANONICAL_MANIFEST_RUN / "sequences"
    for target in targets:
        f = src / f"{target}.fasta"
        if f.is_file():
            shutil.copy2(f, dst / f.name)
        else:
            print(f"  WARN missing sequence FASTA: {target}.fasta", file=sys.stderr)


def merge_manifest(targets, dest_root, dest_rel):
    target_set = set(targets)
    # Canonical column order = superset manifest header.
    canon_path = REPO_ROOT / CANONICAL_MANIFEST_RUN / "metadata" / "prediction_manifest.csv"
    with open(canon_path, newline="") as fh:
        fieldnames = next(csv.reader(fh))

    rows = []
    for run, models in RUNS.items():
        man = REPO_ROOT / run / "metadata" / "prediction_manifest.csv"
        model_set = set(models)
        for row in csv.DictReader(open(man, newline="")):
            if row.get("target_id") not in target_set:
                continue
            if row.get("model") not in model_set:
                continue
            rewritten = {k: rewrite_paths(v, dest_rel) for k, v in row.items()}
            rows.append(rewritten)

    # Stable order: by target, then by a fixed model order.
    model_order = {m: i for i, ms in enumerate(RUNS.values()) for m in ms}
    rows.sort(key=lambda r: (r.get("target_id", ""), model_order.get(r.get("model", ""), 99)))

    out_dir = dest_root / "metadata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "prediction_manifest.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, restval="")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})
    return len(rows)


def copy_manifest_used(targets, dest_root, dest_rel):
    target_set = set(targets)
    src = REPO_ROOT / CANONICAL_MANIFEST_RUN / "manifest_used.csv"
    reader = csv.DictReader(open(src, newline=""))
    fieldnames = reader.fieldnames
    rows = [r for r in reader if r.get("target_id") in target_set]
    out = dest_root / "manifest_used.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, restval="")
        w.writeheader()
        for r in rows:
            w.writerow({k: rewrite_paths(v, dest_rel) for k, v in r.items()})
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--dest",
        default="data/2026-06-06-combine-8models",
        help="Destination folder (relative to repo root). Default: %(default)s",
    )
    ap.add_argument("--dry-run", action="store_true", help="Report plan without copying.")
    args = ap.parse_args()

    dest_rel = args.dest.rstrip("/")
    dest_root = REPO_ROOT / dest_rel

    run_dirs = list(RUNS)
    targets = common_targets(run_dirs)
    all_models = [m for ms in RUNS.values() for m in ms]

    print(f"Combined folder : {dest_root}")
    print(f"Common targets  : {len(targets)}")
    print(f"Models ({len(all_models)})     : {', '.join(all_models)}")
    print(f"Expected rows   : {len(targets) * len(all_models)} (targets x models)")

    if args.dry_run:
        print("\n[dry-run] no files written.")
        return

    dest_root.mkdir(parents=True, exist_ok=True)
    n_pred = copy_predictions(targets, dest_root, dest_rel)
    copy_sequences(targets, dest_root)
    n_manifest = merge_manifest(targets, dest_root, dest_rel)
    n_used = copy_manifest_used(targets, dest_root, dest_rel)

    print(f"\nCopied prediction dirs : {n_pred}")
    print(f"Merged manifest rows   : {n_manifest} -> {dest_rel}/metadata/prediction_manifest.csv")
    print(f"manifest_used rows     : {n_used} -> {dest_rel}/manifest_used.csv")
    print("Done.")


if __name__ == "__main__":
    main()
