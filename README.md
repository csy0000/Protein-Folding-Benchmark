# Protein Folding Benchmark

This project benchmarks locally runnable open-source protein folding models on selected protein targets. For each target, the pipeline runs configured prediction backends, stores their outputs in a standardized layout, and scores predicted structures against an experimental reference structure.

The first benchmark target is Chignolin:

- Target ID: `1UAO_chignolin`
- PDB ID: `1UAO`
- Sequence: `GYDPETGTWG`
- Reference: `data/references/1UAO_model1_chainA.pdb`

## Models

Initial model list:

1. ESMFold
2. OmegaFold
3. Boltz
4. Chai-1
5. ColabFold
6. AlphaFold2
7. OpenFold
8. RoseTTAFold

Optional future models:

9. Uni-Fold
10. SPIRED-Fitness
11. RaptorX-Single

## Environment Policy

Use one driver/scoring environment plus one isolated conda environment per folding model. Do not install all folding models into a single conda environment.

| Environment | Purpose |
|---|---|
| `folding-benchmark` | Driver and scoring environment only |
| `esmfold` | ESMFold environment |
| `omegafold` | OmegaFold environment |
| `boltz` | Boltz environment |
| `chai1` | Chai-1 environment |
| `colabfold` | ColabFold environment |
| `alphafold2` | AlphaFold2 environment |
| `openfold` | OpenFold environment |
| `rosettafold` | RoseTTAFold environment |

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

If a model only produces one structure, it should write only `rank_001.pdb` and record this in `metadata.json`.

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
  --pred-chain A
```

## Scoring

Current scoring includes:

- C-alpha RMSD after structural superposition.
- C-alpha diagnostic counts for reference, prediction, and aligned residues.
- Semicolon-separated residue numbers missing from either structure.
- Internal RMSD Z-score across all successful predictions for one target.

The internal Z-score is:

```text
z_rmsd = (rmsd - mean_rmsd_for_target) / std_rmsd_for_target
```

Lower RMSD and lower Z-score are better.

Future scoring should include TM-score, GDT_TS, lDDT-Ca, runtime, GPU memory, and energy consumption or CO2 estimates.

## Current Model Status

The benchmark has currently been validated only with models that produced standardized `rank_001.pdb` files and were successfully read by the scoring script.

| Model | Environment | Runner | 1UAO test | Notes |
|---|---|---|---|---|
| OmegaFold | `omegafold` | working | passed | Produced `rank_001.pdb`; scoring succeeded |
| ESMFold | `esmfold` | working | passed | Produced `rank_001.pdb`; scoring succeeded after OpenFold dependency and checkpoint-key compatibility fixes |
| Boltz | `boltz` | placeholder/pending | not tested | Runner fails clearly until command mapping is configured |
| Chai-1 | `chai1` | placeholder/pending | not tested | Runner fails clearly until command mapping is configured |
| ColabFold | `colabfold` | placeholder/pending | not tested | No database download attempted |
| AlphaFold2 | `alphafold2` | placeholder/pending | not tested | Official parameters/databases not installed |
| OpenFold | `openfold` | placeholder/pending | not tested | Repository-specific setup still pending |
| RoseTTAFold | `rosettafold` | placeholder/pending | not tested | Repository-specific setup still pending |
