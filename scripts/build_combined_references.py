#!/usr/bin/env python3
"""Build per-target reference PDB files from cached mmCIFs using the manifest's
explicit chain_id and residue_start/residue_end range.

The existing scoring_targets.csv (copied from the colabfold run) forces every target
to chain A and scores the full chain.  This script corrects that by:

  1. Reading the combined-run prediction_manifest.csv (authoritative mapping).
  2. For each of the 45 targets, extracting the correct chain from the cached mmCIF
     and clipping ATOM records to the manifest residue range.
  3. Writing <run-dir>/references/<target_id>.pdb (single chain A, range-clipped).
  4. Rewriting <run-dir>/metadata/scoring_targets.csv with corrected reference paths
     and chain_id=A.

Extraction details
------------------
* Chain matching: exact auth_asym_id match is tried first; falls back to exact
  label_asym_id match if auth yields nothing.  This avoids the false positives that
  occur when label_asym_id of one chain equals auth_asym_id of another.
* Residue-range filtering: keeps only atoms whose auth_seq_id falls in
  [residue_start, residue_end] (PDB author residue numbers, as stored in the
  manifest).
* Deduplication: when the asymmetric unit contains multiple copies of the same chain
  (e.g. 20 copies of a viral monomer all sharing auth_asym_id=A), only the first
  occurrence of each (resSeq, atomName) pair is kept so the reference contains
  exactly one molecule.

All 25 PDB mmCIFs must already be cached under <cache-dir>/<pdb>/<pdb>.cif.

Usage (from repo root):
    python scripts/build_combined_references.py [--run-dir results/2026-06-06-combine-8models]
    python scripts/build_combined_references.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── mmCIF extraction ──────────────────────────────────────────────────────────

def _format_atom_name(name: str) -> str:
    """Format atom name into the 4-character PDB column (cols 13–16, 0-indexed 12–15).

    PDB convention: 1–3 char names for 1-letter elements are left-padded with a
    space (so 'CA' → ' CA ', 'N' → ' N  ').  4-char names fill the field directly.
    """
    if len(name) <= 3:
        return f" {name:<3s}"
    return f"{name[:4]}"


def extract_chain_range_from_cif(
    cif_text: str,
    chain_id: str,
    res_start: int,
    res_end: int,
) -> tuple[str, int]:
    """Extract one chain + residue range from mmCIF text, output as PDB format.

    Matching: exact auth_asym_id first, then label_asym_id as fallback.
    Deduplication: first occurrence of each (auth_seq_id, atom_name) is kept.
    Output chain is renamed to 'A'.

    Returns (pdb_text, ca_count).  Returns ("", 0) if chain not found.
    """
    # Locate the _atom_site loop (may span to end of file or next loop_/#).
    loop_match = re.search(
        r"(loop_\s+(?:_atom_site\.\S+\s*)+)(.*?)(?=\nloop_|\n#|\Z)",
        cif_text,
        re.DOTALL,
    )
    if not loop_match:
        return "", 0

    col_names: list[str] = re.findall(r"_atom_site\.(\S+)", loop_match.group(1))
    col_idx: dict[str, int] = {n: i for i, n in enumerate(col_names)}

    # Required columns.
    for req in ("group_PDB", "label_atom_id", "label_comp_id",
                "auth_asym_id", "label_asym_id", "auth_seq_id",
                "Cartn_x", "Cartn_y", "Cartn_z"):
        if req not in col_idx:
            raise ValueError(f"mmCIF atom_site loop missing column: {req}")

    data_lines = [
        l for l in loop_match.group(2).splitlines()
        if l.startswith(("ATOM", "HETATM"))
    ]

    # Determine matching column: prefer auth_asym_id exact, fall back to label_asym_id.
    auth_ids = {l.split()[col_idx["auth_asym_id"]] for l in data_lines if len(l.split()) > col_idx["auth_asym_id"]}
    label_ids = {l.split()[col_idx["label_asym_id"]] for l in data_lines if len(l.split()) > col_idx["label_asym_id"]}

    if chain_id in auth_ids:
        match_col = "auth_asym_id"
    elif chain_id in label_ids:
        match_col = "label_asym_id"
    else:
        return "", 0  # chain not found in this mmCIF

    # Optional columns (substitute defaults when absent).
    ins_code_col = col_idx.get("pdbx_PDB_ins_code")
    occupancy_col = col_idx.get("occupancy")
    bfactor_col = col_idx.get("B_iso_or_equiv")
    element_col = col_idx.get("type_symbol")
    model_col = col_idx.get("pdbx_PDB_model_num")

    seen: set[tuple[int, str]] = set()
    pdb_lines: list[str] = []
    ca_count = 0
    serial = 0

    for raw in data_lines:
        parts = raw.split()
        if len(parts) < len(col_names):
            continue

        # Chain filter.
        if parts[col_idx[match_col]] != chain_id:
            continue

        # Residue range filter.
        auth_seq_raw = parts[col_idx["auth_seq_id"]]
        try:
            res_seq = int(auth_seq_raw)
        except ValueError:
            continue
        if not (res_start <= res_seq <= res_end):
            continue

        atom_name = parts[col_idx["label_atom_id"]]

        # Deduplication: first occurrence of (resSeq, atomName) wins.
        dup_key = (res_seq, atom_name)
        if dup_key in seen:
            continue
        seen.add(dup_key)

        # Parse coordinates.
        try:
            x = float(parts[col_idx["Cartn_x"]])
            y = float(parts[col_idx["Cartn_y"]])
            z = float(parts[col_idx["Cartn_z"]])
        except (ValueError, IndexError):
            continue

        record = parts[col_idx["group_PDB"]]  # ATOM or HETATM
        res_name = parts[col_idx["label_comp_id"]]

        # Insertion code ("?" in mmCIF means blank).
        if ins_code_col is not None:
            raw_ins = parts[ins_code_col]
            ins_code = " " if raw_ins in (".", "?") else raw_ins[0]
        else:
            ins_code = " "

        # Occupancy / B-factor.
        try:
            occ = float(parts[occupancy_col]) if occupancy_col is not None else 1.0
        except (ValueError, TypeError):
            occ = 1.0
        try:
            bfac = float(parts[bfactor_col]) if bfactor_col is not None else 0.0
        except (ValueError, TypeError):
            bfac = 0.0

        # Element (right-justified in 2 chars; fall back to atom_name first char).
        if element_col is not None:
            raw_el = parts[element_col]
            element = raw_el if raw_el not in (".", "?") else atom_name[0]
        else:
            element = atom_name[0]

        serial += 1
        atom_field = _format_atom_name(atom_name)
        # PDB ATOM line: 80 cols.
        line = (
            f"{record:<6s}{serial:5d} {atom_field}{' ':1s}{res_name:3s} "
            f"{'A':1s}{res_seq:4d}{ins_code:1s}   "
            f"{x:8.3f}{y:8.3f}{z:8.3f}{occ:6.2f}{bfac:6.2f}          "
            f"{element:>2s}  "
        )
        pdb_lines.append(line)

        if atom_name == "CA":
            ca_count += 1

    if not pdb_lines:
        return "", 0

    pdb_text = "\n".join(pdb_lines) + "\nEND\n"
    return pdb_text, ca_count


# ── Main ──────────────────────────────────────────────────────────────────────

def build_targets_from_manifest(manifest_path: Path) -> dict[str, dict[str, str]]:
    """Return {target_id: row} from the manifest (one row per target, first row wins)."""
    targets: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(manifest_path.open(newline="")):
        tid = row.get("target_id", "")
        if tid and tid not in targets:
            targets[tid] = row
    return targets


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--run-dir",
        default="results/2026-06-06-combine-8models",
        help="Combined run folder (relative to repo root). Default: %(default)s",
    )
    ap.add_argument(
        "--cache-dir",
        default="data/cache/rcsb",
        help="mmCIF cache root (<pdb>/<pdb>.cif). Default: %(default)s",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be done without writing any files.",
    )
    args = ap.parse_args()

    run_dir = REPO_ROOT / args.run_dir
    cache_dir = REPO_ROOT / args.cache_dir
    refs_dir = run_dir / "references"
    manifest_path = run_dir / "metadata" / "prediction_manifest.csv"
    old_targets_path = run_dir / "metadata" / "scoring_targets.csv"
    new_targets_path = run_dir / "metadata" / "scoring_targets.csv"

    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    targets = build_targets_from_manifest(manifest_path)
    print(f"Manifest: {len(targets)} unique targets.")

    # Carry sequences from the old scoring_targets.csv (informational only).
    old_sequences: dict[str, str] = {}
    if old_targets_path.exists():
        for row in csv.DictReader(old_targets_path.open(newline="")):
            old_sequences[row["target_id"]] = row.get("sequence", "")

    if not args.dry_run:
        refs_dir.mkdir(parents=True, exist_ok=True)

    new_rows: list[dict[str, str]] = []
    errors = 0

    for tid in sorted(targets):
        row = targets[tid]
        pdb_id = row["pdb_id"].lower()
        chain_id = row["chain_id"]
        try:
            res_start = int(float(row["residue_start"]))
            res_end = int(float(row["residue_end"]))
        except (ValueError, KeyError):
            print(f"  ERROR: {tid}: missing/invalid residue_start or residue_end", file=sys.stderr)
            errors += 1
            continue

        resolved_ca_str = row.get("resolved_ca_count", "")

        cif_path = cache_dir / pdb_id / f"{pdb_id}.cif"
        if not cif_path.exists():
            print(f"  ERROR: {tid}: mmCIF not found: {cif_path}", file=sys.stderr)
            errors += 1
            continue

        cif_text = cif_path.read_text()
        try:
            pdb_text, ca_count = extract_chain_range_from_cif(
                cif_text, chain_id, res_start, res_end
            )
        except Exception as exc:
            print(f"  ERROR: {tid}: extraction failed: {exc}", file=sys.stderr)
            errors += 1
            continue

        # Validate Cα count.
        if ca_count == 0:
            print(
                f"  ERROR: {tid}: 0 Cα atoms after extraction "
                f"(pdb={pdb_id}, chain={chain_id}, residues={res_start}-{res_end})",
                file=sys.stderr,
            )
            errors += 1
        else:
            mismatch_msg = ""
            try:
                expected_ca = int(float(resolved_ca_str))
                pct_diff = abs(ca_count - expected_ca) / max(expected_ca, 1) * 100
                if pct_diff > 10:
                    mismatch_msg = (
                        f"  WARNING: {tid}: Cα count mismatch: "
                        f"got {ca_count}, manifest says {expected_ca} ({pct_diff:.0f}% diff)"
                    )
            except (ValueError, TypeError):
                pass
            status = "DRY" if args.dry_run else "OK "
            print(
                f"  [{status}] {tid}: {pdb_id}/{chain_id} res {res_start}-{res_end}"
                f" → {ca_count} Cα  (manifest: {resolved_ca_str})"
            )
            if mismatch_msg:
                print(mismatch_msg)

        ref_path = refs_dir / f"{tid}.pdb"
        if not args.dry_run and ca_count > 0:
            ref_path.write_text(pdb_text)

        new_rows.append({
            "target_id": tid,
            "pdb_id": row["pdb_id"],
            "chain_id": "A",
            "sequence": old_sequences.get(tid, ""),
            "reference_pdb": str(ref_path.relative_to(REPO_ROOT)),
            "notes": f"src_chain={chain_id};residues={res_start}-{res_end}",
        })

    # Write corrected scoring_targets.csv.
    if not args.dry_run:
        with new_targets_path.open("w", newline="") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=["target_id", "pdb_id", "chain_id", "sequence", "reference_pdb", "notes"],
            )
            w.writeheader()
            w.writerows(new_rows)
        print(f"\nWrote {len(new_rows)} targets → {new_targets_path}")
        print(f"References dir: {refs_dir}")
    else:
        print(f"\n[dry-run] Would write {len(new_rows)} references and scoring_targets.csv.")

    if errors:
        raise SystemExit(f"\n{errors} error(s) — review output above.")
    print(f"\nDone. {len(new_rows)} references {'(dry-run) ' if args.dry_run else ''}built successfully.")


if __name__ == "__main__":
    main()
