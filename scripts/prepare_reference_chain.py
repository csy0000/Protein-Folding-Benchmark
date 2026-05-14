#!/usr/bin/env python3

import argparse
from pathlib import Path


def parse_model_number(line: str) -> int:
    try:
        return int(line[10:14].strip())
    except ValueError:
        return -1


def is_selected_chain(line: str, chain_id: str) -> bool:
    return len(line) > 21 and line[21] == chain_id


def write_reference_chain(input_pdb: Path, output_pdb: Path, chain_id: str, model_index: int) -> None:
    output_pdb.parent.mkdir(parents=True, exist_ok=True)

    saw_model_record = False
    in_selected_model = model_index == 1
    wrote_atom = False
    wrote_ter = False

    with input_pdb.open() as fin, output_pdb.open("w") as fout:
        for line in fin:
            record = line[:6].strip()

            if record == "MODEL":
                saw_model_record = True
                in_selected_model = parse_model_number(line) == model_index
                continue

            if record == "ENDMDL":
                if in_selected_model:
                    break
                in_selected_model = False
                continue

            if saw_model_record and not in_selected_model:
                continue

            if record == "ATOM" and is_selected_chain(line, chain_id):
                fout.write(line)
                wrote_atom = True
                wrote_ter = False
                continue

            if record == "TER" and is_selected_chain(line, chain_id) and wrote_atom and not wrote_ter:
                fout.write(line)
                wrote_ter = True

        if wrote_atom and not wrote_ter:
            fout.write("TER\n")
        fout.write("END\n")

    if not wrote_atom:
        raise RuntimeError(f"No protein ATOM records found for model {model_index} chain {chain_id} in {input_pdb}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract a protein chain from a PDB reference structure.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--chain", default="A")
    parser.add_argument("--model-index", type=int, default=1)
    args = parser.parse_args()

    write_reference_chain(Path(args.input), Path(args.output), args.chain, args.model_index)


if __name__ == "__main__":
    main()
