# Agent Guide

This repository is a local benchmark harness for protein folding models. Preserve the benchmark interface and avoid large or destructive changes unless the user explicitly asks for them.

## Project Invariants

- Keep the standardized runner interface:
  ```bash
  bash runners/run_MODEL.sh input.fasta output_dir top_k
  ```
- Keep standardized prediction output:
  ```text
  rank_001.pdb
  rank_002.pdb
  ...
  metadata.json
  ```
- Keep the benchmark driver independent from model-specific environments.
- Do not merge all folding models into one conda environment.
- Do not download large AlphaFold, ColabFold, or RoseTTAFold databases unless explicitly requested.
- Do not delete model repositories, Python files, Bash files, notebooks, or generated reference files without explicit permission.
- Prefer robust Bash scripts with:
  ```bash
  set -euo pipefail
  ```
- Use this portable conda initialization pattern in all runners:
  ```bash
  CONDA_BASE="$(conda info --base)"
  source "${CONDA_BASE}/etc/profile.d/conda.sh"
  conda activate ENV_NAME
  ```

## Current Benchmark Targets

```text
Target ID: 1UAO_chignolin
PDB ID: 1UAO
Sequence: GYDPETGTWG
Reference structure: data/references/1UAO_model1_chainA.pdb
Reference chain: A

Target ID: 1UBQ_ubiquitin
PDB ID: 1UBQ
Sequence: MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG
Reference structure: data/references/1UBQ_chainA.pdb
Reference chain: A
```

## Coding Conventions

- Python scripts should use `argparse`.
- Use `pathlib.Path`.
- Emit clear error messages.
- Keep failed model predictions from crashing the entire pipeline.
- Log each model run to `logs/{target_id}_{model}.log`.
- Scoring scripts should preserve failed predictions in the output CSV with an `error` column.
- Canonical benchmark scoring should use `--config configs/models.yaml --only-enabled-models` so stale or deprecated prediction folders are not included in score CSVs.
- The canonical Boltz backend ID is `boltz2`; the old `boltz` ID is deprecated and should only appear as a compatibility wrapper or upstream repository/environment name.

## Mandatory Codex Execution Logs

For every Codex instruction or task, create a corresponding execution log under:

```text
codex-plan/
```

The log filename should have the execution date prepended in `YYYYMMDD_` format and be based on the instruction name or purpose, for example:

```text
codex-plan/20260514_add_1ubq_multitarget_benchmark.log
```

Each log must include:

1. The date/time of execution.
2. The instruction/task name.
3. The initial project state observed by Codex.
4. The commands that were run.
5. The files created or modified.
6. The environments activated or modified.
7. The tests or validation commands that were run.
8. The results of each validation step.
9. Any errors encountered, including exact error messages or log paths.
10. Follow-up recommendations for ChatGPT/user.

Use this log to make future ChatGPT follow-up easier. Do not omit the log, even if the task is small.

If the task fails partway through, still write the log and clearly mark:

```text
STATUS: FAILED
```

If the task completes successfully, mark:

```text
STATUS: COMPLETED
```

If the task partially completes, mark:

```text
STATUS: PARTIAL
```

## Documentation

Whenever the pipeline changes, update:

- `README.md`
- `AGENTS.md`, if agent behavior changed
- `docs/`, if setup or model-specific instructions changed
