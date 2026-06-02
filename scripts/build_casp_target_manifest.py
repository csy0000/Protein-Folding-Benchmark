#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import shlex
import sys
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


MANIFEST_COLUMNS = [
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
    "target_list_url",
    "target_detail_url",
    "rcsb_url",
    "mapping_identity",
    "mapping_coverage",
    "mapping_alignment_start",
    "mapping_alignment_end",
    "pdb_entity_id",
    "pdb_polymer_entity_description",
    "reference_coverage",
    "resolved_residue_count",
    "chain_assignment_confidence",
    "should_use",
    "reason",
    "alternative_chain_matches",
]

AMINO_ACIDS = set("ABCDEFGHIKLMNPQRSTVWXYZUO")
PROTEIN_ENTITY_TYPES = {"polypeptide(l)", "polypeptide(d)"}


@dataclass
class TargetRow:
    domain_id: str
    target_id: str
    target_type: str
    residues: int | None
    stoichiometry: str
    description: str
    pdb_ids: list[str]
    detail_url: str
    raw_text: str


@dataclass
class ChainRecord:
    chain_id: str
    label_asym_id: str
    entity_id: str
    sequence: str
    description: str
    label_to_auth: dict[int, str]
    resolved_ca_positions: set[int]


@dataclass
class AlignmentResult:
    identity: float
    coverage: float
    target_start: int
    target_end: int
    chain_start: int
    chain_end: int
    aligned_target_positions: int
    identical_positions: int


class TargetListParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.rows: list[list[dict[str, Any]]] = []
        self._in_tr = False
        self._in_cell = False
        self._current_row: list[dict[str, Any]] = []
        self._current_cell: dict[str, Any] | None = None
        self._current_href = ""
        self.csv_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if tag == "tr":
            self._in_tr = True
            self._current_row = []
        elif tag in {"td", "th"} and self._in_tr:
            self._in_cell = True
            self._current_cell = {"text_parts": [], "links": []}
        elif tag == "a":
            href = attrs_dict.get("href", "")
            self._current_href = urllib.parse.urljoin(self.base_url, href) if href else ""

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell and self._current_cell is not None:
            text = normalize_space(" ".join(self._current_cell["text_parts"]))
            self._current_cell["text"] = text
            self._current_row.append(self._current_cell)
            self._current_cell = None
            self._in_cell = False
        elif tag == "tr" and self._in_tr:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = []
            self._in_tr = False
        elif tag == "a":
            self._current_href = ""

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._in_cell and self._current_cell is not None:
            self._current_cell["text_parts"].append(text)
            if self._current_href:
                href = self._current_href
                self._current_cell["links"].append((text, href))
                if text.lower() == "csv":
                    self.csv_links.append(href)
        elif self._current_href and text.lower() == "csv":
            self.csv_links.append(self._current_href)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return html.unescape("\n".join(self.parts))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_sequence(value: str) -> str:
    return re.sub(r"[^A-Za-z]", "", value or "").upper()


def fetch_cached(url: str, cache_path: Path, force_refresh: bool = False) -> str:
    if cache_path.exists() and not force_refresh:
        return cache_path.read_text(errors="replace")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Protein-Folding-Benchmark/manifest-builder"})
    with urllib.request.urlopen(req, timeout=90) as response:
        data = response.read()
    text = data.decode("utf-8", errors="replace")
    cache_path.write_text(text)
    return text


def parse_target_list(html_text: str, base_url: str) -> list[TargetRow]:
    parser = TargetListParser(base_url)
    parser.feed(html_text)
    rows: list[TargetRow] = []
    for cells in parser.rows:
        cell_texts = [cell.get("text", "") for cell in cells]
        row_text = normalize_space(" ".join(cell_texts))
        target_match = re.search(r"\b[HTR]\d{4}(?:s\d+|v\d+)?\b", row_text)
        if not target_match:
            continue

        target_id = target_match.group(0)
        target_cell_index = next((i for i, text in enumerate(cell_texts) if target_id in text), 0)
        detail_url = ""
        for text, href in cells[target_cell_index].get("links", []):
            if target_id in text:
                detail_url = href
                break
        if not detail_url:
            detail_url = urllib.parse.urljoin(base_url, f"target.cgi?target={target_id}&view=all")

        values_after_target = cell_texts[target_cell_index + 1 :]
        target_type = values_after_target[0] if len(values_after_target) >= 1 else ""
        residues = None
        res_index = None
        for idx, value in enumerate(values_after_target):
            match = re.search(r"\b(\d{1,5})\b", value)
            if match:
                residues = int(match.group(1))
                res_index = idx
                break
        stoichiometry = values_after_target[res_index + 1] if res_index is not None and len(values_after_target) > res_index + 1 else ""
        description = cell_texts[-1] if cell_texts else ""
        # Dates and row numbers also look like four-character PDB IDs. Trust RCSB
        # structure links first, then explicit PDB code text if the row has no links.
        linked_pdbs: set[str] = set()
        for cell in cells:
            for text, href in cell.get("links", []):
                href_match = re.search(r"rcsb\.org/structure/([0-9A-Za-z]{4})\b", href)
                if href_match:
                    linked_pdbs.add(href_match.group(1).upper())
                elif "rcsb.org" in href and re.fullmatch(r"[0-9][A-Za-z0-9]{3}", text.strip()):
                    linked_pdbs.add(text.upper())
        pdb_ids = sorted(linked_pdbs)
        if not pdb_ids and re.search(r"\bPDB codes?\b", row_text, re.IGNORECASE):
            pdb_text = re.split(r"\bPDB codes?:?\b", row_text, flags=re.IGNORECASE)[-1]
            pdb_ids = sorted({match.upper() for match in re.findall(r"\b[0-9][A-Za-z0-9]{3}\b", pdb_text)})

        rows.append(
            TargetRow(
                domain_id=target_id,
                target_id=target_id,
                target_type=target_type,
                residues=residues,
                stoichiometry=normalize_space(stoichiometry),
                description=normalize_space(description),
                pdb_ids=pdb_ids,
                detail_url=detail_url,
                raw_text=row_text,
            )
        )
    return rows


def extract_sequence_from_detail(detail_text: str, target_id: str) -> str:
    extractor = TextExtractor()
    extractor.feed(detail_text)
    text = extractor.text()
    candidates: list[str] = []
    for match in re.finditer(r">[^\n\r]*\b" + re.escape(target_id) + r"\b[^\n\r]*[\r\n]+([^>]+)", text, re.IGNORECASE):
        block = re.split(r"\b(?:Template|PDB|Ligand|Target|Method|Additional Information)\b", match.group(1))[0]
        candidate = clean_sequence(block)
        if candidate.startswith("PLAINTEXTVERSION"):
            candidate = candidate[len("PLAINTEXTVERSION") :]
        candidates.append(candidate)
    if not candidates:
        seq_match = re.search(r"Sequence:\s*(?:\(Plain text version\))?\s*>?[^\n\r]*[\r\n]+([^>]+)", text, re.IGNORECASE)
        if seq_match:
            block = re.split(r"\b(?:Template|PDB|Ligand|Target|Method|Additional Information)\b", seq_match.group(1))[0]
            candidate = clean_sequence(block)
            if candidate.startswith("PLAINTEXTVERSION"):
                candidate = candidate[len("PLAINTEXTVERSION") :]
            candidates.append(candidate)
    candidates = [seq for seq in candidates if seq]
    if not candidates:
        return ""
    return max(candidates, key=len)


def tokenize_cif_value(lines: list[str], index: int) -> tuple[str, int]:
    line = lines[index]
    if line.startswith(";"):
        values = [line[1:]]
        index += 1
        while index < len(lines) and not lines[index].startswith(";"):
            values.append(lines[index])
            index += 1
        return "\n".join(values).strip(), index + 1
    parts = shlex.split(line, posix=True)
    return (parts[0] if parts else ""), index + 1


def shlex_tokens(line: str) -> list[str]:
    try:
        return shlex.split(line, posix=True)
    except ValueError:
        return line.split()


def parse_cif(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    data: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line == "#" or line.startswith("data_"):
            i += 1
            continue
        if line == "loop_":
            i += 1
            headers: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("_"):
                headers.append(lines[i].strip())
                i += 1
            tokens: list[str] = []
            while i < len(lines):
                raw = lines[i]
                stripped = raw.strip()
                if not stripped:
                    i += 1
                    continue
                if stripped == "#" or stripped == "loop_" or stripped.startswith("_") or stripped.startswith("data_"):
                    break
                if raw.startswith(";"):
                    value, i = tokenize_cif_value(lines, i)
                    tokens.append(value)
                else:
                    tokens.extend(shlex_tokens(stripped))
                    i += 1
            if headers:
                cols = {header: [] for header in headers}
                width = len(headers)
                for start in range(0, len(tokens) - len(tokens) % width, width):
                    for header, value in zip(headers, tokens[start : start + width]):
                        cols[header].append("" if value in {".", "?"} else value)
                data.update(cols)
            continue
        if line.startswith("_"):
            parts = line.split(None, 1)
            key = parts[0]
            if len(parts) == 2:
                data[key] = "" if parts[1] in {".", "?"} else parts[1].strip("'\"")
                i += 1
            else:
                value, i = tokenize_cif_value(lines, i + 1)
                data[key] = value
            continue
        i += 1
    return data


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def parse_fasta_chains(text: str) -> dict[str, tuple[str, str, str]]:
    records: dict[str, tuple[str, str, str]] = {}
    header = ""
    seq_parts: list[str] = []

    def flush() -> None:
        nonlocal header, seq_parts
        if not header:
            return
        sequence = clean_sequence("".join(seq_parts))
        entity_match = re.search(r"^[0-9A-Za-z]{4}_(\d+)", header)
        entity_id = entity_match.group(1) if entity_match else ""
        chain_match = re.search(r"\bChains?\s+([^|]+)", header)
        chains = []
        if chain_match:
            chains = [part.strip() for part in re.split(r"[,/]", chain_match.group(1)) if part.strip()]
        description = header
        for chain in chains:
            records[chain] = (sequence, entity_id, description)
        header = ""
        seq_parts = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            flush()
            header = line[1:]
        else:
            seq_parts.append(line)
    flush()
    return records


def parse_chain_records(cif_text: str, fasta_text: str) -> list[ChainRecord]:
    cif = parse_cif(cif_text)
    fasta_records = parse_fasta_chains(fasta_text)

    entity_descriptions: dict[str, str] = {}
    entity_ids = as_list(cif.get("_entity_poly.entity_id"))
    entity_types = as_list(cif.get("_entity_poly.type"))
    entity_names = as_list(cif.get("_entity.pdbx_description"))
    protein_entities = {
        entity_id
        for entity_id, entity_type in zip(entity_ids, entity_types)
        if entity_type.strip().lower() in PROTEIN_ENTITY_TYPES
    }
    for idx, entity_id in enumerate(as_list(cif.get("_entity.id"))):
        if idx < len(entity_names):
            entity_descriptions[entity_id] = entity_names[idx]

    label_to_entity = dict(zip(as_list(cif.get("_struct_asym.id")), as_list(cif.get("_struct_asym.entity_id"))))

    label_to_auth: dict[str, str] = {}
    residue_maps: dict[str, dict[int, str]] = {}
    scheme_labels = as_list(cif.get("_pdbx_poly_seq_scheme.asym_id"))
    scheme_auths = as_list(cif.get("_pdbx_poly_seq_scheme.pdb_strand_id")) or as_list(cif.get("_pdbx_poly_seq_scheme.auth_asym_id"))
    scheme_seq_ids = as_list(cif.get("_pdbx_poly_seq_scheme.seq_id"))
    scheme_auth_nums = as_list(cif.get("_pdbx_poly_seq_scheme.auth_seq_num")) or as_list(cif.get("_pdbx_poly_seq_scheme.pdb_seq_num"))
    for label, auth, seq_id, auth_num in zip(scheme_labels, scheme_auths, scheme_seq_ids, scheme_auth_nums):
        if not label:
            continue
        label_to_auth.setdefault(label, auth or label)
        if seq_id and auth_num:
            residue_maps.setdefault(label, {})[int(float(seq_id))] = auth_num

    resolved: dict[str, set[int]] = {}
    atom_names = as_list(cif.get("_atom_site.label_atom_id")) or as_list(cif.get("_atom_site.auth_atom_id"))
    atom_labels = as_list(cif.get("_atom_site.label_asym_id"))
    atom_auths = as_list(cif.get("_atom_site.auth_asym_id"))
    atom_seq_ids = as_list(cif.get("_atom_site.label_seq_id"))
    for atom, label, auth, seq_id in zip(atom_names, atom_labels, atom_auths, atom_seq_ids):
        if atom != "CA" or not seq_id:
            continue
        key = label or auth
        if not key:
            continue
        try:
            resolved.setdefault(key, set()).add(int(float(seq_id)))
        except ValueError:
            continue

    records: list[ChainRecord] = []
    seen: set[str] = set()
    for chain_id, (sequence, entity_id, description) in fasta_records.items():
        label_candidates = [label for label, auth in label_to_auth.items() if auth == chain_id]
        label = label_candidates[0] if label_candidates else chain_id
        entity_id = entity_id or label_to_entity.get(label, "")
        if protein_entities and entity_id not in protein_entities:
            continue
        records.append(
            ChainRecord(
                chain_id=chain_id,
                label_asym_id=label,
                entity_id=entity_id,
                sequence=sequence,
                description=entity_descriptions.get(entity_id, description),
                label_to_auth=residue_maps.get(label, {}),
                resolved_ca_positions=resolved.get(label, set()),
            )
        )
        seen.add(chain_id)

    for label, entity_id in label_to_entity.items():
        chain_id = label_to_auth.get(label, label)
        if chain_id in seen or (protein_entities and entity_id not in protein_entities):
            continue
        seq = ""
        for fasta_chain, (fasta_seq, fasta_entity, description) in fasta_records.items():
            if fasta_entity == entity_id:
                seq = fasta_seq
                break
        if not seq:
            continue
        records.append(
            ChainRecord(
                chain_id=chain_id,
                label_asym_id=label,
                entity_id=entity_id,
                sequence=seq,
                description=entity_descriptions.get(entity_id, ""),
                label_to_auth=residue_maps.get(label, {}),
                resolved_ca_positions=resolved.get(label, set()),
            )
        )
    return records


def align_sequences(target: str, chain: str) -> AlignmentResult:
    target = clean_sequence(target)
    chain = clean_sequence(chain)
    if not target or not chain:
        return AlignmentResult(0.0, 0.0, 0, 0, 0, 0, 0, 0)
    exact = chain.find(target)
    if exact >= 0:
        return AlignmentResult(1.0, 1.0, 1, len(target), exact + 1, exact + len(target), len(target), len(target))

    try:
        from Bio import Align  # type: ignore

        aligner = Align.PairwiseAligner()
        aligner.mode = "local"
        aligner.match_score = 2
        aligner.mismatch_score = -1
        aligner.open_gap_score = -10
        aligner.extend_gap_score = -0.5
        alignment = aligner.align(target, chain)[0]
        target_blocks = alignment.aligned[0]
        chain_blocks = alignment.aligned[1]
        aligned = 0
        identical = 0
        target_start = int(target_blocks[0][0]) + 1 if len(target_blocks) else 0
        target_end = int(target_blocks[-1][1]) if len(target_blocks) else 0
        chain_start = int(chain_blocks[0][0]) + 1 if len(chain_blocks) else 0
        chain_end = int(chain_blocks[-1][1]) if len(chain_blocks) else 0
        for (t0, t1), (c0, c1) in zip(target_blocks, chain_blocks):
            span = min(int(t1 - t0), int(c1 - c0))
            aligned += span
            identical += sum(1 for offset in range(span) if target[int(t0) + offset] == chain[int(c0) + offset])
        identity = identical / aligned if aligned else 0.0
        coverage = aligned / len(target) if target else 0.0
        return AlignmentResult(identity, coverage, target_start, target_end, chain_start, chain_end, aligned, identical)
    except Exception:
        from difflib import SequenceMatcher

        matcher = SequenceMatcher(None, target, chain, autojunk=False)
        blocks = [block for block in matcher.get_matching_blocks() if block.size]
        if not blocks:
            return AlignmentResult(0.0, 0.0, 0, 0, 0, 0, 0, 0)
        aligned = sum(block.size for block in blocks)
        target_start = blocks[0].a + 1
        target_end = blocks[-1].a + blocks[-1].size
        chain_start = blocks[0].b + 1
        chain_end = blocks[-1].b + blocks[-1].size
        identity = aligned / aligned
        coverage = aligned / len(target)
        return AlignmentResult(identity, coverage, target_start, target_end, chain_start, chain_end, aligned, aligned)


def choose_chain(target_sequence: str, chains: list[ChainRecord]) -> tuple[ChainRecord | None, AlignmentResult, list[tuple[ChainRecord, AlignmentResult]]]:
    scored = [(chain, align_sequences(target_sequence, chain.sequence)) for chain in chains]
    scored.sort(key=lambda item: (item[1].coverage, item[1].identity, len(item[0].resolved_ca_positions)), reverse=True)
    if not scored:
        return None, AlignmentResult(0, 0, 0, 0, 0, 0, 0, 0), []
    best_chain, best_alignment = scored[0]
    alternatives = [
        (chain, aln)
        for chain, aln in scored[1:]
        if abs(aln.identity - best_alignment.identity) <= 0.001 and abs(aln.coverage - best_alignment.coverage) <= 0.001
    ]
    return best_chain, best_alignment, alternatives


def reference_coverage(chain: ChainRecord, alignment: AlignmentResult, target_length: int) -> float:
    if not chain or not target_length or not chain.resolved_ca_positions:
        return 0.0
    start = max(1, alignment.chain_start)
    end = max(start, alignment.chain_end)
    resolved = sum(1 for pos in range(start, end + 1) if pos in chain.resolved_ca_positions)
    return min(1.0, resolved / target_length)


def classify_row(
    target: TargetRow,
    sequence: str,
    pdb_id: str,
    chain: ChainRecord | None,
    alignment: AlignmentResult,
    ref_cov: float,
    alternatives: list[tuple[ChainRecord, AlignmentResult]],
) -> tuple[str, str, str]:
    reasons: list[str] = []
    text = f"{target.target_type} {target.description} {target.raw_text}".lower()
    is_rna = "rna" in text or target.target_id.startswith("R")
    is_ligand_aux = "not a ts target" in text or "auxiliary structure" in text or "ligand-only" in text
    canceled = "canceled" in text or "cancelled" in text

    if not pdb_id:
        reasons.append("no PDB/reference available")
    if is_rna:
        reasons.append("RNA target")
    if canceled:
        reasons.append("canceled target")
    if is_ligand_aux:
        reasons.append("not a TS target or ligand-only auxiliary target")
    if target.stoichiometry and target.stoichiometry != "A1":
        reasons.append(f"stoichiometry is {target.stoichiometry}, not A1")
    if not sequence:
        reasons.append("CASP target sequence could not be extracted")
    if sequence and target.residues and abs(len(sequence) - target.residues) > max(3, int(target.residues * 0.05)):
        reasons.append(f"sequence length {len(sequence)} does not match Res column {target.residues}")
    if sequence and pdb_id and chain is None:
        reasons.append("sequence-to-chain mapping fails")
    if chain is not None:
        if alignment.identity < 0.95 or alignment.coverage < 0.90:
            reasons.append(f"sequence-to-chain mapping below threshold identity={alignment.identity:.3f} coverage={alignment.coverage:.3f}")
        if ref_cov < 0.80:
            reasons.append(f"reference coverage below threshold {ref_cov:.3f}")

    fatal = any(
        reason.startswith(prefix)
        for reason in reasons
        for prefix in [
            "no PDB",
            "RNA",
            "canceled",
            "not a TS",
            "stoichiometry is",
            "CASP target sequence",
            "sequence-to-chain mapping fails",
            "sequence-to-chain mapping below",
        ]
    )
    confidence = "failed" if chain is None or not sequence else "high"
    if chain is not None and (alignment.identity < 0.95 or alignment.coverage < 0.90):
        confidence = "low"
    elif chain is not None and ref_cov < 0.80:
        confidence = "medium"

    if fatal:
        return "No", confidence, "; ".join(reasons)

    check_reasons: list[str] = []
    if alternatives:
        check_reasons.append("multiple equivalent chain copies match")
    if ref_cov < 0.95:
        check_reasons.append("high identity mapping but reference coverage is incomplete")
    if target.residues and target.residues > 1000:
        check_reasons.append("target is very large >1000 aa")
    if re.search(r"s\d+$", target.target_id, re.IGNORECASE) or target.target_id.startswith("H"):
        check_reasons.append("subtarget or heteromer-associated target needs manual inspection")
    if chain and (alignment.chain_start not in chain.label_to_auth or alignment.chain_end not in chain.label_to_auth):
        check_reasons.append("sequence-to-chain mapping found, but PDB residue-number mapping unresolved")
        confidence = "medium" if confidence == "high" else confidence

    if check_reasons:
        return "Check", confidence, "; ".join(check_reasons)
    return "Yes", confidence, "strict A1 protein target with high-confidence sequence-to-chain mapping"


def format_float(value: float) -> str:
    return f"{value:.6f}" if value == value else ""


def build_manifest(args: argparse.Namespace) -> list[dict[str, str]]:
    cache_dir = Path(args.cache_dir)
    target_html = fetch_cached(args.target_list_url, cache_dir / args.casp_round.lower() / "targetlist.html", args.force_refresh)
    target_rows = parse_target_list(target_html, args.target_list_url)
    if args.max_targets:
        target_rows = target_rows[: args.max_targets]

    output_rows: list[dict[str, str]] = []
    for index, target in enumerate(target_rows, start=1):
        if args.verbose:
            print(f"[{args.casp_round}] {index}/{len(target_rows)} {target.target_id}", file=sys.stderr)
        pdb_id = target.pdb_ids[0] if target.pdb_ids else ""
        sequence = ""
        if target.detail_url:
            try:
                detail_text = fetch_cached(
                    target.detail_url,
                    cache_dir / args.casp_round.lower() / "details" / f"{target.target_id}.html",
                    args.force_refresh,
                )
                sequence = extract_sequence_from_detail(detail_text, target.target_id)
            except Exception as exc:
                if args.verbose:
                    print(f"  detail fetch/parse failed: {exc}", file=sys.stderr)

        chain = None
        alignment = AlignmentResult(0, 0, 0, 0, 0, 0, 0, 0)
        alternatives: list[tuple[ChainRecord, AlignmentResult]] = []
        ref_cov = 0.0
        if pdb_id and sequence:
            try:
                rcsb_dir = Path("data/cache/rcsb") / pdb_id.lower()
                cif_text = fetch_cached(f"https://files.rcsb.org/download/{pdb_id}.cif", rcsb_dir / f"{pdb_id.lower()}.cif", args.force_refresh)
                fasta_text = fetch_cached(f"https://www.rcsb.org/fasta/entry/{pdb_id}", rcsb_dir / f"{pdb_id.lower()}.fasta", args.force_refresh)
                chains = parse_chain_records(cif_text, fasta_text)
                chain, alignment, alternatives = choose_chain(sequence, chains)
                if chain:
                    ref_cov = reference_coverage(chain, alignment, len(sequence))
            except Exception as exc:
                if args.verbose:
                    print(f"  RCSB fetch/parse failed for {pdb_id}: {exc}", file=sys.stderr)

        should_use, confidence, reason = classify_row(target, sequence, pdb_id, chain, alignment, ref_cov, alternatives)
        residue_start = "TBD"
        residue_end = "TBD"
        if chain and alignment.chain_start in chain.label_to_auth and alignment.chain_end in chain.label_to_auth:
            residue_start = chain.label_to_auth[alignment.chain_start]
            residue_end = chain.label_to_auth[alignment.chain_end]
        alternative_text = ";".join(
            f"{alt.chain_id}:{aln.identity:.3f}/{aln.coverage:.3f}" for alt, aln in alternatives[:10]
        )
        output_rows.append(
            {
                "casp_round": args.casp_round,
                "domain_id": target.domain_id,
                "target_id": target.target_id,
                "pdb_id": pdb_id,
                "chain_id": chain.chain_id if chain else "",
                "residue_start": residue_start,
                "residue_end": residue_end,
                "sequence_start": str(alignment.target_start or 1 if sequence else ""),
                "sequence_end": str(alignment.target_end or len(sequence) if sequence else ""),
                "sequence": sequence,
                "target_length": str(target.residues or len(sequence) or ""),
                "type": target.target_type,
                "stoichiometry": target.stoichiometry,
                "description": target.description,
                "target_list_url": args.target_list_url,
                "target_detail_url": target.detail_url,
                "rcsb_url": f"https://www.rcsb.org/structure/{pdb_id}" if pdb_id else "",
                "mapping_identity": format_float(alignment.identity),
                "mapping_coverage": format_float(alignment.coverage),
                "mapping_alignment_start": str(alignment.chain_start or ""),
                "mapping_alignment_end": str(alignment.chain_end or ""),
                "pdb_entity_id": chain.entity_id if chain else "",
                "pdb_polymer_entity_description": chain.description if chain else "",
                "reference_coverage": format_float(ref_cov),
                "resolved_residue_count": str(len(chain.resolved_ca_positions) if chain else ""),
                "chain_assignment_confidence": confidence,
                "should_use": should_use,
                "reason": reason,
                "alternative_chain_matches": alternative_text,
            }
        )
    return output_rows


def write_qc_summary(rows: list[dict[str, str]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    counters = {
        "rows": Counter({"total": len(rows)}),
        "casp_round": Counter(row.get("casp_round", "") for row in rows),
        "should_use": Counter(row.get("should_use", "") for row in rows),
        "stoichiometry": Counter(row.get("stoichiometry", "") for row in rows),
        "type": Counter(row.get("type", "") for row in rows),
        "chain_assignment_confidence": Counter(row.get("chain_assignment_confidence", "") for row in rows),
        "check_reason": Counter(reason_part(row) for row in rows if row.get("should_use") == "Check"),
        "no_reason": Counter(reason_part(row) for row in rows if row.get("should_use") == "No"),
    }
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["section", "value", "count"])
        writer.writeheader()
        for section, counter in counters.items():
            for value, count in counter.most_common():
                writer.writerow({"section": section, "value": value, "count": count})


def reason_part(row: dict[str, str]) -> str:
    reason = row.get("reason", "")
    return reason.split(";")[0].strip() if reason else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a CASP solved-target manifest with sequence-based PDB chain assignment.")
    parser.add_argument("--casp-round", required=True, choices=["CASP15", "CASP16"])
    parser.add_argument("--target-list-url", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--strict-all-groups-only", action="store_true")
    parser.add_argument("--strict-a1-only", action="store_true")
    parser.add_argument("--include-unsolved", action="store_true")
    parser.add_argument("--cache-dir", default="data/cache/casp_targets")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--max-targets", type=int, default=0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    rows = build_manifest(args)
    if args.strict_all_groups_only:
        rows = [row for row in rows if "All groups" in row.get("type", "")]
    if args.strict_a1_only:
        rows = [row for row in rows if row.get("stoichiometry") == "A1"]
    if not args.include_unsolved:
        # Keep parsed rows with no PDB in the manifest if they were already parsed; this flag is kept
        # for CLI compatibility with the instruction and future stricter modes.
        pass

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    write_qc_summary(rows, output.with_name(output.stem + "_qc_summary.csv"))
    print(f"Rows parsed: {len(rows)}")
    print(f"Rows with PDB codes: {sum(1 for row in rows if row.get('pdb_id'))}")
    print(f"Rows with extracted sequences: {sum(1 for row in rows if row.get('sequence'))}")
    print(f"High-confidence chain mappings: {sum(1 for row in rows if row.get('chain_assignment_confidence') == 'high')}")
    print("should_use counts:", json.dumps(Counter(row.get("should_use", "") for row in rows), sort_keys=True))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
