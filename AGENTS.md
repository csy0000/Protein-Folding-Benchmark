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
- Record inference timing metadata for model runs when using `scripts/run_benchmark_from_targets.py`; keep timing in seconds and merge it into score CSVs when available.
- Scoring scripts should preserve failed predictions in the output CSV with an `error` column.
- Canonical benchmark scoring should use `--config configs/models.yaml --only-enabled-models` so stale or deprecated prediction folders are not included in score CSVs.
- The canonical Boltz backend ID is `boltz2`; the old `boltz` ID is deprecated and should only appear as a compatibility wrapper or upstream repository/environment name.

## Optional Codex Execution Logs

Do not create Codex execution logs by default. Only write a log file under `codex-plan/` when the user explicitly asks for one.

When requested, use a `YYYYMMDD_` filename prefix and include the date/time, task name, project state, commands run, files created or modified, environments activated or modified, validation steps and results, errors encountered, and follow-up recommendations. Mark the result as `STATUS: COMPLETED`, `STATUS: PARTIAL`, or `STATUS: FAILED`.

## Documentation

Whenever the pipeline changes, update:

- `README.md`
- `AGENTS.md`, if agent behavior changed
- `docs/`, if setup or model-specific instructions changed

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
