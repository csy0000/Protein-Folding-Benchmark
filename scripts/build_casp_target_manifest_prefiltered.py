#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from build_casp_target_manifest import (
    AlignmentResult,
    ChainRecord,
    align_sequences,
    choose_chain,
    clean_sequence,
    extract_sequence_from_detail,
    fetch_cached,
    parse_chain_records,
    parse_cif,
    parse_target_list,
)


CASP_URLS = {
    "CASP15": "https://predictioncenter.org/casp15/targetlist.cgi",
    "CASP16": "https://predictioncenter.org/casp16/targetlist.cgi?view=regular&assis_type=all&view=all&phase=&field=t.release_date&order=ASC",
}

OUTPUT_COLUMNS = [
    "casp_round",
    "domain_id",
    "target_id",
    "pdb_id",
    "chain_id",
    "residue_start",
    "residue_end",
    "sequence_start",
    "sequence_end",
    "sequence",
    "target_length",
    "type",
    "stoichiometry",
    "description",
    "target_detail_url",
    "mapping_identity",
    "mapping_coverage",
    "target_aligned_start",
    "target_aligned_end",
    "chain_aligned_start",
    "chain_aligned_end",
    "chain_sequence_length",
    "resolved_ca_count",
    "expected_mapped_residue_count",
    "reference_coverage",
    "chain_assignment_confidence",
    "should_use",
    "reason",
    "residue_mapping_note",
    "alternative_chain_matches",
]


@dataclass
class RoundStats:
    total_rows: int = 0
    pass_stoichiometry: int = 0
    pass_type: int = 0
    with_pdb: int = 0
    pass_all: int = 0


def normalized_type(value: str) -> str:
    return " ".join((value or "").split())


def passes_type(value: str) -> bool:
    return normalized_type(value) in {"All groups", "Prot"}


def prefilter(rows: list, stats: RoundStats) -> list:
    candidates = []
    stats.total_rows = len(rows)
    for row in rows:
        stoich_ok = row.stoichiometry == "A1"
        type_ok = passes_type(row.target_type)
        pdb_ok = bool(row.pdb_ids)
        stats.pass_stoichiometry += int(stoich_ok)
        stats.pass_type += int(type_ok)
        stats.with_pdb += int(pdb_ok)
        if stoich_ok and type_ok and pdb_ok:
            stats.pass_all += 1
            candidates.append(row)
    return candidates


def fetch_round_targets(casp_round: str, cache_dir: Path, force_refresh: bool) -> tuple[list, RoundStats]:
    url = CASP_URLS[casp_round]
    round_dir = cache_dir / casp_round.lower()
    html = fetch_cached(url, round_dir / "targetlist.html", force_refresh)
    rows = parse_target_list(html, url)
    stats = RoundStats()
    candidates = prefilter(rows, stats)
    return candidates, stats


def residue_id(auth_seq: str, ins_code: str) -> str:
    if ins_code and ins_code not in {".", "?"}:
        return f"{auth_seq}{ins_code}"
    return auth_seq


def ca_author_map(cif_text: str, chain: ChainRecord) -> dict[int, str]:
    cif = parse_cif(cif_text)
    groups = as_list(cif.get("_atom_site.group_PDB"))
    atom_names = as_list(cif.get("_atom_site.label_atom_id")) or as_list(cif.get("_atom_site.auth_atom_id"))
    label_chains = as_list(cif.get("_atom_site.label_asym_id"))
    auth_chains = as_list(cif.get("_atom_site.auth_asym_id"))
    label_seq_ids = as_list(cif.get("_atom_site.label_seq_id"))
    auth_seq_ids = as_list(cif.get("_atom_site.auth_seq_id"))
    ins_codes = as_list(cif.get("_atom_site.pdbx_PDB_ins_code"))
    mapping: dict[int, str] = {}
    width = max(len(atom_names), len(label_seq_ids))
    for idx in range(width):
        group = get(groups, idx)
        atom = get(atom_names, idx)
        label_chain = get(label_chains, idx)
        auth_chain = get(auth_chains, idx)
        label_seq = get(label_seq_ids, idx)
        auth_seq = get(auth_seq_ids, idx)
        ins_code = get(ins_codes, idx)
        if group and group != "ATOM":
            continue
        if atom != "CA" or not label_seq or not auth_seq:
            continue
        if label_chain != chain.label_asym_id and auth_chain != chain.chain_id:
            continue
        try:
            mapping[int(float(label_seq))] = residue_id(auth_seq, ins_code)
        except ValueError:
            continue
    return mapping


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def get(values: list[str], idx: int) -> str:
    return values[idx] if idx < len(values) else ""


def map_residue_range(cif_text: str, chain: ChainRecord, alignment: AlignmentResult) -> tuple[str, str, int, int, float, str]:
    ca_map = ca_author_map(cif_text, chain)
    start = max(1, alignment.chain_start)
    end = max(start, alignment.chain_end)
    expected = max(0, end - start + 1)
    resolved_positions = [pos for pos in range(start, end + 1) if pos in ca_map]
    if not resolved_positions:
        return "", "", 0, expected, 0.0, "no resolved CA atoms found in aligned chain range"
    residue_start = ca_map[resolved_positions[0]]
    residue_end = ca_map[resolved_positions[-1]]
    coverage = len(resolved_positions) / expected if expected else 0.0
    note = "mapped from mmCIF atom_site CA records"
    if len(resolved_positions) < expected:
        note += f"; {expected - len(resolved_positions)} aligned positions lack resolved CA atoms"
    return residue_start, residue_end, len(resolved_positions), expected, coverage, note


def confidence_for(alignment: AlignmentResult) -> str:
    if alignment.identity >= 0.95 and alignment.coverage >= 0.90:
        return "high"
    if alignment.identity >= 0.90 and alignment.coverage >= 0.80:
        return "medium"
    if alignment.aligned_target_positions:
        return "low"
    return "failed"


def classify(
    sequence: str,
    target_length: int | None,
    alignment: AlignmentResult,
    confidence: str,
    residue_start: str,
    residue_end: str,
    reference_coverage: float,
    alternatives: list[tuple[ChainRecord, AlignmentResult]],
    errors: list[str],
) -> tuple[str, str]:
    reasons = list(errors)
    if sequence and target_length and len(sequence) != target_length:
        reasons.append(f"sequence length {len(sequence)} differs from Res column {target_length}")
    if confidence in {"failed", "low"}:
        reasons.append(
            f"chain mapping below threshold identity={alignment.identity:.3f} coverage={alignment.coverage:.3f}"
        )
    if not residue_start or not residue_end:
        reasons.append("chain matched but PDB residue range could not be resolved")
    if reference_coverage < 0.80:
        reasons.append(f"reference coverage below threshold {reference_coverage:.3f}")
    if alternatives:
        reasons.append("multiple equivalent chains match")

    fatal_prefixes = (
        "target sequence extraction failed",
        "RCSB FASTA retrieval failed",
        "RCSB mmCIF retrieval failed",
        "chain mapping below threshold",
    )
    if any(reason.startswith(fatal_prefixes) for reason in reasons):
        return "No", "; ".join(reasons)
    if reasons:
        return "Check", "; ".join(reasons)
    return "Yes", "prefiltered A1 protein target with mapped residue range"


def analyze_target(casp_round: str, target, cache_dir: Path, force_refresh: bool) -> dict[str, str]:
    round_dir = cache_dir / casp_round.lower()
    pdb_id = target.pdb_ids[0]
    errors: list[str] = []
    sequence = ""
    try:
        detail_html = fetch_cached(
            target.detail_url,
            round_dir / "target_details" / f"{target.target_id}.html",
            force_refresh,
        )
        sequence = extract_sequence_from_detail(detail_html, target.target_id)
        if not sequence:
            errors.append("target sequence extraction failed")
    except Exception as exc:
        errors.append(f"target sequence extraction failed: {exc}")

    chain = None
    alignment = AlignmentResult(0, 0, 0, 0, 0, 0, 0, 0)
    alternatives: list[tuple[ChainRecord, AlignmentResult]] = []
    residue_start = ""
    residue_end = ""
    resolved_ca_count = 0
    expected_count = 0
    reference_coverage = 0.0
    residue_mapping_note = ""
    chain_records: list[ChainRecord] = []
    cif_text = ""

    if sequence:
        rcsb_dir = cache_dir / "rcsb" / pdb_id.lower()
        try:
            fasta_text = fetch_cached(
                f"https://www.rcsb.org/fasta/entry/{pdb_id}",
                rcsb_dir / f"{pdb_id.lower()}.fasta",
                force_refresh,
            )
            cif_text = fetch_cached(
                f"https://files.rcsb.org/download/{pdb_id}.cif",
                rcsb_dir / f"{pdb_id.lower()}.cif",
                force_refresh,
            )
            chain_records = parse_chain_records(cif_text, fasta_text)
            chain, alignment, alternatives = choose_chain(sequence, chain_records)
            if chain is None:
                errors.append("chain mapping failed")
            else:
                residue_start, residue_end, resolved_ca_count, expected_count, reference_coverage, residue_mapping_note = map_residue_range(
                    cif_text, chain, alignment
                )
        except Exception as exc:
            errors.append(f"RCSB FASTA/mmCIF retrieval failed: {exc}")

    confidence = confidence_for(alignment) if chain else "failed"
    should_use, reason = classify(
        sequence,
        target.residues,
        alignment,
        confidence,
        residue_start,
        residue_end,
        reference_coverage,
        alternatives,
        errors,
    )
    alt_text = ";".join(f"{alt.chain_id}:{aln.identity:.3f}/{aln.coverage:.3f}" for alt, aln in alternatives[:10])
    return {
        "casp_round": casp_round,
        "domain_id": target.domain_id,
        "target_id": target.target_id,
        "pdb_id": pdb_id,
        "chain_id": chain.chain_id if chain else "",
        "residue_start": residue_start,
        "residue_end": residue_end,
        "sequence_start": "1" if sequence else "",
        "sequence_end": str(len(sequence)) if sequence else "",
        "sequence": sequence,
        "target_length": str(target.residues or len(sequence) or ""),
        "type": normalized_type(target.target_type),
        "stoichiometry": target.stoichiometry,
        "description": target.description,
        "target_detail_url": target.detail_url,
        "mapping_identity": fmt(alignment.identity),
        "mapping_coverage": fmt(alignment.coverage),
        "target_aligned_start": str(alignment.target_start or ""),
        "target_aligned_end": str(alignment.target_end or ""),
        "chain_aligned_start": str(alignment.chain_start or ""),
        "chain_aligned_end": str(alignment.chain_end or ""),
        "chain_sequence_length": str(len(chain.sequence) if chain else ""),
        "resolved_ca_count": str(resolved_ca_count),
        "expected_mapped_residue_count": str(expected_count),
        "reference_coverage": fmt(reference_coverage),
        "chain_assignment_confidence": confidence,
        "should_use": should_use,
        "reason": reason,
        "residue_mapping_note": residue_mapping_note,
        "alternative_chain_matches": alt_text,
    }


def fmt(value: float) -> str:
    return f"{value:.6f}"


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def run_round(casp_round: str, out_dir: Path, cache_dir: Path, force_refresh: bool) -> tuple[list[dict[str, str]], RoundStats]:
    candidates, stats = fetch_round_targets(casp_round, cache_dir, force_refresh)
    rows = [analyze_target(casp_round, target, cache_dir, force_refresh) for target in candidates]
    write_csv(out_dir / f"{casp_round.lower()}_target_manifest_prefiltered.csv", rows)
    print(
        f"{casp_round}: parsed={stats.total_rows} pass_stoich={stats.pass_stoichiometry} "
        f"pass_type={stats.pass_type} with_pdb={stats.with_pdb} pass_all={stats.pass_all} "
        f"yes_check_no={dict(Counter(row['should_use'] for row in rows))}"
    )
    return rows, stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Build prefiltered CASP target manifests with residue ranges.")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--cache-dir", default="data/cache/casp_target_manifest")
    parser.add_argument("--only-round", choices=["CASP15", "CASP16", "both"], default="both")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    cache_dir = Path(args.cache_dir)
    rounds = ["CASP15", "CASP16"] if args.only_round == "both" else [args.only_round]
    all_rows: list[dict[str, str]] = []
    for casp_round in rounds:
        rows, _stats = run_round(casp_round, out_dir, cache_dir, args.force_refresh)
        all_rows.extend(rows)
    if args.only_round == "both":
        write_csv(out_dir / "casp15_casp16_target_manifest_prefiltered.csv", all_rows)
        print(f"combined: rows={len(all_rows)} yes_check_no={dict(Counter(row['should_use'] for row in all_rows))}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
