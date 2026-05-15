#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import shutil
from pathlib import Path


TARGET_COLUMNS = ["target_id", "pdb_id", "chain_id", "sequence", "reference_pdb", "notes"]
AMINO_ACIDS = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
    "SEC": "U",
    "PYL": "O",
}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off", "disabled", "skip"}


def clean_sequence(value: str) -> str:
    sequence = re.sub(r"\s+", "", value or "").upper()
    if sequence and not re.fullmatch(r"[A-Z*]+", sequence):
        raise ValueError(f"sequence contains unsupported characters: {value!r}")
    return sequence.replace("*", "")


def wrap_sequence(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[i : i + width] for i in range(0, len(sequence), width))


def enabled_value(row: dict[str, str]) -> bool:
    if "enabled" not in row or row.get("enabled", "").strip() == "":
        return True
    return row.get("enabled", "").strip().lower() not in FALSE_VALUES


def normalize_pdb_id(value: str) -> str:
    pdb_id = (value or "").strip().upper()
    if not re.fullmatch(r"[0-9A-Z]{4}", pdb_id):
        raise ValueError(f"PDBID must be a four-character PDB ID, got {value!r}")
    return pdb_id


def target_id_for(pdb_id: str, chain_id: str, name: str, existing: dict[tuple[str, str], dict[str, str]]) -> str:
    previous = existing.get((pdb_id, chain_id))
    if previous:
        return previous["target_id"]
    if name:
        slug = re.sub(r"[^0-9A-Za-z]+", "_", name.strip()).strip("_").lower()
        if slug:
            return f"{pdb_id}_{slug}"
    clean_chain = re.sub(r"[^0-9A-Za-z]+", "", chain_id) or "unknown"
    return f"{pdb_id}_chain{clean_chain}"


def load_existing_targets(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = {}
        for row in reader:
            pdb_id = row.get("pdb_id", "").strip().upper()
            chain_id = row.get("chain_id", "").strip()
            if pdb_id and chain_id:
                rows[(pdb_id, chain_id)] = row
        return rows


def sequence_from_reference(reference: Path, chain_id: str) -> str:
    residues: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    with reference.open(errors="replace") as f:
        for line in f:
            if not line.startswith("ATOM"):
                continue
            if len(line) <= 26 or line[21].strip() != chain_id:
                continue
            atom_name = line[12:16].strip()
            if atom_name != "CA":
                continue
            resname = line[17:20].strip().upper()
            resseq = line[22:26].strip()
            icode = line[26].strip()
            key = (resname, resseq, icode)
            if key in seen:
                continue
            seen.add(key)
            residues.append(AMINO_ACIDS.get(resname, "X"))
    return "".join(residues)


def write_fasta(target_id: str, sequence: str, output: Path, overwrite: bool) -> bool:
    if output.exists() and not overwrite:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f">{target_id}\n{wrap_sequence(sequence)}\n")
    return True


def resolve_reference(
    row: dict[str, str],
    pdb_id: str,
    chain_id: str,
    target_id: str,
    references_dir: Path,
    existing: dict[tuple[str, str], dict[str, str]],
    overwrite: bool,
) -> Path:
    reference_value = row.get("reference_path", "").strip()
    if reference_value:
        source = Path(reference_value).expanduser()
        if not source.exists():
            raise FileNotFoundError(f"reference_path does not exist for {target_id}: {source}")
        destination = references_dir / f"{target_id}.pdb"
        if source.resolve() != destination.resolve() and (overwrite or not destination.exists()):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return destination

    previous = existing.get((pdb_id, chain_id))
    if previous and previous.get("reference_pdb"):
        reference = Path(previous["reference_pdb"])
        if reference.exists():
            return reference

    candidate = references_dir / f"{target_id}.pdb"
    if candidate.exists():
        return candidate

    raise FileNotFoundError(
        f"No reference is available for {target_id}. Provide reference_path in the input CSV "
        f"or create {candidate} before preparing targets."
    )


def prepare_rows(args: argparse.Namespace) -> tuple[list[dict[str, str]], int, int, int]:
    input_csv = Path(args.input_csv)
    output_targets = Path(args.output_targets)
    references_dir = Path(args.references_dir)
    sequences_dir = Path(args.sequences_dir)
    existing = load_existing_targets(output_targets)

    with input_csv.open(newline="") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        missing = {"PDBID", "chain"} - fields
        if missing:
            raise SystemExit(f"Input CSV is missing required columns: {sorted(missing)}")

        rows: list[dict[str, str]] = []
        skipped = 0
        fasta_written = 0
        references_ready = 0
        for line_number, row in enumerate(reader, start=2):
            if not enabled_value(row):
                skipped += 1
                continue
            try:
                pdb_id = normalize_pdb_id(row.get("PDBID", ""))
                chain_id = (row.get("chain") or "").strip()
                if not chain_id:
                    raise ValueError("chain is required")
                name = (row.get("name") or "").strip()
                target_id = target_id_for(pdb_id, chain_id, name, existing)
                reference = resolve_reference(row, pdb_id, chain_id, target_id, references_dir, existing, args.overwrite)
                sequence = clean_sequence(row.get("sequence", ""))
                if not sequence:
                    previous = existing.get((pdb_id, chain_id))
                    sequence = clean_sequence(previous.get("sequence", "") if previous else "")
                if not sequence:
                    sequence = sequence_from_reference(reference, chain_id)
                if not sequence:
                    raise ValueError(
                        f"No sequence is available for {target_id}. Provide a sequence column "
                        "or a prepared protein reference_path with C-alpha atoms for the selected chain."
                    )
            except Exception as exc:
                raise SystemExit(f"Invalid input row {line_number}: {exc}") from exc

            fasta_path = sequences_dir / f"{target_id}.fasta"
            if write_fasta(target_id, sequence, fasta_path, args.overwrite):
                fasta_written += 1
            if reference.exists():
                references_ready += 1
            description = (row.get("description") or "").strip()
            note_parts = [part for part in [name, description] if part]
            rows.append(
                {
                    "target_id": target_id,
                    "pdb_id": pdb_id,
                    "chain_id": chain_id,
                    "sequence": sequence,
                    "reference_pdb": str(reference),
                    "notes": "; ".join(note_parts),
                }
            )

    return rows, fasta_written, references_ready, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare benchmark targets from a user CSV with PDBID and chain columns.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-targets", default="data/targets/targets.csv")
    parser.add_argument("--references-dir", default="data/references")
    parser.add_argument("--sequences-dir", default="data/sequences")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    rows, fasta_written, references_ready, skipped = prepare_rows(args)
    if not rows:
        raise SystemExit("No enabled targets were prepared.")

    output_targets = Path(args.output_targets)
    output_targets.parent.mkdir(parents=True, exist_ok=True)
    with output_targets.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TARGET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Prepared {len(rows)} targets")
    print(f"Wrote {output_targets}")
    print(f"Wrote {fasta_written} FASTA files")
    print(f"References ready: {references_ready}/{len(rows)}")
    print(f"Skipped disabled rows: {skipped}")


if __name__ == "__main__":
    main()
