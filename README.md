# Protein-Folding-Benchmark

Local benchmark harness for protein structure prediction. Runs 8 predictors on 45 CASP15/CASP16 monomer targets, scores each prediction against experimental references, and records runtime, MSA provenance, and CO₂e via CodeCarbon.

## Benchmark Scope

- **Targets:** 45 unique CASP15/CASP16 monomer domains (<1000 residues): 33 from CASP15 (2022) and 12 from CASP16 (2024). The working target set is defined by `results/2026-06-06-combine-8models/metadata/scoring_targets.csv`.
- **Models:** 8 — ESMFold, OmegaFold, Boltz-2, Chai-1, ColabFold, OpenFold, Protenix, AlphaFold2 (af2).
- **Metrics:** lDDT-Cα (primary), TM-score (USalign), GDT_TS (0–1 and %), Cα-RMSD.
- **Carbon accounting:** CodeCarbon offline world-average (475 g CO₂e/kWh, `country=WORLD`). MSA build and inference are tracked as separate CodeCarbon stages where applicable.
- **Deliverable:** `results/2026-06-06-combine-8models/` — self-contained folder with 360 predicted structures (45 targets × 8 models), reference structures, scores, and metadata.

## Results

**Current results: 3 replicates (n=3, 2026-08-03).** Every value is **mean ± sample std across the three replicates**, where each replicate value is itself a mean over the 45 targets. This is a different quantity from the across-target std in the score CSVs.

| Model | Mean lDDT-Cα | Mean TM-score | Mean GDT_TS (%) | Mean Cα-RMSD (Å) | MSA |
|---|---:|---:|---:|---:|---|
| colabfold | 0.8760 ± 0.0002 | 0.7698 ± 0.0007 | 70.87 ± 0.03 | 11.964 ± 0.023 | ColabFold/MMseqs2 |
| openfold | 0.8753 ± 0.0018 | 0.7698 ± 0.0033 | 71.22 ± 0.33 | 11.695 ± 0.033 | ColabFold/MMseqs2 (shared) |
| protenix | 0.8709 ± 0.0008 | 0.7444 ± 0.0006 | 69.45 ± 0.09 | 15.361 ± 0.001 | ColabFold/MMseqs2 (shared) |
| af2 | 0.8673 ± 0.0034 | 0.7626 ± 0.0026 | 70.15 ± 0.12 | 11.138 ± 0.244 | Official AF2 DBs |
| boltz2 | 0.8627 ± 0.0018 | 0.7321 ± 0.0026 | 68.39 ± 0.13 | 17.579 ± 0.151 | ColabFold/MMseqs2 (shared) |
| esmfold | 0.8101 ± 0.0000 | 0.7042 ± 0.0000 | 64.08 ± 0.00 | 15.397 ± 0.000 | None (language model) |
| chai1 | 0.7977 ± 0.0009 | 0.6928 ± 0.0025 | 62.12 ± 0.13 | 17.479 ± 0.679 | None (embedding) |
| omegafold | 0.7697 ± 0.0000 | 0.6690 ± 0.0000 | 59.19 ± 0.00 | 17.345 ± 0.000 | None (language model) |

Cost with the same error bars is in the [Cost (n=3)](#cost-n3) table below. Full per-target and per-model scores: `results/replicate_summary/` and each replicate's `scores/all_targets_model_summary.csv`.

### Replicate design and what the error bars mean (n=3, 2026-08-03)

The full 8-model benchmark was run three times end to end on GPU, to put error bars on cost (runtime / energy / CO₂). It turned out to be necessary for accuracy as well — see below. All **1080/1080 predictions succeeded** (45 targets × 8 models × 3 reps).

- **Replicates:** `results/2026-06-09-combine-8models-gpu` (rep1), `results/20260802_082154_combine-8models-gpu_rep2`, `results/20260803_005751_combine-8models-gpu_rep3`.
- **Driver:** `scripts/run_two_more_reps.sh` (serial, pinned to one GPU). **Aggregator:** `scripts/06_summarize_across_reps.py` → `results/replicate_summary/`.
- GDT_TS uses the `external_tmscore_matched` method (2026-07-30 re-scoring); it is **not** comparable with `internal_iterative_ca` values published earlier. lDDT-Cα, TM-score and Cα-RMSD are unaffected by that change.

**Only 2 of 8 models are deterministic.** esmfold and omegafold reproduce exactly (0.000000 spread on all 45 targets). At the per-target level, 152 of the 315 non-af2 (target, model) pairs exceed a 1e-3 lDDT-Cα tolerance — max spread boltz2 0.105, openfold 0.089, chai1 0.082, protenix 0.062, colabfold 0.0055. **chai1 is MSA-free**, so its spread cannot come from MSA rebuild; that isolates genuine sampling nondeterminism in the diffusion-based models. Per-target detail: `results/replicate_summary/reps_accuracy_consistency.csv`.

Per-target variation largely averages out at the benchmark level (all across-rep stds ≤ 0.0034 lDDT-Cα), so the overall ranking is stable — **except at the top**: colabfold leads openfold by 0.0007 lDDT-Cα, smaller than openfold's own across-rep std of 0.0018, and the order flips by metric (openfold leads on GDT_TS, they tie on TM-score to 4 d.p.). **colabfold and openfold are not separable in this benchmark.**

#### Cost (n=3)

Attributed per-model cost — correct for comparing models to each other, but **not additive across models**, because the shared ColabFold/MMseqs2 MSA is built once per replicate and re-charged to colabfold, openfold, protenix and boltz2.

| Model | Total runtime (h) | Inference runtime (h) | CO₂ (g) |
|---|---:|---:|---:|
| colabfold | 8.36 ± 0.18 | 1.81 ± 0.04 | 393 ± 112 |
| protenix | 7.72 ± 0.19 | 1.17 ± 0.03 | 378 ± 57 |
| openfold | 7.43 ± 0.17 | 0.88 ± 0.06 | 401 ± 67 |
| boltz2 | 7.38 ± 0.17 | 0.82 ± 0.01 | 362 ± 58 |
| af2 | 19.83 (n=1) + 1.75 ± 0.04 † | 1.75 ± 0.04 | 1873 (n=1) + 218 † |
| chai1 | 1.67 ± 0.30 | 1.67 ± 0.30 | 208 ± 20 |
| omegafold | 1.42 ± 0.10 | 1.42 ± 0.10 | 210 ± 26 |
| esmfold | 0.78 ± 0.10 | 0.78 ± 0.10 | 79 ± 7 |

Whole-benchmark cost with the shared MSA counted once (`benchmark_incremental_*`): **16.5 ± 0.27 h** per replicate. rep1's 37.4 h is not comparable, because rep1 built AF2's MSA and rep2/rep3 reused it.

Three caveats on the cost figures:

- † **AF2's MSA is measured once.** rep2/rep3 reuse rep1's `features.pkl` (`AF2_REUSE_FEATURES_ROOT`), which saves ~20 h per replicate. AF2's MSA build (19.83 h, 1873 g CO₂ — the single largest cost item in the benchmark, exceeding a whole replicate's incremental cost) therefore stays **n=1**, and the ± covers only AF2 inference. The MSA stage is deterministic given fixed databases, so this affects the cost error bar, not accuracy.
- **Energy/CO₂ error bars are inflated by rep1.** rep2 and rep3 agree to within ~1% on energy, while rep1 is a systematic outlier in both directions by model group (~30–58% higher for the shared-MSA consumers, 14–20% lower for the MSA-free ones) even where runtime is nearly identical. This looks like a measurement/attribution difference in rep1, not run-to-run variance. Runtime is unaffected; prefer rep2+rep3 for energy until rep1's provenance is checked.
- Runtime reproducibility is ~2% CV for the MSA-dominated models. The higher CV for the MSA-free models (chai1 18%, esmfold 13%) reflects their small totals, not instability.

#### Energy by device (n=3)

CPU / GPU / RAM energy from the per-(target, model, stage) CodeCarbon CSVs, summed over all stages. **This is a device split of energy, not of wall time.** The prediction manifest records no device at all, and a stage occupies wall-clock while both CPU and GPU are partly busy, so there is no meaningful per-device wall time to report. Source: `results/replicate_summary/reps_device_energy_{summary,per_rep,by_stage}.csv`.

| Model | CPU (kWh) | GPU (kWh) | RAM (kWh) | GPU share (%) | Measured wall time (h) |
|---|---:|---:|---:|---:|---:|
| af2 † | 0.3731 ± 0.5204 | 0.6755 ± 0.7802 | 0.8115 ± 1.1515 | 44.9 ± 10.0 | 8.78 ± 12.24 † |
| colabfold | 0.0824 ± 0.0018 | 0.4571 ± 0.2356 | 0.2871 ± 0.0063 | 53.1 ± 11.4 | 8.31 ± 0.18 |
| omegafold | 0.0422 ± 0.0256 | 0.2981 ± 0.0133 | 0.1016 ± 0.0421 | 68.5 ± 12.3 | 1.40 ± 0.10 |
| chai1 | 0.0474 ± 0.0266 | 0.2745 ± 0.0233 | 0.1158 ± 0.0398 | 63.5 ± 12.3 | 1.65 ± 0.30 |
| openfold ‡ | 0.0262 ± 0.0156 | 0.1800 ± 0.0082 | 0.0628 ± 0.0260 | 68.0 ± 12.2 | 0.86 ± 0.06 |
| boltz2 ‡ | 0.0250 ± 0.0152 | 0.1035 ± 0.0149 | 0.0594 ± 0.0265 | 57.3 ± 11.7 | 0.80 ± 0.01 |
| protenix ‡ | 0.0362 ± 0.0232 | 0.0986 ± 0.0106 | 0.0862 ± 0.0405 | 47.7 ± 17.8 | 1.15 ± 0.03 |
| esmfold | 0.0229 ± 0.0124 | 0.0893 ± 0.0182 | 0.0547 ± 0.0204 | 54.4 ± 16.5 | 0.76 ± 0.10 |

Three stages are measured: `inference` (all 8 models), `msa_build` (colabfold's shared MMseqs2 search), and `msa_features` (AF2's jackhmmer/HHblits stage, present in rep1 only — hence af2's large ± and its 0.97 kWh of rep1 CPU energy).

**Wall time here is CodeCarbon's own stage timer, independent of the manifest runtime columns** — the two agree to within 1–3% for every model CodeCarbon measures end to end (colabfold 8.31 vs 8.36 h; omegafold 1.40 vs 1.42; chai1 1.65 vs 1.67; esmfold 0.76 vs 0.78), and colabfold's `msa_build` stage matches the manifest MSA cost to ~0.5% (6.48/6.38/6.71 vs 6.51/6.41/6.74 h). ‡ openfold, boltz2 and protenix look 6–9× smaller here only because CodeCarbon measures their *inference* alone: they consume the shared MSA rather than building it, so their manifest totals include a re-charge that has no CodeCarbon stage of their own. That is an independent confirmation of the non-additivity caveat above rather than a discrepancy.

**This identifies the rep1 energy anomaly as a CodeCarbon attribution difference, not machine variance.** rep1 assigns a mean **69.3%** of measured energy to the GPU; rep2 and rep3 assign **51.1%**, and agree with each other to within ~1%. rep1's CPU energy is 3–4× lower for most models (boltz2 0.0075 vs 0.0337/0.0339 kWh; esmfold 0.0087 vs 0.0300/0.0302; openfold 0.0081 vs 0.0350/0.0353) while total wall-clock is nearly identical. colabfold is the one model whose CPU energy is stable across all three (0.0826 / 0.0805 / 0.0841). So rep1's CPU tracking under-measured, inflating the GPU share and the totals for the models that reuse the shared MSA. **Prefer rep2+rep3 for any energy or CO₂ figure**; runtime and accuracy are unaffected.

### Superseded: single-run results (2026-06-06)

Retained for provenance. This is a **different run**, not a replicate of the set above: `results/2026-06-06-combine-8models`, single run, chai1/boltz2/esmfold executed on CPU, and GDT_TS from the older `internal_iterative_ca` method. Its boltz2 value in particular (0.765) is not reproduced by any of the three GPU replicates (0.8627 ± 0.0018) and should not be quoted alongside them.

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

Scores: `results/2026-06-06-combine-8models/scores/all_targets_model_summary.csv`.

### MSA cross-mode variants (2026-07-09)

A follow-up run flips the MSA mode of four models on the **same 45 targets**, to isolate the effect of the MSA alone. Each variant uses a distinct model label; the eight-model results above are unchanged. Baseline (default-mode) values below are the GPU 8-model set (`results/2026-06-09-combine-8models-gpu`).

- **Source run:** `results/20260709_casp15_casp16_unique_lt1000_msa-variants` (45/45 predicted on GPU and scored, `--match-mode sequence`).
- **Per-model JSON + scores:** `results/20260709_.../{chai1_msa,boltz2_nomsa,colabfold_nomsa,openfold_nomsa}.json` and `results/20260709_.../scores/all_targets_model_summary.csv`.
- For `chai1_msa`, the shared ColabFold/MMseqs2 A3M is converted to Chai-1's `.aligned.pqt` format; the three `*_nomsa` variants take single-sequence input.
- **GDT_TS** is computed with the TMscore binary on the sequence-matched Cα atoms; **CO₂/job** and **Time/job** are CodeCarbon world-average emissions and wall-clock per target. Sequence matching used a mean of **284 aligned Cα** per target (range 70–632), identical across variants.

| Variant | Mode vs default | Mean lDDT-Cα | Mean TM-score | Mean GDT_TS (%) | Mean Cα-RMSD (Å) | CO₂/job (g) | Time/job (s) | Base (lDDT-Cα) |
|---|---|---:|---:|---:|---:|---:|---:|---|
| chai1_msa | +ColabFold MSA (default: none) | 0.562 | 0.533 | 43.89 | 24.996 | 3.29 | 141 | chai1 0.799 |
| boltz2_nomsa | −MSA, single-sequence (default: MSA) | 0.421 | 0.387 | 27.12 | 29.835 | 1.31 | 67 | boltz2 0.864 |
| colabfold_nomsa | −MSA, single-sequence (default: MSA) | 0.307 | 0.290 | 16.89 | 32.431 | 2.07 | 128 | colabfold 0.876 |
| openfold_nomsa | −MSA, single-sequence (default: MSA) | 0.307 | 0.288 | 16.92 | 32.839 | 1.92 | 70 | openfold 0.875 |

`chai1_msa` reuses the shared ColabFold MSA and is not re-charged its MSA-build cost, so its carbon is inference-only; the `*_nomsa` variants build no MSA. Removing the MSA collapses the three MSA-dependent models as expected: ColabFold and OpenFold run AlphaFold2 Evoformer weights and lose almost all accuracy without an alignment (lDDT-Cα ≈ 0.31), and Boltz-2 drops from 0.864 to 0.421. Feeding the ColabFold MSA to Chai-1 is the notable case — it lowers the mean (0.562 vs 0.799 single-sequence) and is strongly bimodal: it improves 10/45 targets (e.g. T1145 +0.32, T1159 +0.30) but degrades 22/45, several to near-unfolded structures (T1185s2 −0.72, T1272s4 −0.67), concentrated on the multi-domain CASP subdomain targets (T1137sX / T1272sX / T1114sX / T1185sX). This is **genuine Chai-1 behavior, not an artifact of our conversion**: re-folding all 45 targets with Chai-1's own online MSA server (properly source-tagged and species-paired) gives mean 0.563 vs our ColabFold-A3M 0.562 (mean |Δ| = 0.005, max 0.025 lDDT-Cα per target), collapsing on the same targets. It is consistent with reported "MSA can hurt AF3-style models" behavior, acknowledged by Chai-1's maintainers ([chai-lab #277](https://github.com/chaidiscovery/chai-lab/discussions/277)) and reported for Boltz ([#627](https://github.com/jwohlwend/boltz/issues/627)) — though those cases concern irrelevant MSAs on designed proteins, whereas here it is natural targets with deep, relevant alignments. The online-MSA folds are a diagnostic only (remote MSA server, so not carbon-valid) and are not part of the benchmark.

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
