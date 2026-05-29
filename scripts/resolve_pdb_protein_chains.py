#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import shlex
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

AMINO_ACIDS = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
    "SEC", "PYL",
}
FALSE_VALUES = {"0", "false", "f", "no", "n", "off", "disabled", "skip"}


def enabled(row: dict[str, str]) -> bool:
    value = row.get("enabled", "").strip().lower()
    return value == "" or value not in FALSE_VALUES


def fetch_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def count_pdb_ca(pdb_text: str) -> dict[str, int]:
    residues: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM") or len(line) < 27:
            continue
        atom = line[12:16].strip()
        resname = line[17:20].strip().upper()
        chain = line[21].strip()
        if atom != "CA" or resname not in AMINO_ACIDS or not chain:
            continue
        residues[chain].add((resname, line[22:26].strip(), line[26].strip()))
    return {chain: len(values) for chain, values in residues.items()}


def count_cif_ca(cif_text: str) -> dict[str, int]:
    lines = cif_text.splitlines()
    residues: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    i = 0
    while i < len(lines):
        if lines[i].strip() != "loop_":
            i += 1
            continue
        i += 1
        headers: list[str] = []
        while i < len(lines) and lines[i].startswith("_"):
            headers.append(lines[i].strip())
            i += 1
        if not headers or not all(header.startswith("_atom_site.") for header in headers):
            while i < len(lines) and lines[i].strip() and lines[i].strip() != "#":
                i += 1
            continue
        names = [header.replace("_atom_site.", "") for header in headers]
        index = {name: idx for idx, name in enumerate(names)}
        while i < len(lines):
            raw = lines[i].strip()
            if not raw or raw == "#" or raw == "loop_" or raw.startswith("_"):
                break
            parts = shlex.split(raw)
            if not parts or parts[0] not in {"ATOM", "HETATM"}:
                i += 1
                continue
            def value(name: str, default: str = "") -> str:
                idx = index.get(name)
                if idx is None or idx >= len(parts):
                    return default
                raw_value = parts[idx]
                return default if raw_value in {".", "?"} else raw_value
            atom = value("auth_atom_id") or value("label_atom_id")
            resname = (value("auth_comp_id") or value("label_comp_id")).upper()
            chain = value("auth_asym_id") or value("label_asym_id")
            if atom == "CA" and resname in AMINO_ACIDS and chain:
                resseq = value("auth_seq_id") or value("label_seq_id")
                icode = value("pdbx_PDB_ins_code")
                residues[chain].add((resname, resseq, icode))
            i += 1
        break
    return {chain: len(values) for chain, values in residues.items()}


def chain_counts(pdb_id: str) -> dict[str, int]:
    pdb_id = pdb_id.upper()
    try:
        pdb_text = fetch_text(f"https://files.rcsb.org/download/{pdb_id}.pdb")
        counts = count_pdb_ca(pdb_text)
        if counts:
            return counts
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    cif_text = fetch_text(f"https://files.rcsb.org/download/{pdb_id}.cif")
    return count_cif_ca(cif_text)


def choose_chain(counts: dict[str, int], requested: str) -> tuple[str, int, str]:
    requested = requested.strip()
    if requested and counts.get(requested, 0) > 0:
        return requested, counts[requested], "requested_chain_is_protein"
    if not counts:
        return "", 0, "no_protein_ca_chain_found"
    chain, length = max(counts.items(), key=lambda item: (item[1], item[0]))
    return chain, length, f"resolved_from_placeholder_{requested or 'blank'}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve PDB input rows to protein chains and filter by C-alpha residue count.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--max-residues-exclusive", type=int, default=1000)
    parser.add_argument("--enabled-only", action="store_true")
    args = parser.parse_args()

    with Path(args.input_csv).open(newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        base_fields = list(reader.fieldnames or [])

    output_fields = list(base_fields)
    for field in ["original_chain", "resolved_chain", "residue_count_inferred", "resolution_notes"]:
        if field not in output_fields:
            output_fields.append(field)

    kept: list[dict[str, str]] = []
    skipped_disabled = 0
    skipped_length = 0
    skipped_no_protein = 0
    for row in rows:
        if args.enabled_only and not enabled(row):
            skipped_disabled += 1
            continue
        pdb_id = row.get("PDBID", "").strip().upper()
        original_chain = row.get("chain", "").strip()
        counts = chain_counts(pdb_id)
        chain, length, note = choose_chain(counts, original_chain)
        if not chain:
            skipped_no_protein += 1
            continue
        if length >= args.max_residues_exclusive:
            skipped_length += 1
            continue
        output_chain = chain[:1]
        if output_chain != chain:
            note = f"{note}; pdb_chain_id_truncated_from_{chain}"
        out = dict(row)
        out["original_chain"] = original_chain
        out["chain"] = output_chain
        out["resolved_chain"] = chain
        out["residue_count_inferred"] = str(length)
        out["resolution_notes"] = note
        kept.append(out)

    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields)
        writer.writeheader()
        writer.writerows(kept)

    print(f"Read rows: {len(rows)}")
    print(f"Wrote rows: {len(kept)}")
    print(f"Skipped disabled: {skipped_disabled}")
    print(f"Skipped no protein chain: {skipped_no_protein}")
    print(f"Skipped length >= {args.max_residues_exclusive}: {skipped_length}")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
