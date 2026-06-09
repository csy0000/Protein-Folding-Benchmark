# Protein-Folding-Benchmark

Local benchmark harness for protein structure prediction. Runs 8 predictors on 45 CASP15/CASP16 monomer targets, scores each prediction against experimental references, and records runtime, MSA provenance, and CO₂e via CodeCarbon.

## Benchmark Scope

- **Targets:** 45 unique CASP15/CASP16 monomer domains (<1000 residues): 33 from CASP15 (2022) and 12 from CASP16 (2024). The working target set is defined by `results/2026-06-06-combine-8models/metadata/scoring_targets.csv`.
- **Models:** 8 — ESMFold, OmegaFold, Boltz-2, Chai-1, ColabFold, OpenFold, Protenix, AlphaFold2 (af2).
- **Metrics:** lDDT-Cα (primary), TM-score (USalign), GDT_TS (0–1 and %), Cα-RMSD.
- **Carbon accounting:** CodeCarbon offline world-average (475 g CO₂e/kWh, `country=WORLD`). MSA build and inference are tracked as separate CodeCarbon stages where applicable.
- **Deliverable:** `results/2026-06-06-combine-8models/` — self-contained folder with 360 predicted structures (45 targets × 8 models), reference structures, scores, and metadata.

## Results

All 45 targets predicted successfully for all 8 models. Results ranked by mean lDDT-Cα (N=45).

| Model | Mean lDDT-Cα | Mean TM-score | Mean GDT_TS (%) | Mean Cα-RMSD (Å) | MSA |
|---|---:|---:|---:|---:|---|
| colabfold | 0.876 | 0.770 | 60.96 | 11.972 | ColabFold/MMseqs2 |
| openfold | 0.875 | 0.771 | 60.84 | 11.734 | ColabFold/MMseqs2 (shared) |
| protenix | 0.871 | 0.744 | 57.50 | 15.361 | ColabFold/MMseqs2 (shared) |
| af2 | 0.868 | 0.761 | 59.15 | 11.379 | Official AF2 DBs |
| esmfold | 0.811 | 0.704 | 52.36 | 15.395 | None (language model) |
| chai1 | 0.798 | 0.695 | 48.79 | 17.648 | None (embedding) |
| omegafold | 0.770 | 0.669 | 47.18 | 17.345 | None (language model) |
| boltz2 | 0.765 | 0.714 | 51.82 | 17.605 | None (explicit no-MSA) |

Full per-target and per-model scores: `results/2026-06-06-combine-8models/scores/all_targets_model_summary.csv`.

## Repository Layout

```
Protein-Folding-Benchmark/
├── scripts/                          # Pipeline scripts (see Reproduction below)
├── runners/                          # Per-model bash wrappers (run_<model>.sh)
├── envs/                             # Conda environment YAML files
├── configs/models.yaml               # Model enable/disable and MSA config
├── data/
│   ├── targets/                      # Target list CSVs (smoke sets, prepared lists)
│   ├── references/                   # mmCIF source files for reference building
│   ├── sequences/                    # Target FASTA inputs
│   └── cache/                        # Cached RCSB mmCIF + CASP manifest downloads
├── results/
│   ├── 2026-06-06-combine-8models/   # Canonical deliverable (see below)
│   ├── 20260601_..._msa-free/        # Source run: chai1, esmfold, omegafold
│   ├── 20260603_..._colabfold/       # Source run: colabfold, boltz2, openfold, protenix
│   └── 20260604_...-af2/             # Source run: af2
├── weights/                          # Model weights (local, ~30 GB, not committed)
├── databases/ -> /data/chen/protein_folding_databases   # Symlink to shared DB storage
├── docs/                             # Scoring metrics, installation notes, handoff docs
└── model-installation/               # Per-model setup notes
```

### Deliverable structure (`results/2026-06-06-combine-8models/`)

```
2026-06-06-combine-8models/
├── predictions/
│   └── <target>/
│       └── <model>/
│           ├── rank_001.pdb           # Top-ranked prediction
│           ├── metadata.json          # Runner metadata
│           ├── carbon/                # CodeCarbon emissions CSV(s) per stage
│           └── af2_stage_metadata.csv # (af2 only) split MSA-feature + inference metadata
├── references/
│   └── <target>.pdb                   # Experimental reference (chain A, residue-range clipped)
├── scores/
│   ├── all_targets_model_summary.csv  # Headline: one row per model, mean scores across 45 targets
│   ├── <target>_scores.csv            # Per-target, per-model individual scores
│   └── <target>_model_summary.{csv,md}
├── metadata/
│   ├── prediction_manifest.csv        # One row per (target, model): paths, timing, carbon, MSA provenance
│   └── scoring_targets.csv            # 45 targets: pdb_id, chain_id, sequence, reference_pdb
├── sequences/
│   └── <target>.fasta
├── <model>.json × 8                   # Per-model JSON: aggregate_summary + per_target array
└── manifest_used.csv
```

## Models

| Method | Publication | DOI | GitHub | MSA in this benchmark |
|---|---|---|---|---|
| ESMFold | Lin et al., 2023, *Science* | [`10.1126/science.ade2574`](https://doi.org/10.1126/science.ade2574) | [`facebookresearch/esm`](https://github.com/facebookresearch/esm) | None — single-sequence language model |
| OmegaFold | Wu et al., 2022, bioRxiv | [`10.1101/2022.07.21.500999`](https://doi.org/10.1101/2022.07.21.500999) | [`HeliXonProtein/OmegaFold`](https://github.com/HeliXonProtein/OmegaFold) | None — single-sequence model |
| Boltz-2 | Passaro et al., 2025, bioRxiv | [`10.1101/2025.06.14.659707`](https://doi.org/10.1101/2025.06.14.659707) | [`jwohlwend/boltz`](https://github.com/jwohlwend/boltz) | None — explicit no-MSA mode |
| Chai-1 | Boitreaud et al., 2024, bioRxiv | [`10.1101/2024.10.10.615955`](https://doi.org/10.1101/2024.10.10.615955) | [`chaidiscovery/chai-lab`](https://github.com/chaidiscovery/chai-lab) | None — native embedding without MSA |
| ColabFold | Mirdita et al., 2022, *Nat. Methods* | [`10.1038/s41592-022-01488-1`](https://doi.org/10.1038/s41592-022-01488-1) | [`sokrypton/ColabFold`](https://github.com/sokrypton/ColabFold) | Yes — local ColabFold/MMseqs2 (`mmseqs2_uniref_env`) |
| OpenFold | Ahdritz et al., 2024, *Nat. Methods* | [`10.1038/s41592-024-02272-z`](https://doi.org/10.1038/s41592-024-02272-z) | [`aqlaboratory/openfold`](https://github.com/aqlaboratory/openfold) | Yes — shared ColabFold/MMseqs2 A3M from colabfold run. **Note:** this benchmark uses AlphaFold2 `params_model_1.npz` weights through the OpenFold inference engine (not OpenFold's own retrained weights). |
| Protenix | Zhang et al., 2026, bioRxiv | [`10.64898/2026.02.05.703733`](https://doi.org/10.64898/2026.02.05.703733) | [`bytedance/Protenix`](https://github.com/bytedance/Protenix) | Yes — shared ColabFold/MMseqs2 A3M converted to paired/unpaired Protenix format |
| AlphaFold2 (af2) | Jumper et al., 2021, *Nature* | [`10.1038/s41586-021-03819-2`](https://doi.org/10.1038/s41586-021-03819-2) | [`google-deepmind/alphafold`](https://github.com/google-deepmind/alphafold) | Yes — official AlphaFold2 full database search + JAX inference, split into separate MSA-feature and inference CodeCarbon stages |

## Environments

One driver/scoring environment plus one isolated conda environment per model. Do not co-install folding models.

| Environment | Purpose |
|---|---|
| `folding-benchmark` | Pipeline driver, scoring, and export scripts |
| `esmfold` | ESMFold backend |
| `omegafold` | OmegaFold backend |
| `boltz` | Boltz-2 backend (backend ID `boltz2`) |
| `chai1` | Chai-1 backend |
| `colabfold` | ColabFold backend |
| `openfold` | OpenFold backend; also provides hhblits/jackhmmer/hhsearch for af2 MSA search |
| `protenix` | Protenix backend |
| `af2` | Official AlphaFold2 backend |

Environment YAML files are in `envs/`. See `model-installation/` for per-model setup notes.

## Reproduction

### Prerequisites

- All 8 conda environments installed (see `envs/`).
- Model weights in `weights/` (af2, colabfold, openfold share `colabfold/params/params_model_1.npz`; others have their own).
- Databases in `databases/` (symlink or directory): ColabFold/MMseqs2 databases at `databases/colabfold/`; AlphaFold2 databases at `databases/alphafold/`.
- `USalign` and `TMscore` executables on PATH (for TM-score and GDT_TS scoring).

### Step 1 — Build target manifest

Scrapes CASP15/CASP16 target lists, resolves each target's experimental PDB chain and residue range, and classifies `should_use` ∈ {`Yes`, `Check`, `No`}.

```bash
python scripts/build_casp_target_manifest_prefiltered.py \
  --only-round both \
  --out-dir data \
  --cache-dir data/cache/casp_target_manifest
```

Outputs: `data/casp15_casp16_target_manifest_prefiltered.csv`. The 45-target subset used for colabfold and af2 runs is `data/casp15_casp16_target_manifest_prefiltered_use.csv` (select `should_use=Yes` rows, <1000 residues).

### Step 2 — Run predictions: MSA-free models (chai1, esmfold, omegafold)

```bash
bash scripts/run_casp15_casp16_unique_lt1000_all_default_benchmark-msa-free.sh
```

Produces: `results/<timestamp>_casp15_casp16_unique_lt1000_all_default_msa-free/`. Each target/model subdirectory contains `rank_001.pdb`, `metadata.json`, and `carbon/` emissions CSVs.

### Step 3 — Run predictions: ColabFold-MSA models (colabfold, boltz2, openfold, protenix)

```bash
bash scripts/run_casp15_casp16_unique_lt1000_all_default_benchmark-colabfold.sh
```

Produces: `results/<timestamp>_casp15_casp16_unique_lt1000_all_default_colabfold/`. **Important:** `colabfold` must complete first for each target because `boltz2`, `openfold`, and `protenix` reuse its `.a3m` as a shared MSA. The model order in the script ensures this.

### Step 4 — Run predictions: official AlphaFold2 (af2)

```bash
bash scripts/run_casp15_casp16_unique_lt1000_all_default_benchmark-af2.sh
```

Produces: `results/<timestamp>_casp15_casp16_unique_lt1000_all_default-af2/`. AF2 runs a split pipeline — MSA/feature generation and JAX inference are separate CodeCarbon stages, recorded in `af2_stage_metadata.csv`.

For long runs, use the watchdog to auto-resume if the process dies:

```bash
bash scripts/watch_af2_benchmark_resume.sh \
  --results-dir results/<timestamp>_...-af2 \
  --interval-sec 1800
```

### Step 5 — Combine into one deliverable folder

Intersects the three source runs to the 45 targets common to all, copies essential outputs (`rank_*.pdb`, `metadata.json`, `carbon/`), and merges manifest rows.

```bash
python scripts/combine_8model_predictions.py \
  --dest results/2026-06-06-combine-8models
```

Source-run → model mapping:

| Source run | Models |
|---|---|
| `..._msa-free/` | chai1, esmfold, omegafold |
| `..._colabfold/` | boltz2, colabfold, openfold, protenix |
| `...-af2/` | af2 |

To update a single model after re-running it:

```bash
python scripts/combine_8model_predictions.py \
  --dest results/2026-06-06-combine-8models \
  --only-targets T1104,T1106s1 --only-models af2
```

### Step 6 — Build experimental reference structures

Extracts per-target reference PDBs from cached mmCIF files using the exact `chain_id`, `residue_start`, and `residue_end` from the prediction manifest (not a generic chain A assumption). Renames the extracted chain to `A`.

```bash
python scripts/build_combined_references.py \
  --run-dir results/2026-06-06-combine-8models \
  --cache-dir data/cache/rcsb
```

Outputs: `results/2026-06-06-combine-8models/references/<target>.pdb` (45 files).

### Step 7 — Score predictions

Runs lDDT-Cα, TM-score (USalign), GDT_TS, and Cα-RMSD for all 45 × 8 = 360 (target, model) pairs. Uses Needleman-Wunsch Cα alignment (`--match-mode sequence`) as the residue correspondence method.

```bash
conda run -n folding-benchmark python scripts/score_combined_8models.py \
  --run-dir results/2026-06-06-combine-8models \
  --match-mode sequence
```

Outputs: `scores/<target>_scores.csv` (per-model structural scores + merged timing/carbon columns), `scores/all_targets_model_summary.csv`, and one `<model>.json` per model.

### Step 8 — Export to carbon4science (optional)

Converts the combined run into the carbon4science.github.io data format:

```bash
conda run -n folding-benchmark python scripts/export_combined_to_carbon4science.py \
  --run-dir results/2026-06-06-combine-8models \
  --out-dir ../carbon4science.github.io/results
```

## Scoring Methodology

| Metric | Tool | Description |
|---|---|---|
| lDDT-Cα | Internal (lddt library) | Primary ranking metric. Local distance difference test on Cα atoms. |
| TM-score | USalign | Normalized by reference length. Reports TM-score vs. reference and vs. prediction. |
| GDT_TS | TMscore executable | Reported on both 0–1 (`gdt_ts`) and 0–100 (`gdt_ts_percent`) scales. |
| Cα-RMSD | Internal | Diagnostic geometry metric. |

All metrics use **match-mode `sequence`** (Needleman-Wunsch Cα alignment) so that the residue correspondence respects sequence identity rather than structure alone. See `docs/scoring_metrics.md` for full column definitions and caveats.

## Hardware

- **CPU:** Intel Xeon Gold 6240R, 1 socket, 24 cores / 48 threads
- **RAM:** 251 GiB
- **GPUs:** 3 × NVIDIA RTX A5000, 24,564 MiB each
- **NVIDIA driver:** 580.159.03
- **CUDA (driver-reported):** 13.0
- **OS/kernel:** Ubuntu Linux, kernel `6.8.0-117-generic`, x86_64

Carbon accounting uses **CodeCarbon** in offline mode with `carbon_intensity_mode=world_average` (475 g CO₂e/kWh, `carbon_country_iso_code=WORLD`) unless otherwise stated.

## Caveats

1. **OpenFold uses AlphaFold2 weights.** Our OpenFold backend loads `alphafold2/params/params_model_1.npz` (MD5 `e2c73bf2…`) through the OpenFold inference engine — the same weights as the `af2` backend. It does *not* use OpenFold's own retrained weights. This is why OpenFold's accuracy and parameter count (93.2 M) track AlphaFold2 closely, and why both share a training-data PDB cutoff of 2018-04-30.

2. **Boltz-2 CASP15 leakage.** Boltz-2's training-data PDB cutoff is 2023-06-01, which postdates CASP15. The 33 CASP15 targets (released 2022–2023) may overlap Boltz-2's training data. Interpret Boltz-2's CASP15 target numbers with that caveat. The 12 CASP16 targets (released 2024) are unaffected.

3. **Training-data cutoffs.** All other models have cutoffs that predate CASP15: af2/colabfold/openfold = 2018-04-30; ESMFold = 2020-05-01; Chai-1 = 2021-01-12; Protenix = 2021-09-30. OmegaFold's cutoff is not documented by the authors.

4. **45-target set.** The 45 scored targets are the intersection of targets successfully predicted across all three source runs. They are defined by `results/2026-06-06-combine-8models/metadata/scoring_targets.csv`, not by a standalone file in `data/targets/`.

5. **GDT_TS caveat.** GDT_TS requires the external `TMscore` binary. Without it the scoring script falls back to an internal Cα-only approximation, which may differ slightly.

6. **Timing and carbon.** For MSA-using models (colabfold, openfold, protenix, af2), total_runtime_sec and total_carbon_emissions_g include both MSA build and inference stages. For the MSA-free models (esmfold, omegafold, boltz2, chai1), only inference is measured.

## Documentation

- `docs/scoring_metrics.md` — full definitions of all score and metadata columns
- `docs/multitarget_benchmark.md` — protocol notes and run history
- `docs/model_installation_status.md` — per-model installation status
- `model-installation/` — per-model setup guides
- `results/2026-06-06-combine-8models/scores/all_targets_model_summary.md` — rendered results table
- Carbon4Science publication: [`carbon4science.github.io/results/`](https://carbon4science.github.io/results/) — per-model JSON + benchmark CSVs exported from this run
