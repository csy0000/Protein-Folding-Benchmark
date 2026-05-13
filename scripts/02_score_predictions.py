#!/usr/bin/env python3

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from Bio.PDB import PDBParser, Superimposer


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


def ca_diagnostics(reference_pdb: Path, predicted_pdb: Path, ref_chain: str | None, pred_chain: str | None) -> dict[str, object]:
    ref_keys, ref_atoms = get_ca_atoms(reference_pdb, ref_chain)
    pred_keys, pred_atoms = get_ca_atoms(predicted_pdb, pred_chain)

    ref_map = dict(zip(ref_keys, ref_atoms))
    pred_map = dict(zip(pred_keys, pred_atoms))

    common_keys = [k for k in ref_keys if k in pred_map]
    missing_ref = [k for k in ref_keys if k not in pred_map]
    missing_pred = [k for k in pred_keys if k not in ref_map]

    if len(common_keys) < 3:
        raise ValueError(f"Too few matched C-alpha atoms for {predicted_pdb}")

    fixed = [ref_map[k] for k in common_keys]
    moving = [pred_map[k] for k in common_keys]

    sup = Superimposer()
    sup.set_atoms(fixed, moving)
    return {
        "n_ref_ca": len(ref_keys),
        "n_pred_ca": len(pred_keys),
        "n_aligned_ca": len(common_keys),
        "missing_ref_resseq": format_missing(missing_ref),
        "missing_pred_resseq": format_missing(missing_pred),
        "ca_rmsd": float(sup.rms),
    }


def empty_diagnostics() -> dict[str, object]:
    return {
        "n_ref_ca": np.nan,
        "n_pred_ca": np.nan,
        "n_aligned_ca": np.nan,
        "missing_ref_resseq": "",
        "missing_pred_resseq": "",
        "ca_rmsd": np.nan,
        "z_rmsd": np.nan,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--pred-root", default="data/predictions")
    parser.add_argument("--outdir", default="data/scores")
    parser.add_argument("--ref-chain", default=None)
    parser.add_argument("--pred-chain", default=None)
    args = parser.parse_args()

    reference = Path(args.reference)
    pred_dir = Path(args.pred_root) / args.target_id
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    columns = [
        "target_id",
        "model",
        "prediction",
        "n_ref_ca",
        "n_pred_ca",
        "n_aligned_ca",
        "missing_ref_resseq",
        "missing_pred_resseq",
        "ca_rmsd",
        "z_rmsd",
        "error",
    ]

    if pred_dir.exists():
        model_dirs = sorted(path for path in pred_dir.iterdir() if path.is_dir())
    else:
        model_dirs = []

    for model_dir in model_dirs:
        for pdb in sorted(model_dir.glob("*.pdb")):
            try:
                diagnostics = ca_diagnostics(reference, pdb, args.ref_chain, args.pred_chain)
            except Exception as e:
                rows.append({
                    "target_id": args.target_id,
                    "model": model_dir.name,
                    "prediction": pdb.name,
                    **empty_diagnostics(),
                    "error": str(e),
                })
                continue

            rows.append({
                "target_id": args.target_id,
                "model": model_dir.name,
                "prediction": pdb.name,
                **diagnostics,
                "z_rmsd": np.nan,
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

    out_csv = outdir / f"{args.target_id}_scores.csv"
    df.to_csv(out_csv, index=False)

    print(df)
    print(f"Scores written to: {out_csv}")


if __name__ == "__main__":
    main()
