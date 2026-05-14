#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path


def wrap_sequence(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[i : i + width] for i in range(0, len(sequence), width))


def write_fasta(target_id: str, sequence: str, output: Path, overwrite: bool) -> str:
    if output.exists() and not overwrite:
        return "skipped"

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f">{target_id}\n{wrap_sequence(sequence)}\n")
    return "written"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare benchmark FASTA files from data/targets/targets.csv.")
    parser.add_argument("--targets", default="data/targets/targets.csv")
    parser.add_argument("--sequence-dir", default="data/sequences")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    targets_path = Path(args.targets)
    sequence_dir = Path(args.sequence_dir)

    with targets_path.open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"target_id", "sequence"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Missing required target columns: {sorted(missing)}")

        for row in reader:
            target_id = row["target_id"].strip()
            sequence = "".join(row["sequence"].split()).upper()
            if not target_id or not sequence:
                raise SystemExit(f"Invalid target row: {row}")
            output = sequence_dir / f"{target_id}.fasta"
            status = write_fasta(target_id, sequence, output, args.overwrite)
            print(f"{status}: {output}")


if __name__ == "__main__":
    main()
