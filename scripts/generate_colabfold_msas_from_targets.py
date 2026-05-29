#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import os
import shutil
import shlex
import subprocess
import sys
import time
from pathlib import Path

from carbon_tracking import CarbonRunTracker, empty_carbon_metadata

MSA_METADATA_COLUMNS = [
    "target_id",
    "pdb_id",
    "chain",
    "sequence_length",
    "fasta_file",
    "msa_dir",
    "a3m_file",
    "pairing_a3m_file",
    "non_pairing_a3m_file",
    "msa_status",
    "msa_exit_code",
    "msa_runtime_sec",
    "msa_carbon_emissions_kg",
    "msa_carbon_emissions_g",
    "msa_energy_consumed_kwh",
    "msa_carbon_country_iso_code",
    "msa_carbon_intensity_mode",
    "msa_carbon_intensity_g_per_kwh",
    "msa_log_file",
    "msa_database",
    "msa_database_path",
    "msa_source",
    "msa_command",
    "notes",
]


def read_targets(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        required = {"target_id", "sequence"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"Target CSV is missing required columns: {sorted(missing)}")
        return list(reader)


def write_fasta(target_id: str, sequence: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    seq = "".join(sequence.split()).upper()
    wrapped = "\n".join(seq[i : i + 80] for i in range(0, len(seq), 80))
    output.write_text(f">{target_id}\n{wrapped}\n")


def choose_a3m(raw_dir: Path) -> Path | None:
    files = sorted(raw_dir.rglob("*.a3m"), key=lambda p: (-p.stat().st_size, str(p)))
    return files[0] if files else None


def normalize_msa(target_id: str, target_dir: Path, raw_a3m: Path) -> tuple[Path, Path, Path]:
    main = target_dir / f"{target_id}.a3m"
    non_pairing = target_dir / "non_pairing.a3m"
    cfdb = target_dir / "cfdb_hits.a3m"
    for dest in (main, non_pairing, cfdb):
        if dest.resolve() != raw_a3m.resolve():
            shutil.copy2(raw_a3m, dest)
    pairing = target_dir / "pairing.a3m"
    if not pairing.exists():
        pairing.write_text("")
    return main, pairing, non_pairing


def write_metadata(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MSA_METADATA_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in MSA_METADATA_COLUMNS})


def row_from_carbon(prefix: str, carbon: dict[str, object]) -> dict[str, object]:
    return {
        f"{prefix}_carbon_emissions_kg": carbon.get("carbon_emissions_kg", ""),
        f"{prefix}_carbon_emissions_g": carbon.get("carbon_emissions_g", ""),
        f"{prefix}_energy_consumed_kwh": carbon.get("carbon_energy_consumed_kwh", ""),
        f"{prefix}_carbon_country_iso_code": carbon.get("carbon_country_iso_code", ""),
        f"{prefix}_carbon_intensity_mode": carbon.get("carbon_intensity_mode", ""),
        f"{prefix}_carbon_intensity_g_per_kwh": carbon.get("carbon_intensity_g_per_kwh", ""),
    }


def run_target(target: dict[str, str], args: argparse.Namespace) -> dict[str, object]:
    target_id = target["target_id"]
    sequence = "".join(target["sequence"].split()).upper()
    fasta = Path(args.sequences_dir) / f"{target_id}.fasta"
    target_dir = Path(args.msa_output_dir) / target_id
    raw_dir = target_dir / "raw"
    log_file = Path(args.logs_dir) / f"{target_id}_colabfold_search.log"
    existing = target_dir / f"{target_id}.a3m"

    if args.skip_existing and existing.exists() and not args.force:
        carbon = empty_carbon_metadata(False, args.carbon_country_iso_code)
        return {
            "target_id": target_id,
            "pdb_id": target.get("pdb_id", ""),
            "chain": target.get("chain_id", target.get("chain", "")),
            "sequence_length": len(sequence),
            "fasta_file": str(fasta),
            "msa_dir": str(target_dir),
            "a3m_file": str(existing),
            "pairing_a3m_file": str(target_dir / "pairing.a3m") if (target_dir / "pairing.a3m").exists() else "",
            "non_pairing_a3m_file": str(target_dir / "non_pairing.a3m") if (target_dir / "non_pairing.a3m").exists() else "",
            "msa_status": "skipped_existing",
            "msa_exit_code": 0,
            "msa_runtime_sec": "0.000000",
            "msa_log_file": str(log_file),
            "msa_database": "colabfold",
            "msa_database_path": args.colabfold_db,
            "msa_source": "colabfold_mmseqs2",
            "msa_command": "",
            "notes": "Reused existing shared MSA; timing/carbon not measured in this invocation",
            **row_from_carbon("msa", carbon),
        }

    if args.force and target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    Path(args.logs_dir).mkdir(parents=True, exist_ok=True)
    write_fasta(target_id, sequence, fasta)

    cmd = [
        "conda",
        "run",
        "-n",
        args.colabfold_env,
        "colabfold_search",
        "--mmseqs",
        args.mmseqs_bin,
        "--gpu",
        str(args.gpu),
        "--threads",
        str(args.threads),
        str(fasta),
        args.colabfold_db,
        str(raw_dir),
    ]
    env = os.environ.copy()
    env["PATH"] = str(Path(args.mmseqs_bin).parent) + os.pathsep + env.get("PATH", "")
    tracker = CarbonRunTracker(
        enabled=args.track_carbon,
        output_dir=Path(args.metadata_out).parent / "carbon",
        country_iso_code=args.carbon_country_iso_code,
        project_name=args.carbon_project_name,
        measure_power_secs=args.carbon_measure_power_secs,
        run_label=f"msa_{target_id}",
    )
    start = time.perf_counter()
    tracker.start()
    with log_file.open("w") as log:
        log.write("$ " + " ".join(shlex.quote(part) for part in cmd) + "\n\n")
        completed = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, text=True, check=False, env=env)
        log.write(f"\n[exit_code={completed.returncode}]\n")
    elapsed = time.perf_counter() - start
    carbon = tracker.stop()

    raw_a3m = choose_a3m(raw_dir)
    status = "success" if completed.returncode == 0 and raw_a3m is not None else "failed"
    a3m_file = pairing_file = non_pairing_file = Path("")
    notes = ""
    if raw_a3m is not None:
        a3m_file, pairing_file, non_pairing_file = normalize_msa(target_id, target_dir, raw_a3m)
        notes = f"Normalized from {raw_a3m}; monomer target uses non_pairing.a3m and leaves pairing.a3m empty"
    elif completed.returncode == 0:
        notes = "colabfold_search exited 0 but no .a3m file was found"
    else:
        notes = f"colabfold_search failed; see {log_file}"

    return {
        "target_id": target_id,
        "pdb_id": target.get("pdb_id", ""),
        "chain": target.get("chain_id", target.get("chain", "")),
        "sequence_length": len(sequence),
        "fasta_file": str(fasta),
        "msa_dir": str(target_dir),
        "a3m_file": str(a3m_file) if a3m_file else "",
        "pairing_a3m_file": str(pairing_file) if pairing_file else "",
        "non_pairing_a3m_file": str(non_pairing_file) if non_pairing_file else "",
        "msa_status": status,
        "msa_exit_code": completed.returncode,
        "msa_runtime_sec": f"{elapsed:.6f}",
        "msa_log_file": str(log_file),
        "msa_database": "colabfold",
        "msa_database_path": args.colabfold_db,
        "msa_source": "colabfold_mmseqs2",
        "msa_command": " ".join(shlex.quote(part) for part in cmd),
        "notes": notes,
        **row_from_carbon("msa", carbon),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one shared ColabFold/MMseqs2 MSA per target with timing/carbon metadata.")
    parser.add_argument("--targets", required=True)
    parser.add_argument("--sequences-dir", required=True)
    parser.add_argument("--msa-output-dir", required=True)
    parser.add_argument("--logs-dir", required=True)
    parser.add_argument("--metadata-out", required=True)
    parser.add_argument("--colabfold-db", required=True)
    parser.add_argument("--mmseqs-bin", required=True)
    parser.add_argument("--track-carbon", action="store_true")
    parser.add_argument("--carbon-country-iso-code", default="WORLD")
    parser.add_argument("--carbon-project-name", default="protein_folding_shared_msa")
    parser.add_argument("--carbon-measure-power-secs", type=float, default=1.0)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--colabfold-env", default="colabfold")
    parser.add_argument("--threads", type=int, default=64)
    parser.add_argument("--gpu", type=int, default=1)
    args = parser.parse_args()

    if args.force and args.skip_existing:
        raise SystemExit("Use either --force or --skip-existing, not both")
    if not Path(args.colabfold_db).is_dir():
        raise SystemExit(f"ColabFold DB does not exist: {args.colabfold_db}")
    if not Path(args.mmseqs_bin).is_file():
        raise SystemExit(f"MMseqs binary does not exist: {args.mmseqs_bin}")

    rows = []
    for target in read_targets(Path(args.targets)):
        print(f"[msa] {target['target_id']}")
        row = run_target(target, args)
        rows.append(row)
        print(f"[{row['msa_status']}] {target['target_id']} {row.get('a3m_file', '')}")
    write_metadata(Path(args.metadata_out), rows)
    print(f"Shared MSA metadata: {args.metadata_out}")
    failed = [row for row in rows if row.get("msa_status") not in {"success", "skipped_existing"}]
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
