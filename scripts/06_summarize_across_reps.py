#!/usr/bin/env python3
"""Aggregate runtime / energy / CO2 across benchmark replicates (mean +/- std over reps).

Every other summary in this repo takes mean/std across the 45 *targets*. This one takes
them across *runs*, which is what an error bar on a cost measurement actually needs.

Two accounting subtleties it exists to get right:

1. The ColabFold/MMseqs2 MSA is built once per rep and re-charged to boltz2, openfold and
   protenix. Summing total_runtime_sec over all rows therefore counts it 4x -- 56.9 h
   against a true 37.4 h for rep1. Per-model attributed cost is correct for comparing
   models to each other, but is NOT additive across models. Only benchmark_incremental_*
   is a defensible whole-benchmark figure.

2. A model charged the shared MSA in one rep and not another shows enormous fake variance.
   The attribution-drift check catches that before it reaches a table.

Usage:
    python scripts/06_summarize_across_reps.py \
        --run-dirs results/2026-06-09-combine-8models-gpu \
                   results/<TS>_combine-8models-gpu_rep2 \
                   results/<TS>_combine-8models-gpu_rep3
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent.parent

KEY = ["target_id", "model"]

# (manifest column, output prefix)
COST_METRICS = [
    ("total_runtime_sec", "total_runtime_sec"),
    ("inference_runtime_sec", "inference_runtime_sec"),
    ("msa_build_runtime_sec", "msa_build_runtime_sec"),
    ("total_energy_consumed_kwh", "total_energy_kwh"),
    ("inference_energy_consumed_kwh", "inference_energy_kwh"),
    ("total_carbon_emissions_g", "total_co2_g"),
    ("inference_carbon_emissions_g", "inference_co2_g"),
]

# Models expected to differ run-to-run. AF2 draws a random seed that drives MSA
# subsampling; measured effect is ~0.02 lDDT between seeds, vs ~1e-4 at fixed seed.
DEFAULT_NONDETERMINISTIC = "af2"

# Models allowed to change MSA builder/reuser role between reps (deliberate reuse).
DEFAULT_EXPECT_MSA_REUSE = "af2"


def mean_value(series: pd.Series) -> float:
    valid = pd.to_numeric(series, errors="coerce").dropna()
    if valid.empty:
        return np.nan
    return float(valid.mean())


def sample_std(series: pd.Series) -> float:
    valid = pd.to_numeric(series, errors="coerce").dropna()
    if len(valid) < 2:
        return np.nan
    return float(valid.std(ddof=1))


def cv(mean: float, std: float) -> float:
    if pd.isna(mean) or pd.isna(std) or mean == 0:
        return np.nan
    return float(std / mean)


def resolve(path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else REPO_ROOT / path


def load_manifest(run_dir: Path, rep: str) -> pd.DataFrame:
    path = run_dir / "metadata" / "prediction_manifest.csv"
    if not path.is_file():
        raise SystemExit(f"Manifest not found for rep {rep}: {path}")
    df = pd.read_csv(path, low_memory=False)
    before = len(df)
    df = df.drop_duplicates(KEY, keep="last")
    if len(df) < before:
        print(f"WARNING: {rep}: dropped {before - len(df)} duplicate (target_id, model) rows",
              file=sys.stderr)
    df["rep"] = rep
    df["success_bool"] = df["success"].astype(str).str.strip().str.lower().eq("true")
    for column, _ in COST_METRICS:
        if column not in df.columns:
            df[column] = np.nan
        df[column] = pd.to_numeric(df[column], errors="coerce")
    for column in ("msa_build_carbon_emissions_g", "msa_build_energy_consumed_kwh"):
        if column not in df.columns:
            df[column] = np.nan
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def load_accuracy(run_dir: Path, rep: str) -> pd.DataFrame:
    """Per (model, target) best lDDT-Ca from the per-target model summaries."""
    scores_dir = run_dir / "scores"
    frames = []
    for path in sorted(scores_dir.glob("*_model_summary.csv")):
        if path.name.startswith("all_targets"):
            continue
        target_id = path.name[: -len("_model_summary.csv")]
        df = pd.read_csv(path)
        if "best_lddt_ca" not in df.columns:
            continue
        df = df[["model", "best_lddt_ca"]].copy()
        df["target_id"] = target_id
        frames.append(df)
    if not frames:
        print(f"WARNING: {rep}: no per-target model summaries under {scores_dir}", file=sys.stderr)
        return pd.DataFrame(columns=["rep", "target_id", "model", "best_lddt_ca"])
    out = pd.concat(frames, ignore_index=True)
    out["rep"] = rep
    out["best_lddt_ca"] = pd.to_numeric(out["best_lddt_ca"], errors="coerce")
    return out[["rep", "target_id", "model", "best_lddt_ca"]]


def classify_msa_roles(df: pd.DataFrame) -> pd.DataFrame:
    """Label each row builder / reuser / none, from the data rather than a model list."""
    reused = df.get("msa_reused", pd.Series("", index=df.index)).astype(str).str.lower().eq("true")
    mode = df.get("msa_mode", pd.Series("", index=df.index)).astype(str)
    reused = reused | mode.str.contains("shared_precomputed", na=False)
    charged = df["msa_build_runtime_sec"].fillna(0) > 0

    role = pd.Series("none", index=df.index)
    role[reused] = "reuser"
    role[charged & ~reused] = "builder"
    df = df.copy()
    df["msa_role"] = role
    df["msa_charged"] = charged
    return df


def intersect_reps(manifests: list[pd.DataFrame]) -> tuple[set[tuple[str, str]], pd.DataFrame]:
    """Keep (target, model) pairs successful in EVERY rep; report the rest."""
    per_rep_ok = []
    per_rep_present = []
    for df in manifests:
        per_rep_ok.append(set(map(tuple, df.loc[df["success_bool"], KEY].values)))
        per_rep_present.append(set(map(tuple, df[KEY].values)))
    keep = set.intersection(*per_rep_ok) if per_rep_ok else set()
    universe = set.union(*per_rep_present) if per_rep_present else set()

    dropped_rows = []
    for target_id, model in sorted(universe - keep):
        missing, failed = [], []
        for df in manifests:
            rep = df["rep"].iloc[0]
            if (target_id, model) not in set(map(tuple, df[KEY].values)):
                missing.append(rep)
            elif (target_id, model) not in set(map(tuple, df.loc[df["success_bool"], KEY].values)):
                failed.append(rep)
        dropped_rows.append({
            "target_id": target_id,
            "model": model,
            "n_reps_missing": len(missing),
            "n_reps_failed": len(failed),
            "reps_missing": "|".join(missing),
            "reps_failed": "|".join(failed),
            "reason": "absent_from_rep" if missing else "failed_in_rep",
        })
    return keep, pd.DataFrame(dropped_rows)


def attribution_drift(df: pd.DataFrame, expect_reuse: set[str]) -> pd.DataFrame:
    """Flag models charged the shared MSA in some reps but not others."""
    rows = []
    for model, group in df.groupby("model", sort=True):
        by_rep = group.groupby("rep")["msa_charged"].any()
        roles = sorted(set(group["msa_role"]))
        if by_rep.nunique() > 1:
            expected = model in expect_reuse
            rows.append({
                "model": model,
                "charged_in_reps": "|".join(sorted(by_rep[by_rep].index)),
                "uncharged_in_reps": "|".join(sorted(by_rep[~by_rep].index)),
                "roles_seen": "|".join(roles),
                "expected": expected,
                "severity": "note" if expected else "ERROR",
            })
    return pd.DataFrame(rows)


def per_rep_model_cost(df: pd.DataFrame) -> pd.DataFrame:
    agg = {out: (col, "sum") for col, out in COST_METRICS}
    agg["n_targets"] = ("target_id", "nunique")
    per_rep = df.groupby(["rep", "model"], sort=True).agg(**agg).reset_index()
    per_rep["per_target_total_runtime_sec"] = per_rep["total_runtime_sec"] / per_rep["n_targets"]
    per_rep["per_target_total_co2_g"] = per_rep["total_co2_g"] / per_rep["n_targets"]
    return per_rep


def aggregate_across_reps(per_rep: pd.DataFrame, roles: dict[str, str],
                          drift_models: set[str]) -> pd.DataFrame:
    metrics = [out for _, out in COST_METRICS] + [
        "per_target_total_runtime_sec", "per_target_total_co2_g",
    ]
    rows = []
    all_reps = set(per_rep["rep"])
    for model, group in per_rep.groupby("model", sort=True):
        row = {
            "model": model,
            "n_reps": int(group["rep"].nunique()),
            "reps_present": "|".join(sorted(group["rep"])),
            "model_in_all_reps": set(group["rep"]) == all_reps,
            "n_targets": int(group["n_targets"].max()),
            "msa_role": roles.get(model, ""),
            # A model charged the shared MSA in only some reps has a *total* cost that
            # mixes accounting with machine variance; its inference cost stays valid.
            "total_cost_comparable": model not in drift_models,
        }
        for metric in metrics:
            m, s = mean_value(group[metric]), sample_std(group[metric])
            row[f"mean_{metric}"] = m
            row[f"std_{metric}"] = s
            row[f"cv_{metric}"] = cv(m, s)
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values("mean_total_runtime_sec", ascending=False, na_position="last")


def per_target_spread(df: pd.DataFrame, flag_cv: float) -> pd.DataFrame:
    rows = []
    for (model, target_id), group in df.groupby(["model", "target_id"], sort=True):
        m = mean_value(group["total_runtime_sec"])
        s = sample_std(group["total_runtime_sec"])
        mi = mean_value(group["inference_runtime_sec"])
        si = sample_std(group["inference_runtime_sec"])
        rows.append({
            "model": model,
            "target_id": target_id,
            "n_reps": int(group["rep"].nunique()),
            "mean_total_runtime_sec": m,
            "std_total_runtime_sec": s,
            "cv_total_runtime_sec": cv(m, s),
            "min_total_runtime_sec": float(group["total_runtime_sec"].min()),
            "max_total_runtime_sec": float(group["total_runtime_sec"].max()),
            "mean_inference_runtime_sec": mi,
            "std_inference_runtime_sec": si,
            "cv_inference_runtime_sec": cv(mi, si),
            "flagged_unstable": bool(cv(mi, si) > flag_cv) if not pd.isna(cv(mi, si)) else False,
        })
    out = pd.DataFrame(rows)
    return out.sort_values("cv_total_runtime_sec", ascending=False, na_position="last")


def accuracy_consistency(acc: pd.DataFrame, keep: set[tuple[str, str]], tol: float,
                         nondeterministic: set[str]) -> pd.DataFrame:
    if acc.empty:
        return pd.DataFrame()
    mask = acc.apply(lambda r: (r["target_id"], r["model"]) in keep, axis=1)
    acc = acc[mask]
    rows = []
    for (model, target_id), group in acc.groupby(["model", "target_id"], sort=True):
        values = pd.to_numeric(group["best_lddt_ca"], errors="coerce").dropna()
        if values.empty:
            continue
        spread = float(values.max() - values.min())
        exempt = model in nondeterministic
        rows.append({
            "model": model,
            "target_id": target_id,
            "n_reps": int(group["rep"].nunique()),
            "mean_best_lddt_ca": float(values.mean()),
            "std_best_lddt_ca": sample_std(values),
            "min_best_lddt_ca": float(values.min()),
            "max_best_lddt_ca": float(values.max()),
            "max_abs_dev_lddt_ca": spread,
            "tolerance": tol,
            "exempt_nondeterministic": exempt,
            "violation": bool(spread > tol and not exempt),
            "per_rep_values": "|".join(
                f"{r}={v:.6f}" for r, v in zip(group["rep"], group["best_lddt_ca"])
            ),
        })
    return pd.DataFrame(rows)


def benchmark_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Per-rep whole-benchmark cost, with the shared MSA counted once."""
    rows = []
    for rep, group in df.groupby("rep", sort=True):
        builders = group[group["msa_role"] == "builder"]
        entry = {
            "rep": rep,
            "n_models": int(group["model"].nunique()),
            "n_targets": int(group["target_id"].nunique()),
            "n_msa_builds_counted": int(len(builders)),
            "n_msa_recharges_excluded": int(((group["msa_role"] == "reuser") & group["msa_charged"]).sum()),
        }
        for inf_col, msa_col, total_col, label in (
            ("inference_runtime_sec", "msa_build_runtime_sec", "total_runtime_sec", "runtime_sec"),
            ("inference_energy_consumed_kwh", "msa_build_energy_consumed_kwh", "total_energy_consumed_kwh", "energy_kwh"),
            ("inference_carbon_emissions_g", "msa_build_carbon_emissions_g", "total_carbon_emissions_g", "co2_g"),
        ):
            inference = float(pd.to_numeric(group[inf_col], errors="coerce").fillna(0).sum())
            msa_dedup = float(pd.to_numeric(builders[msa_col], errors="coerce").fillna(0).sum())
            attributed = float(pd.to_numeric(group[total_col], errors="coerce").fillna(0).sum())
            entry[f"sum_inference_{label}"] = inference
            entry[f"sum_msa_build_dedup_{label}"] = msa_dedup
            entry[f"benchmark_incremental_{label}"] = inference + msa_dedup
            entry[f"sum_attributed_{label}_DO_NOT_SUM_ACROSS_MODELS"] = attributed
            entry[f"shared_msa_overcount_{label}"] = attributed - (inference + msa_dedup)
        rows.append(entry)
    return pd.DataFrame(rows)


def write_markdown(summary: pd.DataFrame, totals: pd.DataFrame, acc: pd.DataFrame,
                   drift: pd.DataFrame, dropped: pd.DataFrame, reps: list[str],
                   run_dirs: list[Path], tol: float, output: Path) -> None:
    def fmt(value: object, places: int = 5) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, (float, np.floating)):
            return f"{value:.{places}f}"
        return str(value)

    def pm(mean: object, std: object, scale: float = 1.0, places: int = 2) -> str:
        if pd.isna(mean):
            return ""
        if pd.isna(std):
            return f"{mean / scale:.{places}f}"
        return f"{mean / scale:.{places}f} ± {std / scale:.{places}f}"

    lines = [
        "# Cross-replicate cost summary",
        "",
        f"Replicates (n={len(reps)}): " + ", ".join(reps),
        "",
    ]
    for rep, run_dir in zip(reps, run_dirs):
        lines.append(f"- `{rep}` -> `{run_dir}`")
    lines += [
        "",
        "All mean ± std below are **across replicates**, not across targets.",
        "",
        "## Per-model cost",
        "",
        "Per-model cost is *attributed* cost: correct for comparing models to each other, "
        "but **not additive across models**, because the shared ColabFold/MMseqs2 MSA is "
        "built once and re-charged to every model that reuses it. For a whole-benchmark "
        "figure use `benchmark_incremental_*` in the next section.",
        "",
    ]
    headers = ["model", "n_reps", "msa_role", "total runtime (h)", "inference runtime (h)",
               "energy (kWh)", "CO2 (g)", "runtime CV"]
    lines += ["| " + " | ".join(headers) + " |",
              "| " + " | ".join(["---"] * len(headers)) + " |"]
    incomparable = []
    for _, row in summary.iterrows():
        comparable = bool(row.get("total_cost_comparable", True))
        if comparable:
            total_cell = pm(row["mean_total_runtime_sec"], row["std_total_runtime_sec"], 3600.0)
            energy_cell = pm(row["mean_total_energy_kwh"], row["std_total_energy_kwh"], 1.0, 4)
            co2_cell = pm(row["mean_total_co2_g"], row["std_total_co2_g"], 1.0, 1)
            cv_cell = fmt(row["cv_total_runtime_sec"], 4)
        else:
            total_cell = energy_cell = co2_cell = cv_cell = "not comparable †"
            incomparable.append(str(row["model"]))
        lines.append("| " + " | ".join([
            str(row["model"]),
            str(int(row["n_reps"])),
            str(row["msa_role"]),
            total_cell,
            pm(row["mean_inference_runtime_sec"], row["std_inference_runtime_sec"], 3600.0),
            energy_cell,
            co2_cell,
            cv_cell,
        ]) + " |")
    if incomparable:
        lines += [
            "",
            "† " + ", ".join(incomparable) + ": the shared MSA is charged in some replicates "
            "but not others (deliberate MSA reuse), so the *total* cost mixes accounting with "
            "machine variance and no mean ± std over reps is meaningful. The **inference** "
            "column is unaffected and is the comparable quantity for these models. Per-rep "
            "totals are in reps_per_rep_model_cost.csv.",
        ]

    lines += ["", "## Whole-benchmark cost per replicate (shared MSA counted once)", ""]
    t_headers = ["rep", "inference (h)", "MSA dedup (h)", "incremental total (h)",
                 "naive sum (h)", "overcount (h)", "CO2 incremental (g)"]
    lines += ["| " + " | ".join(t_headers) + " |",
              "| " + " | ".join(["---"] * len(t_headers)) + " |"]
    for _, row in totals.iterrows():
        lines.append("| " + " | ".join([
            str(row["rep"]),
            fmt(row["sum_inference_runtime_sec"] / 3600, 3),
            fmt(row["sum_msa_build_dedup_runtime_sec"] / 3600, 3),
            fmt(row["benchmark_incremental_runtime_sec"] / 3600, 3),
            fmt(row["sum_attributed_runtime_sec_DO_NOT_SUM_ACROSS_MODELS"] / 3600, 3),
            fmt(row["shared_msa_overcount_runtime_sec"] / 3600, 3),
            fmt(row["benchmark_incremental_co2_g"], 1),
        ]) + " |")

    lines += ["", "## Accuracy consistency across replicates", ""]
    if acc.empty:
        lines.append("No per-target scores found; accuracy consistency not checked.")
    else:
        violations = acc[acc["violation"]]
        lines.append(f"Tolerance on lDDT-Ca: {tol}. "
                     f"Fixed-seed GPU nondeterminism alone moves lDDT by ~1e-4.")
        lines.append("")
        for model, group in acc.groupby("model", sort=True):
            n_bad = int(group["violation"].sum())
            exempt = bool(group["exempt_nondeterministic"].any())
            worst = float(group["max_abs_dev_lddt_ca"].max())
            note = " (exempt: nondeterministic by design)" if exempt else ""
            verdict = "OK" if n_bad == 0 else f"{n_bad} VIOLATION(S)"
            lines.append(f"- **{model}**: {verdict}, max deviation {worst:.6f}{note}")
        if not violations.empty:
            lines += ["", "Violations:", ""]
            for _, row in violations.iterrows():
                lines.append(f"  - {row['model']} / {row['target_id']}: "
                             f"spread {row['max_abs_dev_lddt_ca']:.6f} ({row['per_rep_values']})")

    lines += ["", "## MSA attribution drift", ""]
    if drift.empty:
        lines.append("None: every model is charged the shared MSA consistently across reps.")
    else:
        for _, row in drift.iterrows():
            lines.append(f"- **{row['severity']}** {row['model']}: charged in "
                         f"[{row['charged_in_reps']}], uncharged in [{row['uncharged_in_reps']}]")

    lines += ["", "## Dropped (target, model) pairs", ""]
    if dropped.empty:
        lines.append("None: every pair succeeded in every replicate.")
    else:
        lines.append(f"{len(dropped)} pair(s) excluded because they did not succeed in all reps; "
                     "see reps_dropped_pairs.csv.")

    output.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate cost metrics across benchmark replicates.")
    parser.add_argument("--run-dirs", nargs="+", required=True,
                        help="Combine run directories, one per replicate.")
    parser.add_argument("--rep-labels", nargs="*", default=None,
                        help="Labels for each run dir (default: directory name).")
    parser.add_argument("--out-dir", default="results/replicate_summary")
    parser.add_argument("--lddt-tol", type=float, default=1e-3,
                        help="Max lDDT-Ca spread across reps before flagging (default 1e-3; "
                             "fixed-seed GPU nondeterminism alone is ~1e-4).")
    parser.add_argument("--runtime-cv-flag", type=float, default=0.25,
                        help="Per-target inference CV above which a target is flagged unstable.")
    parser.add_argument("--nondeterministic-models", default=DEFAULT_NONDETERMINISTIC,
                        help="Comma list exempt from the accuracy-consistency gate.")
    parser.add_argument("--expect-msa-reuse", default=DEFAULT_EXPECT_MSA_REUSE,
                        help="Comma list allowed to change MSA builder/reuser role between reps.")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if any violation, drift ERROR, or dropped pair is found.")
    args = parser.parse_args()

    run_dirs = [resolve(d) for d in args.run_dirs]
    for run_dir in run_dirs:
        if not run_dir.is_dir():
            raise SystemExit(f"Run directory not found: {run_dir}")
    if args.rep_labels:
        if len(args.rep_labels) != len(run_dirs):
            raise SystemExit("--rep-labels must have the same length as --run-dirs")
        reps = list(args.rep_labels)
    else:
        reps = [d.name for d in run_dirs]
    if len(set(reps)) != len(reps):
        raise SystemExit(f"Replicate labels must be unique, got: {reps}")
    if len(run_dirs) < 2:
        print("WARNING: fewer than 2 replicates; every std will be undefined.", file=sys.stderr)

    nondeterministic = {m.strip() for m in args.nondeterministic_models.split(",") if m.strip()}
    expect_reuse = {m.strip() for m in args.expect_msa_reuse.split(",") if m.strip()}

    manifests = [classify_msa_roles(load_manifest(d, r)) for d, r in zip(run_dirs, reps)]
    keep, dropped = intersect_reps(manifests)
    if not keep:
        raise SystemExit("No (target, model) pair succeeded in every replicate; nothing to compare.")
    print(f"Kept {len(keep)} (target, model) pairs present and successful in all {len(reps)} reps.")
    if not dropped.empty:
        print(f"WARNING: dropped {len(dropped)} pair(s) not successful in all reps.", file=sys.stderr)

    combined = pd.concat(manifests, ignore_index=True)
    combined = combined[combined.apply(lambda r: (r["target_id"], r["model"]) in keep, axis=1)]

    drift = attribution_drift(combined, expect_reuse)
    for _, row in drift.iterrows():
        stream = sys.stderr if row["severity"] == "ERROR" else sys.stdout
        print(f"{row['severity']}: model '{row['model']}' is charged the shared MSA in "
              f"[{row['charged_in_reps']}] but not in [{row['uncharged_in_reps']}]. "
              f"Cost statistics for this model mix accounting with machine variance.",
              file=stream)

    roles = {m: g["msa_role"].mode().iat[0] for m, g in combined.groupby("model")}
    drift_models = set(drift["model"]) if not drift.empty else set()
    per_rep = per_rep_model_cost(combined)
    summary = aggregate_across_reps(per_rep, roles, drift_models)
    spread = per_target_spread(combined, args.runtime_cv_flag)
    totals = benchmark_totals(combined)

    acc_frames = [load_accuracy(d, r) for d, r in zip(run_dirs, reps)]
    acc = accuracy_consistency(pd.concat(acc_frames, ignore_index=True), keep,
                               args.lddt_tol, nondeterministic)

    out_dir = resolve(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_dir / "reps_model_cost_summary.csv", index=False)
    per_rep.to_csv(out_dir / "reps_per_rep_model_cost.csv", index=False)
    spread.to_csv(out_dir / "reps_model_target_cost_spread.csv", index=False)
    totals.to_csv(out_dir / "reps_benchmark_cost_totals.csv", index=False)
    if not acc.empty:
        acc.to_csv(out_dir / "reps_accuracy_consistency.csv", index=False)
    if not dropped.empty:
        dropped.to_csv(out_dir / "reps_dropped_pairs.csv", index=False)
    if not drift.empty:
        drift.to_csv(out_dir / "reps_attribution_drift.csv", index=False)
    write_markdown(summary, totals, acc, drift, dropped, reps, run_dirs,
                   args.lddt_tol, out_dir / "reps_model_cost_summary.md")

    display = summary[["model", "n_reps", "msa_role", "mean_total_runtime_sec",
                       "std_total_runtime_sec", "cv_total_runtime_sec", "mean_total_co2_g"]]
    print(display.to_string(index=False))
    print(f"\nCross-replicate summary written to: {out_dir}")

    violations = 0 if acc.empty else int(acc["violation"].sum())
    errors = 0 if drift.empty else int((drift["severity"] == "ERROR").sum())
    if violations:
        print(f"WARNING: {violations} accuracy-consistency violation(s).", file=sys.stderr)
    if args.strict and (violations or errors or not dropped.empty):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
