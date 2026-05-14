# Protein Folding Benchmark

This project benchmarks locally runnable protein folding backends on selected protein targets. For each target, the pipeline runs configured prediction backends, stores their outputs in a standardized layout, and scores predicted structures against an experimental reference structure.

Benchmark targets are listed in `data/targets/targets.csv`. The first two targets are:

- Target ID: `1UAO_chignolin`
- PDB ID: `1UAO`
- Sequence: `GYDPETGTWG`
- Reference: `data/references/1UAO_model1_chainA.pdb`
- Target ID: `1UBQ_ubiquitin`
- PDB ID: `1UBQ`
- Sequence length: 76 residues
- Reference: `data/references/1UBQ_chainA.pdb`

## Benchmark Model Set

The core benchmark scope is exactly these 9 backends:

1. ESMFold (`esmfold`)
2. OmegaFold (`omegafold`)
3. Chai-1 (`chai1`)
4. Boltz-2 (`boltz2`)
5. OpenFold (`openfold`)
6. OpenFold3 (`openfold3`)
7. ColabFold (`colabfold`)
8. AlphaFold2 (`alphafold2`)
9. AlphaFold3 (`alphafold3`)

Model families:

- AF2-style / MSA-template family: AlphaFold2, OpenFold, ColabFold
- AF3-style / biomolecular family: AlphaFold3, OpenFold3, Boltz-2, Chai-1
- Single-sequence language-model / sequence-only baselines: ESMFold, OmegaFold

AlphaFold3 is included as a future optional restricted-access baseline and remains disabled by default. Its inference code is available, but model parameters and outputs are subject to the applicable Google/DeepMind terms, including non-commercial-use restrictions. Do not use AlphaFold3 for non-academic or commercial work unless rights, licensing, and any approved commercial route have been resolved.

OpenFold is included as an AF2-style backend and is enabled after a two-target smoke validation. The current benchmark runner uses single-sequence mode with AlphaFold-style parameters from `weights/colabfold/params`; full MSA/template OpenFold runs still require separate OpenFold-compatible databases supplied through `OPENFOLD_DATA_DIR` and related `OPENFOLD_*` environment variables. The benchmark does not download OpenFold sequence/template databases automatically.

Model-specific setup notes are in `docs/model_setup_notes.md`. The local OpenFold installation and smoke-run notes are in `models/openfold/README.md`; other backend status details are tracked in `docs/model_installation_status.md`.

Exact license and usage terms should be checked from each upstream repository before publication, redistribution, or benchmark release.

## Environment Policy

Use one driver/scoring environment plus one isolated conda environment per folding model. Do not install all folding models into a single conda environment.

| Environment | Purpose |
|---|---|
| `folding-benchmark` | Driver and scoring environment only |
| `openfold` | OpenFold backend |
| `openfold3` | OpenFold3 backend |
| `boltz` | Current working Boltz-2 backend environment; kept for compatibility |
| `chai1` | Chai-1 backend |
| `esmfold` | ESMFold backend |
| `colabfold` | ColabFold backend |
| `alphafold2` | AlphaFold2 backend |
| `alphafold3` | AlphaFold3 backend |
| `omegafold` | OmegaFold backend |

The benchmark backend ID is `boltz2`, but the current working conda environment may remain named `boltz` for compatibility.

## Runner Interface

Each runner must accept exactly:

```bash
bash runners/run_MODEL.sh input.fasta output_dir top_k
```

Each runner should write standardized outputs:

```text
output_dir/
├── rank_001.pdb
├── rank_002.pdb
├── rank_003.pdb
├── rank_004.pdb
├── rank_005.pdb
└── metadata.json
```

`top_k=5` is a request, not a guarantee. If a model only produces one structure, it should write only `rank_001.pdb` and record this in `metadata.json`. Runners must not duplicate deterministic outputs to satisfy `top_k`. `metadata.json` records `top_k_requested`, `top_k_generated`, `top_k_policy`, and, for multi-sample adapters, the source files used for each standardized rank.

## Chignolin Example

```bash
conda activate folding-benchmark

python scripts/01_predict_top5.py \
  --target-id 1UAO_chignolin \
  --fasta data/sequences/1UAO_chignolin.fasta \
  --top-k 5

python scripts/02_score_predictions.py \
  --target-id 1UAO_chignolin \
  --reference data/references/1UAO_model1_chainA.pdb \
  --ref-chain A \
  --pred-chain A \
  --match-mode sequential \
  --use-tmalign \
  --config configs/models.yaml \
  --only-enabled-models
```

Use `--config configs/models.yaml --only-enabled-models` for benchmark score generation. This prevents stale prediction folders, such as archived or deprecated backend IDs, from contaminating the canonical CSV.

## Scoring and Ranking

The benchmark now records both local and global structural metrics.

Primary ranking metric:

- `lddt_ca`: C-alpha-only local distance difference test. Higher is better.

Secondary ranking metric:

- `tmalign_tm_score_ref`: TM-score from TM-align/US-align, normalized by the reference length. Higher is better.

Additional diagnostic metrics:

- `tmalign_rmsd`: RMSD from TM-align/US-align. Lower is better.
- `ca_rmsd`: C-alpha RMSD using the configured matching mode. Lower is better.
- `n_aligned_ca`: number of aligned C-alpha atoms.

Current scoring also records TM-score normalized by prediction length, TM-align aligned length, TM-align sequence identity, C-alpha diagnostic counts, missing residue lists, and internal RMSD Z-score across all successful predictions for one target.

For the current benchmark, lDDT-C-alpha is treated as the major metric because it measures local distance agreement and is superposition-free. TM-score remains the main global-fold metric and is used as the secondary ranking criterion.

For very short targets such as Chignolin, lDDT-C-alpha and TM-score can be noisy. Chignolin is mainly a smoke-test target; ubiquitin is the first more meaningful folded-protein target.

Future scoring should include GDT_TS, runtime, GPU memory, and energy consumption or CO2 estimates.

## Model-Level Summary and Ranking

The raw score CSV has one row per predicted structure. The model summary CSV has one row per model/backend and selects the best prediction for each model.

```bash
python scripts/03_summarize_scores.py \
  --scores data/scores/1UAO_chignolin_scores.csv \
  --output data/scores/1UAO_chignolin_model_summary.csv \
  --markdown-output data/scores/1UAO_chignolin_model_summary.md
```

By default, ranking uses `lddt_ca` as the primary metric, `tmalign_tm_score_ref` as the secondary metric, `tmalign_rmsd` as the tertiary metric, and `ca_rmsd` as the quaternary metric. Higher `lddt_ca` and `tmalign_tm_score_ref` are better; lower `tmalign_rmsd` and `ca_rmsd` are better.

## Multi-Target Benchmark

Use `data/targets/targets.csv` as the source of truth for benchmark targets. Chignolin / `1UAO_chignolin` is a 10-residue smoke-test peptide; ubiquitin / `1UBQ_ubiquitin` is the first larger single-chain protein target.

Prepare FASTA files from the target table:

```bash
python scripts/prepare_targets.py \
  --targets data/targets/targets.csv \
  --overwrite
```

Run all targets through prediction, scoring, and per-target summaries:

```bash
python scripts/04_run_benchmark_targets.py \
  --targets data/targets/targets.csv \
  --config configs/models.yaml \
  --top-k 5 \
  --only-enabled-models \
  --use-tmalign \
  --match-mode sequential
```

Aggregate model summaries across targets:

```bash
python scripts/05_summarize_all_targets.py \
  --targets data/targets/targets.csv \
  --scores-dir data/scores \
  --out-csv data/scores/all_targets_model_summary.csv \
  --out-md data/scores/all_targets_model_summary.md
```

## Current Model Status

The active target set is exactly two targets: `1UAO_chignolin` and `1UBQ_ubiquitin`. The benchmark has currently been validated only with models that produced standardized `rank_*.pdb` files and were successfully read by the scoring script.

| Model | Enabled | Validated on 1UAO | Validated on 1UBQ | Structures per target | Notes |
|---|---|---|---|---:|---|
| ESMFold (`esmfold`) | yes | yes | yes | 1 | Deterministic/single-output sequence baseline. |
| OmegaFold (`omegafold`) | yes | yes | yes | 1 | Deterministic/single-output sequence baseline. |
| Chai-1 (`chai1`) | yes | yes | yes | 5 | Uses genuine generated samples only. |
| Boltz-2 (`boltz2`) | yes | yes | yes | 5 | Current Boltz backend; uses genuine generated samples only. |
| OpenFold (`openfold`) | yes | yes | yes | 1 | Single-sequence smoke mode using AlphaFold-style params from `weights/colabfold/params`; see `models/openfold/README.md`. |
| OpenFold3 (`openfold3`) | no | no | no | 0 | AF3-style open implementation; setup pending. |
| ColabFold (`colabfold`) | yes | yes | yes | 5 | Runs `colabfold_batch` with `--msa-mode single_sequence`; no local sequence databases are required for the current smoke workflow. |
| AlphaFold2 (`alphafold2`) | no | no | no | 0 | Canonical AF2 baseline; full databases not required for this project unless explicitly requested. |
| AlphaFold3 (`alphafold3`) | no | no | no | 0 | Future optional restricted/non-commercial baseline; weights and outputs require separate terms review. |

The old backend ID `boltz` is deprecated. `runners/run_boltz.sh` is retained only as a compatibility wrapper that delegates to `runners/run_boltz2.sh`.

The current canonical score outputs should contain 18 rows per target: ESMFold 1, OmegaFold 1, Chai-1 5, Boltz-2 5, ColabFold 5, and OpenFold 1. The cross-target aggregate summary is `data/scores/all_targets_model_summary.csv`.
