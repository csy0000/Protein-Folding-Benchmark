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


def enabled_models_from_config(config_path: Path) -> list[str]:
    with config_path.open() as f:
        config = yaml.safe_load(f)

    models = config.get("models", {})
    return [name for name, cfg in models.items() if cfg.get("enabled", False)]


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
    args = parser.parse_args()

    reference = Path(args.reference)
    pred_dir = Path(args.pred_root) / args.target_id
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    resolved_tmalign_bin = resolve_tmalign_binary(args.tmalign_bin) if args.use_tmalign else None
    tmalign_missing_error = ""
    if args.use_tmalign and resolved_tmalign_bin is None:
        tmalign_missing_error = f"TM-align/US-align binary not found for --tmalign-bin {args.tmalign_bin}"

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
        active_names = set(enabled_models)
        all_dirs = sorted(path for path in pred_dir.iterdir() if path.is_dir())
        ignored_dirs = [path for path in all_dirs if path.name not in active_names]
        if ignored_dirs:
            warn("Ignoring non-enabled prediction directories:")
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
                    **tmalign_result,
                    "error": str(e),
                })
                continue

            rows.append({
                "target_id": args.target_id,
                "model": model_dir.name,
                "prediction": pdb.name,
                **diagnostics,
                "z_rmsd": np.nan,
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

    df = df.sort_values(["ca_rmsd", "model", "prediction"], na_position="last")

    suffix = f"_{args.output_suffix}" if args.output_suffix else ""
    out_csv = outdir / f"{args.target_id}_scores{suffix}.csv"
    df.to_csv(out_csv, index=False)

    print(df)
    print(f"Scores written to: {out_csv}")


if __name__ == "__main__":
    main()
