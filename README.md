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

1. OpenFold (`openfold`)
2. OpenFold3 (`openfold3`)
3. Boltz-2 (`boltz2`)
4. Chai-1 (`chai1`)
5. ESMFold (`esmfold`)
6. ColabFold (`colabfold`)
7. AlphaFold2 (`alphafold2`)
8. AlphaFold3 (`alphafold3`)
9. OmegaFold (`omegafold`)

Model families:

- AF2-style / MSA-template family: AlphaFold2, OpenFold, ColabFold
- AF3-style / biomolecular family: AlphaFold3, OpenFold3, Boltz-2, Chai-1
- Single-sequence language-model / sequence-only baselines: ESMFold, OmegaFold

AlphaFold3 is included as a restricted-access baseline. Its inference code is available, but model parameters must be obtained under the applicable Google/DeepMind terms. Do not treat AlphaFold3 as equivalent to permissively licensed open-source models such as Chai-1 or Boltz-2.

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

## Scoring

Current scoring includes:

- C-alpha RMSD after structural superposition using sequential residue order.
- C-alpha RMSD after structural superposition using residue sequence numbers.
- TM-align / US-align structural alignment when `--use-tmalign` is set.
- TM-score normalized by reference length.
- TM-score normalized by prediction length.
- TM-align RMSD and aligned length.
- C-alpha diagnostic counts for reference, prediction, and aligned residues.
- Semicolon-separated residue numbers missing from either structure.
- Internal RMSD Z-score across all successful predictions for one target.

Recommended primary metric:

- `tmalign_tm_score_ref`, higher is better.

Recommended secondary metrics:

- `tmalign_rmsd`, lower is better.
- `ca_rmsd`, lower is better.
- `n_aligned_ca`, higher is better.

For very short peptides such as Chignolin, TM-score and RMSD can be unstable. Chignolin is mainly a pipeline-debug target, not a robust benchmark target.

Future scoring should include GDT_TS, lDDT-Ca, runtime, GPU memory, and energy consumption or CO2 estimates.

## Model-Level Summary and Ranking

The raw score CSV has one row per predicted structure. The model summary CSV has one row per model/backend and selects the best prediction for each model.

```bash
python scripts/03_summarize_scores.py \
  --scores data/scores/1UAO_chignolin_scores.csv \
  --output data/scores/1UAO_chignolin_model_summary.csv \
  --markdown-output data/scores/1UAO_chignolin_model_summary.md
```

By default, ranking uses `tmalign_tm_score_ref` as the primary metric when available. Higher `tmalign_tm_score_ref` is better; lower `tmalign_rmsd` and `ca_rmsd` are better. For very short targets such as Chignolin, these metrics are mainly for pipeline validation, not final scientific benchmarking.

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

The benchmark has currently been validated only with models that produced standardized `rank_*.pdb` files and were successfully read by the scoring script.

| Model | Backend ID | Environment | Runner | 1UAO test | Top-k generated | Notes |
|---|---|---|---|---|---:|---|
| OpenFold | `openfold` | `openfold` | `runners/run_openfold.sh` | not validated | 0 | AF2-style PyTorch implementation; runner placeholder unless already functional |
| OpenFold3 | `openfold3` | `openfold3` | `runners/run_openfold3.sh` | not validated | 0 | AF3-style open implementation; setup pending |
| Boltz-2 | `boltz2` | `boltz` | `runners/run_boltz2.sh` | passed | 5 | Current Boltz backend; uses genuine generated samples only |
| Chai-1 | `chai1` | `chai1` | `runners/run_chai1.sh` | passed | 5 | Uses genuine generated samples only |
| ESMFold | `esmfold` | `esmfold` | `runners/run_esmfold.sh` | passed | 1 | Deterministic/single-output baseline |
| ColabFold | `colabfold` | `colabfold` | `runners/run_colabfold.sh` | not validated | 0 | AF2-style workflow; local DBs should not be downloaded unless explicitly requested |
| AlphaFold2 | `alphafold2` | `alphafold2` | `runners/run_alphafold2.sh` | not validated | 0 | Canonical AF2 baseline; full databases not required for this project unless explicitly requested |
| AlphaFold3 | `alphafold3` | `alphafold3` | `runners/run_alphafold3.sh` | not validated | 0 | Restricted-access baseline; weights require separate approval/terms |
| OmegaFold | `omegafold` | `omegafold` | `runners/run_omegafold.sh` | passed | 1 | Single-sequence baseline currently kept in benchmark |

The old backend ID `boltz` is deprecated. `runners/run_boltz.sh` is retained only as a compatibility wrapper that delegates to `runners/run_boltz2.sh`.

The current canonical Chignolin score output should contain 12 rows: ESMFold 1, OmegaFold 1, Chai-1 5, and Boltz-2 5.
