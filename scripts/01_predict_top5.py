#!/usr/bin/env python3

import argparse
import shlex
import subprocess
import yaml
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--config", default="configs/models.yaml")
    parser.add_argument("--outdir", default="data/predictions")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    root = Path.cwd()
    fasta_path = Path(args.fasta)
    target_dir = root / args.outdir / args.target_id
    target_dir.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)

    with open(args.config) as f:
        config = yaml.safe_load(f)

    for model_name, model_cfg in config["models"].items():
        if not model_cfg.get("enabled", False):
            continue

        model_out = target_dir / model_name
        model_out.mkdir(parents=True, exist_ok=True)

        runner_cmd = shlex.split(model_cfg["runner"])
        cmd = runner_cmd + [str(fasta_path), str(model_out), str(args.top_k)]

        print(f"\n[run] {model_name}")
        print(" ".join(cmd))

        log_file = root / "logs" / f"{args.target_id}_{model_name}.log"
        with log_file.open("w") as log:
            try:
                subprocess.run(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"[failed] {model_name}; see {log_file}")
                continue

        print(f"[done] {model_name}: {model_out}")

    print(f"\nPredictions written to: {target_dir}")


if __name__ == "__main__":
    main()
