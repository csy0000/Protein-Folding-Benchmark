# Project Scope

This repository provides a local benchmark harness for protein folding models. The scientific goal is to compare local folding backends under one standardized prediction and scoring workflow, with consistent sequence inputs, runner calls, output names, and reference-based metrics.

The first debug target is Chignolin / `1UAO_chignolin`, using sequence `GYDPETGTWG` and reference structure `data/references/1UAO_model1_chainA.pdb`. Chignolin is a smoke-test peptide target.

The first larger single-chain protein benchmark target is ubiquitin / `1UBQ_ubiquitin`, using chain A from `1UBQ` and reference structure `data/references/1UBQ_chainA.pdb`.

Benchmark targets are defined in `data/targets/targets.csv`. The current active target set is exactly these two targets.

## Benchmark Backends

The benchmark scope is exactly 9 backend IDs:

1. `esmfold` - ESMFold
2. `omegafold` - OmegaFold
3. `chai1` - Chai-1
4. `boltz2` - Boltz-2
5. `openfold` - OpenFold
6. `openfold3` - OpenFold3
7. `colabfold` - ColabFold
8. `alphafold2` - AlphaFold2
9. `alphafold3` - AlphaFold3

## Model Families

AF2-style / MSA-template family:

- AlphaFold2
- OpenFold
- ColabFold

AF3-style / biomolecular family:

- AlphaFold3
- OpenFold3
- Boltz-2
- Chai-1

Single-sequence language-model / sequence-only baselines:

- ESMFold
- OmegaFold

## Metrics

Current metrics:

- lDDT-C-alpha
- C-alpha RMSD
- TM-align / US-align RMSD
- TM-score normalized by reference length
- TM-score normalized by prediction length
- Aligned length

Primary ranking metric:

- lDDT-C-alpha, `lddt_ca`, higher is better

Secondary ranking metric:

- TM-score normalized by reference length, `tmalign_tm_score_ref`, higher is better

Diagnostic metrics:

- TM-align / US-align RMSD, `tmalign_rmsd`, lower is better
- C-alpha RMSD, `ca_rmsd`, lower is better

Future metrics:

- GDT_TS
- Runtime
- GPU memory
- Energy / CO2 estimates

## Top-k Policy

The benchmark convention is to request up to the top 5 predicted structures per model. `top_k=5` is a request, not a guarantee.

Deterministic models must not duplicate one structure into multiple ranks. A single-output backend should write only `rank_001.pdb` and record `top_k_generated: 1` in `metadata.json`. Multi-sample backends should record the raw source files that produced each standardized rank.

## Multi-Target Workflow

`scripts/04_run_benchmark_targets.py` runs prediction, scoring, and per-target model summaries for every target in `data/targets/targets.csv`.

`scripts/05_summarize_all_targets.py` aggregates per-target model summaries into `data/scores/all_targets_model_summary.csv` and `data/scores/all_targets_model_summary.md`.

The current enabled and validated local backends are `esmfold`, `omegafold`, `chai1`, `boltz2`, `colabfold`, and `openfold`. OpenFold is validated in single-sequence smoke mode; full OpenFold MSA/template inference requires real OpenFold-compatible database paths. AlphaFold3 remains disabled as a future optional restricted/non-commercial baseline; do not enable it until model parameter and output usage terms are resolved for the intended use.
