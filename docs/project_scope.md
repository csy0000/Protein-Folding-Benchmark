# Project Scope

This repository provides a local benchmark harness for protein folding models. The scientific goal is to compare local folding backends under one standardized prediction and scoring workflow, with consistent sequence inputs, runner calls, output names, and reference-based metrics.

The first debug target is Chignolin / `1UAO_chignolin`, using sequence `GYDPETGTWG` and reference structure `data/references/1UAO_model1_chainA.pdb`. Chignolin is a smoke-test peptide target.

The first larger single-chain protein benchmark target is ubiquitin / `1UBQ_ubiquitin`, using chain A from `1UBQ` and reference structure `data/references/1UBQ_chainA.pdb`.

Benchmark targets are defined in `data/targets/targets.csv`.

## Benchmark Backends

The benchmark scope is exactly 9 backend IDs:

1. `openfold` - OpenFold
2. `openfold3` - OpenFold3
3. `boltz2` - Boltz-2
4. `chai1` - Chai-1
5. `esmfold` - ESMFold
6. `colabfold` - ColabFold
7. `alphafold2` - AlphaFold2
8. `alphafold3` - AlphaFold3
9. `omegafold` - OmegaFold

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

- C-alpha RMSD
- TM-align / US-align RMSD
- TM-score normalized by reference length
- TM-score normalized by prediction length
- Aligned length

Future metrics:

- lDDT-Ca
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
