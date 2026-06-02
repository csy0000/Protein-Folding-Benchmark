#!/usr/bin/env python3
"""Run a command while collecting CodeCarbon metadata."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

from carbon_tracking import CarbonRunTracker


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-json", required=True, type=Path)
    parser.add_argument("--carbon-dir", required=True, type=Path)
    parser.add_argument("--label", required=True)
    parser.add_argument("--country-iso-code", default="WORLD")
    parser.add_argument("--measure-power-secs", default=1.0, type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("command is required after --")
    return args


def main() -> None:
    args = parse_args()
    tracker = CarbonRunTracker(
        enabled=True,
        output_dir=args.carbon_dir,
        country_iso_code=args.country_iso_code,
        project_name="protein_folding_benchmark",
        measure_power_secs=args.measure_power_secs,
        run_label=args.label,
    )
    start = time.monotonic()
    return_code = 1
    command_error = ""
    tracker.start()
    try:
        completed = subprocess.run(args.command, check=False)
        return_code = completed.returncode
    except Exception as exc:
        command_error = repr(exc)
    finally:
        carbon = tracker.stop()
    elapsed = time.monotonic() - start
    payload = {
        **carbon,
        "command": args.command,
        "command_return_code": return_code,
        "command_error": command_error,
        "elapsed_sec": elapsed,
    }
    args.metadata_json.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_json.write_text(json.dumps(payload, indent=2) + "\n")
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
