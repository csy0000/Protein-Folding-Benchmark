#!/usr/bin/env python3

from pathlib import Path
import argparse


def extract_model_1(input_pdb: Path, output_pdb: Path, chain_id: str = "A") -> None:
    in_model_1 = False
    wrote_model = False
    saw_model_record = False

    output_pdb.parent.mkdir(parents=True, exist_ok=True)

    with input_pdb.open() as fin, output_pdb.open("w") as fout:
        for line in fin:
            record = line[:6].strip()

            if record == "MODEL":
                saw_model_record = True
                model_number = int(line[10:14].strip())
                in_model_1 = model_number == 1
                continue

            if record == "ENDMDL":
                if in_model_1:
                    wrote_model = True
                    break
                in_model_1 = False
                continue

            if saw_model_record and not in_model_1:
                continue

            if record in {"ATOM", "TER"}:
                if len(line) > 21 and line[21] == chain_id:
                    fout.write(line)
                    wrote_model = True

        fout.write("END\n")

    if not wrote_model:
        raise RuntimeError(f"Could not write MODEL 1 chain {chain_id} from input PDB.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--chain", default="A")
    args = parser.parse_args()

    extract_model_1(Path(args.input), Path(args.output), args.chain)


if __name__ == "__main__":
    main()
