#!/usr/bin/env python3

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from Bio.PDB import PDBParser, Superimposer


TMALIGN_BIN_CANDIDATES = ["USalign", "TMalign", "TM-align", "tmalign"]
GDTTM_BIN_CANDIDATES = ["TMscore"]
GDT_CUTOFFS = (1.0, 2.0, 4.0, 8.0)


def get_ca_atoms(pdb_path: Path, chain_id: str | None):
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure(pdb_path.stem, str(pdb_path))

    atoms = []
    residue_keys = []

    for model in structure:
        for chain in model:
            if chain_id and chain.id != chain_id:
                continue
            for residue in chain:
                if "CA" in residue:
                    hetflag, resseq, icode = residue.id
                    if hetflag == " ":
                        atoms.append(residue["CA"])
                        residue_keys.append(resseq)
        break

    return residue_keys, atoms


def format_missing(resseqs: list[int]) -> str:
    return ";".join(str(resseq) for resseq in resseqs)


def ca_diagnostics(
    reference_pdb: Path,
    predicted_pdb: Path,
    ref_chain: str | None,
    pred_chain: str | None,
    match_mode: str,
) -> dict[str, object]:
    ref_keys, ref_atoms = get_ca_atoms(reference_pdb, ref_chain)
    pred_keys, pred_atoms = get_ca_atoms(predicted_pdb, pred_chain)

    if match_mode == "sequential":
        n_aligned = min(len(ref_atoms), len(pred_atoms))
        common_keys = list(range(n_aligned))
        missing_ref = ref_keys[n_aligned:]
        missing_pred = pred_keys[n_aligned:]
        fixed = ref_atoms[:n_aligned]
        moving = pred_atoms[:n_aligned]
    else:
        ref_map = dict(zip(ref_keys, ref_atoms))
        pred_map = dict(zip(pred_keys, pred_atoms))

        common_keys = [k for k in ref_keys if k in pred_map]
        missing_ref = [k for k in ref_keys if k not in pred_map]
        missing_pred = [k for k in pred_keys if k not in ref_map]
        fixed = [ref_map[k] for k in common_keys]
        moving = [pred_map[k] for k in common_keys]

    if len(common_keys) < 3:
        raise ValueError(f"Too few matched C-alpha atoms for {predicted_pdb}")

    sup = Superimposer()
    sup.set_atoms(fixed, moving)
    return {
        "match_mode": match_mode,
        "n_ref_ca": len(ref_keys),
        "n_pred_ca": len(pred_keys),
        "n_aligned_ca": len(common_keys),
        "missing_ref_resseq": format_missing(missing_ref),
        "missing_pred_resseq": format_missing(missing_pred),
        "ca_rmsd": float(sup.rms),
    }


def empty_lddt_result(error: str = "") -> dict[str, object]:
    return {
        "lddt_ca": np.nan,
        "lddt_ca_n_pairs": 0,
        "lddt_ca_cutoff": np.nan,
        "lddt_ca_f_0p5": np.nan,
        "lddt_ca_f_1p0": np.nan,
        "lddt_ca_f_2p0": np.nan,
        "lddt_ca_f_4p0": np.nan,
        "lddt_ca_error": error,
    }


def matched_ca_atoms(
    reference_pdb: Path,
    predicted_pdb: Path,
    ref_chain: str | None,
    pred_chain: str | None,
    match_mode: str,
) -> tuple[list[object], list[object]]:
    ref_keys, ref_atoms = get_ca_atoms(reference_pdb, ref_chain)
    pred_keys, pred_atoms = get_ca_atoms(predicted_pdb, pred_chain)

    if match_mode == "sequential":
        n_aligned = min(len(ref_atoms), len(pred_atoms))
        return ref_atoms[:n_aligned], pred_atoms[:n_aligned]

    pred_map = dict(zip(pred_keys, pred_atoms))
    common_keys = [k for k in ref_keys if k in pred_map]
    ref_map = dict(zip(ref_keys, ref_atoms))
    return [ref_map[k] for k in common_keys], [pred_map[k] for k in common_keys]


def lddt_ca_score(
    reference_pdb: Path,
    predicted_pdb: Path,
    ref_chain: str | None,
    pred_chain: str | None,
    match_mode: str,
    cutoff: float,
) -> dict[str, object]:
    ref_atoms, pred_atoms = matched_ca_atoms(reference_pdb, predicted_pdb, ref_chain, pred_chain, match_mode)
    if len(ref_atoms) < 2:
        return empty_lddt_result("fewer than two matched C-alpha atoms") | {"lddt_ca_cutoff": cutoff}

    ref_coords = np.asarray([atom.coord for atom in ref_atoms], dtype=float)
    pred_coords = np.asarray([atom.coord for atom in pred_atoms], dtype=float)

    ref_deltas = ref_coords[:, None, :] - ref_coords[None, :, :]
    pred_deltas = pred_coords[:, None, :] - pred_coords[None, :, :]
    ref_distances = np.linalg.norm(ref_deltas, axis=2)
    pred_distances = np.linalg.norm(pred_deltas, axis=2)

    pair_mask = np.triu(ref_distances < cutoff, k=1)
    n_pairs = int(pair_mask.sum())
    if n_pairs == 0:
        return empty_lddt_result("no reference C-alpha pairs within cutoff") | {"lddt_ca_cutoff": cutoff}

    errors = np.abs(pred_distances[pair_mask] - ref_distances[pair_mask])
    fractions = {
        "lddt_ca_f_0p5": float(np.mean(errors < 0.5)),
        "lddt_ca_f_1p0": float(np.mean(errors < 1.0)),
        "lddt_ca_f_2p0": float(np.mean(errors < 2.0)),
        "lddt_ca_f_4p0": float(np.mean(errors < 4.0)),
    }
    return {
        "lddt_ca": float(0.25 * sum(fractions.values())),
        "lddt_ca_n_pairs": n_pairs,
        "lddt_ca_cutoff": cutoff,
        **fractions,
        "lddt_ca_error": "",
    }


def empty_diagnostics() -> dict[str, object]:
    return {
        "match_mode": "",
        "n_ref_ca": np.nan,
        "n_pred_ca": np.nan,
        "n_aligned_ca": np.nan,
        "missing_ref_resseq": "",
        "missing_pred_resseq": "",
        "ca_rmsd": np.nan,
        "z_rmsd": np.nan,
    }


def empty_tmalign_result(available: bool, binary: str, error: str = "") -> dict[str, object]:
    return {
        "tmalign_available": available,
        "tmalign_bin": binary,
        "tmalign_rmsd": np.nan,
        "tmalign_tm_score_ref": np.nan,
        "tmalign_tm_score_pred": np.nan,
        "tmalign_aligned_length": np.nan,
        "tmalign_seq_id": np.nan,
        "tmalign_error": error,
    }


def resolve_tmalign_binary(tmalign_bin: str) -> str | None:
    if tmalign_bin != "auto":
        return tmalign_bin if shutil.which(tmalign_bin) or Path(tmalign_bin).exists() else None

    for candidate in TMALIGN_BIN_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def parse_tmalign_stdout(stdout: str) -> tuple[dict[str, object], list[str]]:
    result: dict[str, object] = {
        "tmalign_rmsd": np.nan,
        "tmalign_tm_score_ref": np.nan,
        "tmalign_tm_score_pred": np.nan,
        "tmalign_aligned_length": np.nan,
        "tmalign_seq_id": np.nan,
    }
    errors: list[str] = []

    aligned_match = re.search(
        r"Aligned\s+length\s*=\s*(\d+)\s*,\s*RMSD\s*=\s*([0-9.+\-Ee]+)\s*,\s*Seq_ID.*?=\s*([0-9.+\-Ee]+)",
        stdout,
    )
    if aligned_match:
        result["tmalign_aligned_length"] = int(aligned_match.group(1))
        result["tmalign_rmsd"] = float(aligned_match.group(2))
        result["tmalign_seq_id"] = float(aligned_match.group(3))
    else:
        errors.append("Could not parse aligned length/RMSD/Seq_ID")

    tm_score_matches = re.findall(
        r"TM-score\s*=\s*([0-9.+\-Ee]+)\s*\((?:if\s+)?normalized by length of (?:Chain_|Structure_)([12])",
        stdout,
    )
    if tm_score_matches:
        for score, chain_number in tm_score_matches:
            if chain_number == "1":
                result["tmalign_tm_score_pred"] = float(score)
            elif chain_number == "2":
                result["tmalign_tm_score_ref"] = float(score)
    else:
        fallback_scores = re.findall(r"TM-score\s*=\s*([0-9.+\-Ee]+)", stdout)
        if len(fallback_scores) >= 1:
            result["tmalign_tm_score_pred"] = float(fallback_scores[0])
        if len(fallback_scores) >= 2:
            result["tmalign_tm_score_ref"] = float(fallback_scores[1])
        if not fallback_scores:
            errors.append("Could not parse TM-score")

    return result, errors


def run_tmalign(reference_pdb: Path, prediction_pdb: Path, binary: str) -> dict[str, object]:
    completed = subprocess.run(
        [binary, str(prediction_pdb), str(reference_pdb)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"TM-align exited {completed.returncode}"
        return empty_tmalign_result(True, binary, message)

    parsed, parse_errors = parse_tmalign_stdout(completed.stdout)
    return {
        "tmalign_available": True,
        "tmalign_bin": binary,
        **parsed,
        "tmalign_error": "; ".join(parse_errors),
    }


def empty_gdt_ts_result(method: str = "unavailable", error: str = "") -> dict[str, object]:
    return {
        "gdt_ts": np.nan,
        "gdt_ts_percent": np.nan,
        "gdt_p1": np.nan,
        "gdt_p2": np.nan,
        "gdt_p4": np.nan,
        "gdt_p8": np.nan,
        "gdt_ts_method": method,
        "gdt_ts_error": error,
    }


def resolve_gdt_ts_binary(gdt_ts_bin: str) -> str | None:
    if gdt_ts_bin != "auto":
        return gdt_ts_bin if shutil.which(gdt_ts_bin) or Path(gdt_ts_bin).exists() else None
    for candidate in GDTTM_BIN_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def parse_tmscore_gdt_stdout(stdout: str) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    result = empty_gdt_ts_result("external_tmscore", "")
    match = re.search(
        r"GDT-TS-score\s*=\s*([0-9.+\-Ee]+)\s+%\(d<1\)\s*=\s*([0-9.+\-Ee]+)\s+%\(d<2\)\s*=\s*([0-9.+\-Ee]+)\s+%\(d<4\)\s*=\s*([0-9.+\-Ee]+)\s+%\(d<8\)\s*=\s*([0-9.+\-Ee]+)",
        stdout,
    )
    if not match:
        match = re.search(
            r"GDT[_-]?TS(?:-score)?\s*=\s*([0-9.+\-Ee]+).*?d<1\)?\s*=\s*([0-9.+\-Ee]+).*?d<2\)?\s*=\s*([0-9.+\-Ee]+).*?d<4\)?\s*=\s*([0-9.+\-Ee]+).*?d<8\)?\s*=\s*([0-9.+\-Ee]+)",
            stdout,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if not match:
        return result | {"gdt_ts_error": "Could not parse GDT_TS from TMscore output"}, ["Could not parse GDT_TS"]
    values = [float(match.group(i)) for i in range(1, 6)]
    if any(value > 1.0 for value in values):
        values = [value / 100.0 for value in values]
    gdt_ts, p1, p2, p4, p8 = values
    return {
        "gdt_ts": gdt_ts,
        "gdt_ts_percent": 100.0 * gdt_ts,
        "gdt_p1": p1,
        "gdt_p2": p2,
        "gdt_p4": p4,
        "gdt_p8": p8,
        "gdt_ts_method": "external_tmscore",
        "gdt_ts_error": "",
    }, errors


def run_tmscore_gdt(reference_pdb: Path, prediction_pdb: Path, binary: str) -> dict[str, object]:
    completed = subprocess.run(
        [binary, str(prediction_pdb), str(reference_pdb)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"TMscore exited {completed.returncode}"
        return empty_gdt_ts_result("external_tmscore", message)
    parsed, parse_errors = parse_tmscore_gdt_stdout(completed.stdout)
    if parse_errors and not parsed.get("gdt_ts_error"):
        parsed["gdt_ts_error"] = "; ".join(parse_errors)
    return parsed


def kabsch_transform(moving: np.ndarray, fixed: np.ndarray) -> np.ndarray:
    moving_centroid = moving.mean(axis=0)
    fixed_centroid = fixed.mean(axis=0)
    moving_centered = moving - moving_centroid
    fixed_centered = fixed - fixed_centroid
    covariance = moving_centered.T @ fixed_centered
    v, _, wt = np.linalg.svd(covariance)
    correction = np.eye(3)
    if np.linalg.det(v @ wt) < 0:
        correction[-1, -1] = -1
    rotation = v @ correction @ wt
    return moving_centered @ rotation + fixed_centroid


def iterative_gdt_fraction(ref_coords: np.ndarray, pred_coords: np.ndarray, cutoff: float) -> float:
    active = np.ones(len(ref_coords), dtype=bool)
    best_fraction = 0.0
    for _ in range(20):
        if int(active.sum()) < 3:
            break
        # Refit on active subset, then apply that transform to all atoms.
        moving_centroid = pred_coords[active].mean(axis=0)
        fixed_centroid = ref_coords[active].mean(axis=0)
        moving_centered = pred_coords[active] - moving_centroid
        fixed_centered = ref_coords[active] - fixed_centroid
        covariance = moving_centered.T @ fixed_centered
        v, _, wt = np.linalg.svd(covariance)
        correction = np.eye(3)
        if np.linalg.det(v @ wt) < 0:
            correction[-1, -1] = -1
        rotation = v @ correction @ wt
        transformed = (pred_coords - moving_centroid) @ rotation + fixed_centroid
        distances = np.linalg.norm(transformed - ref_coords, axis=1)
        new_active = distances <= cutoff
        best_fraction = max(best_fraction, float(new_active.mean()))
        if np.array_equal(new_active, active):
            break
        active = new_active
    return best_fraction


def internal_gdt_ts_score(
    reference_pdb: Path,
    predicted_pdb: Path,
    ref_chain: str | None,
    pred_chain: str | None,
    match_mode: str,
) -> dict[str, object]:
    ref_atoms, pred_atoms = matched_ca_atoms(reference_pdb, predicted_pdb, ref_chain, pred_chain, match_mode)
    if len(ref_atoms) < 3:
        return empty_gdt_ts_result("internal_iterative_ca", "fewer than three matched C-alpha atoms")
    ref_coords = np.asarray([atom.coord for atom in ref_atoms], dtype=float)
    pred_coords = np.asarray([atom.coord for atom in pred_atoms], dtype=float)
    fractions = [iterative_gdt_fraction(ref_coords, pred_coords, cutoff) for cutoff in GDT_CUTOFFS]
    gdt_ts = float(np.mean(fractions))
    return {
        "gdt_ts": gdt_ts,
        "gdt_ts_percent": 100.0 * gdt_ts,
        "gdt_p1": fractions[0],
        "gdt_p2": fractions[1],
        "gdt_p4": fractions[2],
        "gdt_p8": fractions[3],
        "gdt_ts_method": "internal_iterative_ca",
        "gdt_ts_error": "",
    }


def gdt_ts_score(
    reference_pdb: Path,
    predicted_pdb: Path,
    ref_chain: str | None,
    pred_chain: str | None,
    match_mode: str,
    method: str,
    binary: str | None,
    requested_bin: str,
) -> dict[str, object]:
    external_error = ""
    if method in {"auto", "external"}:
        if binary:
            external = run_tmscore_gdt(reference_pdb, predicted_pdb, binary)
            if not str(external.get("gdt_ts_error", "")).strip():
                return external
            external_error = str(external.get("gdt_ts_error", ""))
        else:
            external_error = f"TMscore binary not found for --gdt-ts-bin {requested_bin}"
        if method == "external":
            return empty_gdt_ts_result("external_tmscore", external_error)
    if method in {"auto", "internal"}:
        internal = internal_gdt_ts_score(reference_pdb, predicted_pdb, ref_chain, pred_chain, match_mode)
        if external_error and not str(internal.get("gdt_ts_error", "")).strip():
            internal["gdt_ts_error"] = f"external unavailable: {external_error}; used internal fallback"
        return internal
    return empty_gdt_ts_result("unavailable", f"unsupported GDT_TS method: {method}")


def enabled_models_from_config(config_path: Path) -> list[str]:
    with config_path.open() as f:
        config = yaml.safe_load(f)

    models = config.get("models", {})
    return [name for name, cfg in models.items() if cfg.get("enabled", False)]


def parse_model_list(models: str) -> list[str]:
    return [name.strip() for name in models.split(",") if name.strip()]


def warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--pred-root", default="data/predictions")
    parser.add_argument("--outdir", default="data/scores")
    parser.add_argument("--ref-chain", default=None)
    parser.add_argument("--pred-chain", default=None)
    parser.add_argument("--match-mode", choices=["sequential", "resseq"], default="sequential")
    parser.add_argument("--use-tmalign", action="store_true")
    parser.add_argument("--tmalign-bin", default="auto")
    parser.add_argument("--output-suffix", default="")
    parser.add_argument("--config", default="configs/models.yaml")
    parser.add_argument("--only-enabled-models", action="store_true")
    parser.add_argument("--models", default="", help="Comma-separated model IDs to score, in config order where applicable.")
    parser.add_argument("--lddt-cutoff", type=float, default=15.0)
    parser.add_argument("--disable-lddt", action="store_true")
    parser.add_argument("--use-gdt-ts", action="store_true", default=True)
    parser.add_argument("--no-gdt-ts", action="store_false", dest="use_gdt_ts")
    parser.add_argument("--gdt-ts-method", choices=["auto", "external", "internal"], default="auto")
    parser.add_argument("--gdt-ts-bin", default="auto")
    args = parser.parse_args()

    reference = Path(args.reference)
    pred_dir = Path(args.pred_root) / args.target_id
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    resolved_tmalign_bin = resolve_tmalign_binary(args.tmalign_bin) if args.use_tmalign else None
    tmalign_missing_error = ""
    if args.use_tmalign and resolved_tmalign_bin is None:
        tmalign_missing_error = f"TM-align/US-align binary not found for --tmalign-bin {args.tmalign_bin}"
    resolved_gdt_ts_bin = resolve_gdt_ts_binary(args.gdt_ts_bin) if args.use_gdt_ts else None

    rows = []
    columns = [
        "target_id",
        "model",
        "prediction",
        "match_mode",
        "n_ref_ca",
        "n_pred_ca",
        "n_aligned_ca",
        "missing_ref_resseq",
        "missing_pred_resseq",
        "ca_rmsd",
        "z_rmsd",
        "lddt_ca",
        "lddt_ca_n_pairs",
        "lddt_ca_cutoff",
        "lddt_ca_f_0p5",
        "lddt_ca_f_1p0",
        "lddt_ca_f_2p0",
        "lddt_ca_f_4p0",
        "lddt_ca_error",
        "gdt_ts",
        "gdt_ts_percent",
        "gdt_p1",
        "gdt_p2",
        "gdt_p4",
        "gdt_p8",
        "gdt_ts_method",
        "gdt_ts_error",
        "tmalign_available",
        "tmalign_bin",
        "tmalign_rmsd",
        "tmalign_tm_score_ref",
        "tmalign_tm_score_pred",
        "tmalign_aligned_length",
        "tmalign_seq_id",
        "tmalign_error",
        "error",
    ]

    if not pred_dir.exists():
        model_dirs = []
    elif args.only_enabled_models:
        enabled_models = enabled_models_from_config(Path(args.config))
        requested_models = parse_model_list(args.models)
        if requested_models:
            unknown = [name for name in requested_models if name not in enabled_models]
            if unknown:
                raise SystemExit(f"Requested model(s) are not enabled in {args.config}: {', '.join(unknown)}")
            requested_names = set(requested_models)
            enabled_models = [name for name in enabled_models if name in requested_names]
        active_names = set(enabled_models)
        all_dirs = sorted(path for path in pred_dir.iterdir() if path.is_dir())
        ignored_dirs = [path for path in all_dirs if path.name not in active_names]
        if ignored_dirs:
            warn("Ignoring prediction directories outside active model set:")
            for path in ignored_dirs:
                print(f"  {path}", file=sys.stderr)

        model_dirs = []
        for model_name in enabled_models:
            model_dir = pred_dir / model_name
            if not model_dir.exists():
                warn(f"Enabled model has no prediction directory: {model_dir}")
                continue
            if not list(model_dir.glob("rank_*.pdb")):
                warn(f"Enabled model has no rank_*.pdb predictions: {model_dir}")
                continue
            model_dirs.append(model_dir)
    else:
        model_dirs = sorted(path for path in pred_dir.iterdir() if path.is_dir())

    for model_dir in model_dirs:
        for pdb in sorted(model_dir.glob("rank_*.pdb")):
            if args.use_tmalign and resolved_tmalign_bin:
                tmalign_result = run_tmalign(reference, pdb, resolved_tmalign_bin)
            elif args.use_tmalign:
                tmalign_result = empty_tmalign_result(False, args.tmalign_bin, tmalign_missing_error)
            else:
                tmalign_result = empty_tmalign_result(False, "", "")

            try:
                diagnostics = ca_diagnostics(reference, pdb, args.ref_chain, args.pred_chain, args.match_mode)
            except Exception as e:
                rows.append({
                    "target_id": args.target_id,
                    "model": model_dir.name,
                    "prediction": pdb.name,
                    **empty_diagnostics(),
                    **(empty_lddt_result("disabled" if args.disable_lddt else str(e)) | {"lddt_ca_cutoff": args.lddt_cutoff}),
                    **empty_gdt_ts_result("disabled" if not args.use_gdt_ts else "unavailable", "disabled" if not args.use_gdt_ts else str(e)),
                    **tmalign_result,
                    "error": str(e),
                })
                continue

            if args.disable_lddt:
                lddt_result = empty_lddt_result("disabled")
            else:
                try:
                    lddt_result = lddt_ca_score(
                        reference,
                        pdb,
                        args.ref_chain,
                        args.pred_chain,
                        args.match_mode,
                        args.lddt_cutoff,
                    )
                except Exception as e:
                    lddt_result = empty_lddt_result(str(e)) | {"lddt_ca_cutoff": args.lddt_cutoff}

            if args.use_gdt_ts:
                try:
                    gdt_ts_result = gdt_ts_score(
                        reference,
                        pdb,
                        args.ref_chain,
                        args.pred_chain,
                        args.match_mode,
                        args.gdt_ts_method,
                        resolved_gdt_ts_bin,
                        args.gdt_ts_bin,
                    )
                except Exception as e:
                    gdt_ts_result = empty_gdt_ts_result("unavailable", str(e))
            else:
                gdt_ts_result = empty_gdt_ts_result("disabled", "disabled")

            rows.append({
                "target_id": args.target_id,
                "model": model_dir.name,
                "prediction": pdb.name,
                **diagnostics,
                "z_rmsd": np.nan,
                **lddt_result,
                **gdt_ts_result,
                **tmalign_result,
                "error": "",
            })

    df = pd.DataFrame(rows, columns=columns)

    valid = df["ca_rmsd"].dropna()
    if len(valid) >= 2:
        mean = valid.mean()
        std = valid.std(ddof=1)
        if std > 0:
            df["z_rmsd"] = (df["ca_rmsd"] - mean) / std

    df = df.sort_values(
        ["lddt_ca", "tmalign_tm_score_ref", "tmalign_rmsd", "ca_rmsd", "model", "prediction"],
        ascending=[False, False, True, True, True, True],
        na_position="last",
    )

    suffix = f"_{args.output_suffix}" if args.output_suffix else ""
    out_csv = outdir / f"{args.target_id}_scores{suffix}.csv"
    df.to_csv(out_csv, index=False)

    print(df)
    print(f"Scores written to: {out_csv}")


if __name__ == "__main__":
    main()
