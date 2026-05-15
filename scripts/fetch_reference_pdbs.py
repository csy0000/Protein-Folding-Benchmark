#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import shlex
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from prepare_targets_from_csv import enabled_value, normalize_pdb_id, target_id_for


def filter_chain_lines(pdb_text: str, chain_id: str) -> str:
    keep_prefixes = (
        "HEADER",
        "TITLE ",
        "COMPND",
        "SOURCE",
        "KEYWDS",
        "EXPDTA",
        "AUTHOR",
        "REMARK",
        "DBREF ",
        "SEQRES",
        "CRYST1",
        "SCALE",
        "ORIGX",
        "MTRIX",
    )
    lines: list[str] = []
    wrote_atom = False
    for line in pdb_text.splitlines():
        record = line[:6]
        if record.startswith(keep_prefixes):
            lines.append(line)
            continue
        if record.strip() in {"ATOM", "HETATM", "ANISOU", "TER"} and len(line) > 21 and line[21].strip() == chain_id:
            lines.append(line)
            if record.strip() == "ATOM":
                wrote_atom = True
    if wrote_atom:
        lines.append("END")
    return "\n".join(lines) + "\n"


def read_rows(path: Path, limit: int | None) -> tuple[int, list[dict[str, str]]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        missing = {"PDBID", "chain"} - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Input CSV is missing required columns: {sorted(missing)}")
        rows = list(reader)

    selected: list[dict[str, str]] = []
    for row in rows:
        if not enabled_value(row):
            continue
        selected.append(row)
        if limit is not None and len(selected) >= limit:
            break
    return len(rows), selected


def fetch_pdb_text(pdb_id: str, source: str) -> str:
    if source != "rcsb":
        raise ValueError(f"Unsupported source: {source}")
    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    return data.decode("utf-8", errors="replace")


def fetch_cif_text(pdb_id: str, source: str) -> str:
    if source != "rcsb":
        raise ValueError(f"Unsupported source: {source}")
    url = f"https://files.rcsb.org/download/{pdb_id}.cif"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    return data.decode("utf-8", errors="replace")


def cif_to_pdb_chain(cif_text: str, chain_id: str) -> str:
    lines = cif_text.splitlines()
    atom_headers: list[str] = []
    atom_rows: list[list[str]] = []
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
        if headers and all(header.startswith("_atom_site.") for header in headers):
            atom_headers = [header.replace("_atom_site.", "") for header in headers]
            while i < len(lines):
                raw = lines[i].strip()
                if not raw or raw == "#" or raw == "loop_" or raw.startswith("_"):
                    break
                parts = shlex.split(raw)
                if parts and parts[0] in {"ATOM", "HETATM"}:
                    atom_rows.append(parts)
                i += 1
            break
        while i < len(lines) and lines[i].strip() and lines[i].strip() != "#":
            i += 1

    if not atom_headers or not atom_rows:
        raise ValueError("mmCIF atom_site loop not found")

    index = {name: idx for idx, name in enumerate(atom_headers)}

    def value(row: list[str], name: str, default: str = "") -> str:
        idx = index.get(name)
        if idx is None or idx >= len(row):
            return default
        raw = row[idx]
        return default if raw in {".", "?"} else raw

    pdb_lines: list[str] = []
    serial = 1
    for row in atom_rows:
        group = value(row, "group_PDB", "ATOM")
        if group != "ATOM":
            continue
        auth_chain = value(row, "auth_asym_id")
        label_chain = value(row, "label_asym_id")
        if chain_id not in {auth_chain, label_chain}:
            continue
        atom_name = value(row, "auth_atom_id") or value(row, "label_atom_id")
        resname = value(row, "auth_comp_id") or value(row, "label_comp_id", "UNK")
        resseq_text = value(row, "auth_seq_id") or value(row, "label_seq_id", "1")
        try:
            resseq = int(float(resseq_text))
        except ValueError:
            resseq = 1
        try:
            x = float(value(row, "Cartn_x", "0"))
            y = float(value(row, "Cartn_y", "0"))
            z = float(value(row, "Cartn_z", "0"))
            occupancy = float(value(row, "occupancy", "1"))
            b_factor = float(value(row, "B_iso_or_equiv", "0"))
        except ValueError:
            continue
        element = (value(row, "type_symbol") or atom_name[:1]).upper()[:2]
        pdb_chain = (auth_chain or label_chain or chain_id)[:1]
        atom_field = atom_name[:4].rjust(4)
        pdb_lines.append(
            f"ATOM  {serial:5d} {atom_field} {resname[:3]:>3s} {pdb_chain:1s}"
            f"{resseq:4d}    {x:8.3f}{y:8.3f}{z:8.3f}{occupancy:6.2f}{b_factor:6.2f}"
            f"          {element:>2s}"
        )
        serial += 1
        if serial > 99999:
            break
    if not pdb_lines:
        raise ValueError(f"No ATOM rows found for chain {chain_id} in mmCIF")
    pdb_lines.extend(["TER", "END"])
    return "\n".join(pdb_lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download reference PDB files for a CSV with PDBID and chain columns.")
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--references-dir", default="data/references")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--source", default="rcsb", choices=["rcsb"])
    parser.add_argument("--filter-chain", action="store_true")
    args = parser.parse_args()

    references_dir = Path(args.references_dir)
    references_dir.mkdir(parents=True, exist_ok=True)

    rows_read, selected = read_rows(Path(args.input_csv), args.limit)
    downloaded = 0
    skipped_existing = 0
    failures: list[str] = []

    for row in selected:
        try:
            pdb_id = normalize_pdb_id(row.get("PDBID", ""))
            chain_id = (row.get("chain") or "").strip()
            if not chain_id:
                raise ValueError("chain is required")
            name = (row.get("name") or "").strip()
            target_id = target_id_for(pdb_id, chain_id, name, {})
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", target_id):
                raise ValueError(f"unsafe target_id: {target_id}")
            output = references_dir / f"{target_id}.pdb"
            if output.exists() and not args.overwrite:
                print(f"[skip] {output}")
                skipped_existing += 1
                continue
            try:
                text = fetch_pdb_text(pdb_id, args.source)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                cif_text = fetch_cif_text(pdb_id, args.source)
                text = cif_to_pdb_chain(cif_text, chain_id)
            if args.filter_chain:
                text = filter_chain_lines(text, chain_id)
            if "ATOM" not in text:
                raise ValueError(f"downloaded file for {pdb_id} does not contain ATOM records")
            output.write_text(text)
            downloaded += 1
            print(f"[downloaded] {pdb_id} chain {chain_id} -> {output}")
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
            message = f"{row.get('PDBID', '')},{row.get('chain', '')}: {exc}"
            failures.append(message)
            print(f"[failed] {message}", file=sys.stderr)

    print("Fetch summary")
    print(f"Rows read: {rows_read}")
    print(f"Enabled rows considered: {len(selected)}")
    print(f"Files downloaded: {downloaded}")
    print(f"Files skipped existing: {skipped_existing}")
    print(f"Failures: {len(failures)}")

    if failures:
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
