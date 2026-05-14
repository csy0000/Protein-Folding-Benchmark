#!/usr/bin/env python3

import argparse
import json
import shutil
from pathlib import Path

import gemmi


STRUCTURE_SUFFIXES = {".pdb", ".cif", ".mmcif"}


def find_structure_files(input_dir: Path, output_dir: Path) -> list[Path]:
    output_dir = output_dir.resolve()
    candidates: list[Path] = []
    for path in input_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in STRUCTURE_SUFFIXES:
            continue
        if path.resolve().is_relative_to(output_dir) and path.name.startswith("rank_"):
            continue
        candidates.append(path)
    return sorted(candidates, key=lambda p: str(p.relative_to(input_dir)))


def convert_to_pdb(src: Path, dst: Path) -> None:
    if src.suffix.lower() == ".pdb":
        shutil.copy2(src, dst)
        return

    structure = gemmi.read_structure(str(src))
    structure.write_pdb(str(dst))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k", type=int, required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--top-k-policy", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_files = find_structure_files(input_dir, output_dir)
    selected = source_files[: args.top_k]

    for old_rank in output_dir.glob("rank_*.pdb"):
        old_rank.unlink()

    for index, src in enumerate(selected, start=1):
        dst = output_dir / f"rank_{index:03d}.pdb"
        convert_to_pdb(src, dst)

    metadata = {
        "model": args.model_name,
        "environment": args.environment,
        "top_k_requested": args.top_k,
        "top_k_generated": len(selected),
        "top_k_policy": args.top_k_policy,
        "source_files": [str(path) for path in selected],
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

    if not selected:
        print(f"No structure files found under {input_dir}.")
        print("Discovered files:")
        for path in sorted(p for p in input_dir.rglob("*") if p.is_file()):
            print(path)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
