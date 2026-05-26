#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def archive_path(path: Path, archive_dir: Path) -> Path:
    try:
        relative = path.relative_to("results")
    except ValueError:
        relative = Path(path.name)
    return archive_dir / relative


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive test-only benchmark artifacts listed in a cleanup manifest.")
    parser.add_argument("--manifest", default="results/consolidated/test_artifact_cleanup_manifest.csv")
    parser.add_argument("--archive-dir", default="results/_archived_test_artifacts_20260526")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    rows = read_manifest(Path(args.manifest))
    archive_dir = Path(args.archive_dir)
    candidates = [
        Path(row["path"])
        for row in rows
        if row.get("cleanup_action") == "archive" and row.get("safe_to_remove", "").lower() == "true"
    ]

    print(f"Archive candidates: {len(candidates)}")
    moved = 0
    skipped = 0
    for source in candidates:
        if not source.exists():
            print(f"SKIP missing {source}")
            skipped += 1
            continue
        destination = archive_path(source, archive_dir)
        if destination.exists():
            print(f"SKIP destination exists {destination}")
            skipped += 1
            continue
        print(f"{'MOVE' if args.execute else 'DRY-RUN'} {source} -> {destination}")
        if args.execute:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            moved += 1

    print(f"Moved: {moved}")
    print(f"Skipped: {skipped}")
    if not args.execute:
        print("Dry run only. Re-run with --execute to move files.")


if __name__ == "__main__":
    main()
