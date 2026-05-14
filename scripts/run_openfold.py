#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


PARAMETER_SUFFIXES = (".pt", ".pth", ".ckpt", ".npz")
DATABASE_CANDIDATES = {
    "uniref90": ("--uniref90_database_path", ("uniref90", "uniref90.fasta")),
    "mgnify": ("--mgnify_database_path", ("mgnify", "mgy_clusters_2018_12.fa")),
    "pdb70": ("--pdb70_database_path", ("pdb70", "pdb70")),
    "pdb_seqres": ("--pdb_seqres_database_path", ("pdb_seqres", "pdb_seqres.txt")),
    "uniref30": ("--uniref30_database_path", ("uniref30", "UniRef30_2021_03")),
    "uniclust30": ("--uniclust30_database_path", ("uniclust30", "uniclust30_2018_08", "uniclust30_2018_08")),
    "uniprot": ("--uniprot_database_path", ("uniprot", "uniprot.fasta")),
    "bfd": ("--bfd_database_path", ("bfd", "bfd_metaclust_clu_complete_id30_c90_final_seq.sorted_opt")),
    "obsolete_pdbs": ("--obsolete_pdbs_path", ("pdb_mmcif", "obsolete.dat")),
}


def read_fasta_sequence(path: Path) -> tuple[str, str]:
    header = path.stem
    parts: list[str] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            header = line[1:].strip() or header
            continue
        parts.append(line)
    sequence = "".join(parts)
    if not sequence:
        raise SystemExit(f"No sequence found in FASTA: {path}")
    return header, sequence


def write_fasta_dir(target_id: str, sequence: str, output_dir: Path) -> Path:
    fasta_dir = output_dir / "fasta"
    fasta_dir.mkdir(parents=True, exist_ok=True)
    fasta_path = fasta_dir / f"{target_id}.fasta"
    fasta_path.write_text(f">{target_id}\n{sequence}\n")
    return fasta_dir


def resolve_path(value: str | None, label: str, *, must_exist: bool = True) -> Path:
    if not value:
        raise SystemExit(
            "OpenFold is configured but not runnable. "
            "Please set OPENFOLD_REPO, OPENFOLD_PARAMS_DIR, and OPENFOLD_DATA_DIR, "
            "or disable openfold in configs/models.yaml."
        )
    path = Path(value).expanduser()
    if must_exist and not path.exists():
        raise SystemExit(f"{label} does not exist: {path}")
    return path


def find_parameter_file(params_dir: Path, config_preset: str, explicit_path: str | None) -> Path:
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"OpenFold parameter path does not exist: {path}")
        return path

    if params_dir.is_file():
        return params_dir

    preferred_names = [
        f"params_{config_preset}.npz",
        f"{config_preset}.npz",
        f"{config_preset}.pt",
        f"{config_preset}.pth",
        f"{config_preset}.ckpt",
    ]
    for name in preferred_names:
        candidate = params_dir / name
        if candidate.exists():
            return candidate

    candidates = sorted(path for path in params_dir.rglob("*") if path.suffix.lower() in PARAMETER_SUFFIXES)
    if not candidates:
        raise SystemExit(f"No OpenFold parameter/checkpoint file found under: {params_dir}")
    return candidates[0]


def default_template_mmcif_dir(data_dir: Path, explicit_path: str | None) -> Path:
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"OpenFold template mmCIF directory does not exist: {path}")
        return path

    candidates = [
        data_dir / "pdb_mmcif" / "mmcif_files",
        data_dir / "pdb_mmcif",
        data_dir / "mmcif_files",
        data_dir,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(f"No template mmCIF directory found under OPENFOLD_DATA_DIR: {data_dir}")


def add_if_exists(cmd: list[str], flag: str, path: Path) -> bool:
    if path.exists():
        cmd.extend([flag, str(path)])
        return True
    return False


def add_database_args(cmd: list[str], data_dir: Path) -> set[str]:
    found: set[str] = set()
    for name, (flag, parts) in DATABASE_CANDIDATES.items():
        if add_if_exists(cmd, flag, data_dir.joinpath(*parts)):
            found.add(name)
    return found


def validate_msa_databases(data_dir: Path, found: set[str], preset: str) -> None:
    required = {"uniref90", "mgnify", "pdb70"}
    if preset == "full_dbs":
        required.update({"bfd", "uniref30"})
    missing = sorted(required - found)
    if missing:
        expected = "\n".join(
            f"  {name}: {data_dir.joinpath(*DATABASE_CANDIDATES[name][1])}" for name in missing
        )
        raise SystemExit(
            "OpenFold MSA mode requires database paths that were not found under "
            f"OPENFOLD_DATA_DIR={data_dir}.\nMissing:\n{expected}\n"
            "Provide the full OpenFold/AlphaFold database tree or run an explicit "
            "single-sequence smoke test with --mode single_sequence."
        )


def structure_sort_key(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    for index in range(1, 100):
        if f"rank_{index:03d}" in name or f"model_{index}" in name or f"model_{index}_ptm" in name:
            return index, str(path)
    return 1000, str(path)


def standardize_outputs(raw_dir: Path, output_dir: Path, top_k: int, command: list[str]) -> None:
    structure_files = sorted(raw_dir.rglob("*.pdb"), key=structure_sort_key)
    selected = structure_files[:top_k]
    if not selected:
        discovered = "\n".join(str(path) for path in sorted(raw_dir.rglob("*")) if path.is_file())
        raise SystemExit(f"No OpenFold PDB output found under {raw_dir}.\nDiscovered files:\n{discovered}")

    for old_rank in output_dir.glob("rank_*.pdb"):
        old_rank.unlink()
    for index, src in enumerate(selected, start=1):
        shutil.copy2(src, output_dir / f"rank_{index:03d}.pdb")

    metadata = {
        "model": "openfold",
        "environment": "openfold",
        "top_k_requested": top_k,
        "top_k_generated": len(selected),
        "top_k_policy": "OpenFold inference outputs; use genuine generated structures only; no artificial duplication",
        "source_files": [str(path) for path in selected],
        "raw_output_dir": str(raw_dir),
        "command": command,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run optional OpenFold backend and standardize benchmark outputs.")
    parser.add_argument("--target-id")
    parser.add_argument("--sequence")
    parser.add_argument("--fasta-path")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--openfold-repo", default=os.environ.get("OPENFOLD_REPO", "models/openfold"))
    parser.add_argument("--params-dir", default=os.environ.get("OPENFOLD_PARAMS_DIR", ""))
    parser.add_argument("--data-dir", default=os.environ.get("OPENFOLD_DATA_DIR", ""))
    parser.add_argument("--param-path", default=os.environ.get("OPENFOLD_PARAM_PATH"))
    parser.add_argument("--template-mmcif-dir", default=os.environ.get("OPENFOLD_TEMPLATE_MMCIF_DIR", ""))
    parser.add_argument("--use-precomputed-alignments", default=os.environ.get("OPENFOLD_PRECOMPUTED_ALIGNMENTS", ""))
    parser.add_argument("--num-models", type=int, default=1)
    parser.add_argument("--max-template-date", default=os.environ.get("OPENFOLD_MAX_TEMPLATE_DATE", "2026-05-14"))
    parser.add_argument("--device", default=os.environ.get("OPENFOLD_DEVICE", "cpu"))
    parser.add_argument("--config-preset", default=os.environ.get("OPENFOLD_CONFIG_PRESET", "model_1"))
    parser.add_argument("--cpus", type=int, default=int(os.environ.get("OPENFOLD_CPUS", "4")))
    parser.add_argument("--preset", choices=["full_dbs", "reduced_dbs"], default=os.environ.get("OPENFOLD_DB_PRESET", "full_dbs"))
    parser.add_argument("--mode", choices=["msa", "single_sequence"], default=os.environ.get("OPENFOLD_MODE", "msa"))
    parser.add_argument("--use-single-seq-mode", action="store_true")
    parser.add_argument("--skip-relaxation", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if args.fasta_path:
        fasta_path = Path(args.fasta_path).resolve()
        target_id, sequence = read_fasta_sequence(fasta_path)
    elif args.sequence:
        target_id = args.target_id or "openfold_target"
        sequence = args.sequence
    else:
        raise SystemExit("Provide --fasta-path or --sequence for OpenFold inference.")

    if args.target_id:
        target_id = args.target_id

    fasta_dir = write_fasta_dir(target_id, sequence, output_dir)
    repo_dir = resolve_path(args.openfold_repo, "OPENFOLD_REPO").resolve()
    params_dir = resolve_path(args.params_dir, "OPENFOLD_PARAMS_DIR").resolve()
    data_dir = resolve_path(args.data_dir, "OPENFOLD_DATA_DIR").resolve()
    run_script = repo_dir / "run_pretrained_openfold.py"
    if not run_script.exists():
        raise SystemExit(f"OpenFold inference script not found: {run_script}")

    parameter_file = find_parameter_file(params_dir, args.config_preset, args.param_path)
    use_single_sequence = args.mode == "single_sequence" or args.use_single_seq_mode
    found_databases: set[str] = set()
    if args.use_precomputed_alignments and args.mode == "msa":
        raise SystemExit(
            "--use-precomputed-alignments is not accepted in OpenFold MSA mode. "
            "Provide real database paths under OPENFOLD_DATA_DIR or set --mode single_sequence "
            "for the smoke-test path."
        )
    if not args.use_precomputed_alignments and args.mode == "msa":
        found_databases = {
            name
            for name, (_, parts) in DATABASE_CANDIDATES.items()
            if data_dir.joinpath(*parts).exists()
        }
        validate_msa_databases(data_dir, found_databases, args.preset)
    template_mmcif_dir = default_template_mmcif_dir(data_dir, args.template_mmcif_dir)

    cmd = [
        sys.executable,
        str(run_script),
        str(fasta_dir),
        str(template_mmcif_dir),
        "--output_dir",
        str(raw_dir),
        "--model_device",
        args.device,
        "--config_preset",
        args.config_preset,
        "--cpus",
        str(args.cpus),
        "--preset",
        args.preset,
        "--max_template_date",
        args.max_template_date,
    ]

    if parameter_file.suffix.lower() == ".npz":
        cmd.extend(["--jax_param_path", str(parameter_file)])
    else:
        cmd.extend(["--openfold_checkpoint_path", str(parameter_file)])

    if args.skip_relaxation:
        cmd.append("--skip_relaxation")
    if use_single_sequence:
        cmd.append("--use_single_seq_mode")
    if args.use_precomputed_alignments:
        precomputed_alignments = Path(args.use_precomputed_alignments).expanduser().resolve()
        if not precomputed_alignments.exists():
            raise SystemExit(f"OpenFold precomputed alignment directory does not exist: {precomputed_alignments}")
        (precomputed_alignments / target_id).mkdir(parents=True, exist_ok=True)
        cmd.extend(["--use_precomputed_alignments", str(precomputed_alignments)])
    else:
        add_database_args(cmd, data_dir)

    try:
        subprocess.run(cmd, check=True, cwd=repo_dir)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "OpenFold inference failed. Check that the openfold conda environment has "
            "PyTorch/OpenFold installed and that OPENFOLD_REPO, OPENFOLD_PARAMS_DIR, "
            f"and OPENFOLD_DATA_DIR are valid. Exit code: {exc.returncode}"
        ) from exc

    standardize_outputs(raw_dir, output_dir, args.num_models, cmd)
    print(f"OpenFold standardized outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
