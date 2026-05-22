# Protein Folding Benchmark

This repository is a local benchmark harness for protein structure prediction backends. It runs each model through a standardized shell runner, writes standardized prediction files, scores predictions against prepared experimental references, and records runtime, MSA provenance, and CodeCarbon CO2e metadata.

The current compact benchmark is the first-five CASP target smoke set in `data/targets/targets_first5.csv`. The canonical default-mode model IDs are kept stable (`esmfold`, `omegafold`, `boltz2`, `chai1`, `colabfold`, `openfold`), while explicit side-study IDs such as `colabfold_single`, `colabfold_msa`, `openfold_single`, and `openfold_msa` are reserved for ablations. Experimental shared-MSA runs for `protenix` and `openfold3` are reported separately and remain disabled in `configs/models.yaml`.

## Hardware

The current benchmark host is:

- CPU: Intel Xeon Gold 6240R, 1 socket, 24 cores / 48 threads
- RAM: 251 GiB
- GPUs: 3 x NVIDIA RTX A5000, 24,564 MiB each
- NVIDIA driver: 580.159.03
- CUDA reported by driver: 13.0
- OS/kernel: Ubuntu Linux, kernel `6.8.0-117-generic`, x86_64

Carbon accounting uses CodeCarbon. Unless otherwise stated, benchmark runs use the repository's offline world-average default intensity (`475 g CO2e/kWh`) and record `carbon_country_iso_code=WORLD`, `carbon_intensity_mode=world_average`.

## Models and References

| Method | Paper / report | DOI | GitHub repository | Default MSA usage in this benchmark | Notes |
|---|---|---|---|---|---|
| ESMFold | Lin et al., "Evolutionary-scale prediction of atomic-level protein structure with a language model" | [`10.1126/science.ade2574`](https://doi.org/10.1126/science.ade2574) | [`facebookresearch/esm`](https://github.com/facebookresearch/esm) | No MSA; native single-sequence language model | Enabled canonical backend. |
| OmegaFold | Wu et al., "High-resolution de novo structure prediction from primary sequence" | [`10.1101/2022.07.21.500999`](https://doi.org/10.1101/2022.07.21.500999) | [`HeliXonProtein/OmegaFold`](https://github.com/HeliXonProtein/OmegaFold) | No MSA; native single-sequence model | Enabled canonical backend. |
| Boltz-2 | Passaro et al., "Boltz-2: Towards Accurate and Efficient Binding Affinity Prediction" | [`10.1101/2025.06.14.659707`](https://doi.org/10.1101/2025.06.14.659707) | [`jwohlwend/boltz`](https://github.com/jwohlwend/boltz) | No MSA in this local runner; explicit no-MSA mode | Enabled canonical backend as `boltz2`. |
| Chai-1 | Boitreaud et al., "Chai-1: Decoding the molecular interactions of life" | [`10.1101/2024.10.10.615955`](https://doi.org/10.1101/2024.10.10.615955) | [`chaidiscovery/chai-lab`](https://github.com/chaidiscovery/chai-lab) | No MSA by default; Chai-1 uses embeddings without MSAs/templates unless external MSAs are supplied | Metadata now records `native_embedding_no_msa`, not `unknown`. |
| ColabFold | Mirdita et al., "ColabFold: making protein folding accessible to all" | [`10.1038/s41592-022-01488-1`](https://doi.org/10.1038/s41592-022-01488-1) | [`sokrypton/ColabFold`](https://github.com/sokrypton/ColabFold) | Yes; local ColabFold/MMseqs2 database | Enabled canonical backend. |
| OpenFold | Ahdritz et al., "OpenFold: retraining AlphaFold2 yields new insights into its learning mechanisms and capacity for generalization" | [`10.1038/s41592-024-02272-z`](https://doi.org/10.1038/s41592-024-02272-z) | [`aqlaboratory/openfold`](https://github.com/aqlaboratory/openfold) | Yes; fresh ColabFold/MMseqs2 A3M passed to OpenFold | Enabled canonical backend. |
| OpenFold3-preview | The OpenFold3 Team, OpenFold3-preview software / report | [`10.5281/zenodo.19001000`](https://doi.org/10.5281/zenodo.19001000) | [`aqlaboratory/openfold-3`](https://github.com/aqlaboratory/openfold-3) | Yes; shared ColabFold/MMseqs2 MSA in experimental low-memory mode | Experimental on RTX A5000 24 GB; disabled in canonical config. |
| Protenix | Zhang et al., "Protenix-v1: Toward High-Accuracy Open-Source Biomolecular Structure Prediction" | [`10.64898/2026.02.05.703733`](https://doi.org/10.64898/2026.02.05.703733) | [`bytedance/Protenix`](https://github.com/bytedance/Protenix) | Yes; shared ColabFold/MMseqs2 MSA adapted to Protenix paired/unpaired inputs | Experimental; disabled in canonical config. |
| AlphaFold2 | Jumper et al., "Highly accurate protein structure prediction with AlphaFold" | [`10.1038/s41586-021-03819-2`](https://doi.org/10.1038/s41586-021-03819-2) | [`google-deepmind/alphafold`](https://github.com/google-deepmind/alphafold) | Not benchmarked here | Blocked pending official parameters and AlphaFold database layout; ColabFold is not relabeled as AF2. |

## Benchmark Protocol

The standard runner interface is:

```bash
bash runners/run_MODEL.sh input.fasta output_dir top_k
```

Each runner writes standardized outputs:

```text
output_dir/
├── rank_001.pdb
├── rank_002.pdb
├── ...
└── metadata.json
```

`top_k` is a request, not a guarantee. Single-output backends write only `rank_001.pdb`. The benchmark driver writes per-run status and timing metadata, including MSA provenance columns, to `run_metadata.csv` and `run_status.csv`.

Scoring uses:

- lDDT-C-alpha as the primary ranking metric;
- TM-score normalized by reference length via USalign as a secondary metric;
- C-alpha RMSD as a diagnostic geometry metric.

Canonical scoring should use:

```bash
python scripts/score_benchmark_from_targets.py \
  --targets data/targets/targets_first5.csv \
  --config configs/models.yaml \
  --only-enabled-models \
  --use-tmalign
```

## Shared MSA Protocol

For compatible MSA-based models, the shared-MSA workflow separates homology search from model inference:

1. `scripts/generate_colabfold_msas_from_targets.py` runs ColabFold/MMseqs2 once per target against `/data/chen/protein_folding_databases/colabfold`.
2. The generated cache stores per-target A3M files and a separate `msa_metadata.csv` with MSA runtime and CodeCarbon emissions.
3. `scripts/run_benchmark_from_targets.py --shared-msa-metadata ... --shared-msa-root ...` passes the target-specific shared MSA paths to compatible runners.
4. Model inference rows record `msa_generation_included_in_timing=false`, `msa_generation_included_in_carbon=false`, and `msa_reused=true`.
5. `scripts/summarize_shared_msa_benchmark.py` joins MSA cost, model inference cost, and structure scores for total-cost reporting.

This avoids rerunning the same MSA search separately for every compatible model. In the total-cost table, MSA generation cost is added back once per target for each model so that shared-MSA models can still be compared on an end-to-end basis.

Main shared-MSA outputs:

- `results/shared_msa_colabfold_first5/msa_metadata.csv`
- `results/protenix_openfold3_shared_msa_first5/run_metadata.csv`
- `results/protenix_openfold3_shared_msa_first5/shared_msa_score_cost_summary.csv`

## Performance Summary

All values below are from existing result CSVs; no expensive model rerun is required to regenerate this README. Tables can be regenerated with:

```bash
conda run -n folding-benchmark python scripts/make_readme_benchmark_tables.py
```

### Default/native first-five benchmark

| Model | Mode / MSA | n_success | Mean lDDT-Ca | Mean TM-score | Mean Ca RMSD (A) | Mean inference time (s) | Mean model CO2e (g) | MSA cost included? | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| esmfold | no; native_single_sequence | 5 | 0.748 | 0.750 | 5.888 | 57.8 | 1.04 | no | single-sequence language model |
| omegafold | no; native_single_sequence | 5 | 0.671 | 0.700 | 7.378 | 86.6 | 1.56 | no | single-sequence model |
| boltz2 | no; model_default_no_msa | 5 | 0.564 | 0.591 | 11.693 | 54.3 | 0.98 | no | local runner uses explicit no-MSA mode |
| chai1 | no; native_embedding_no_msa | 5 | 0.721 | 0.718 | 6.552 | 104.5 | 1.89 | no | default Chai-1 uses embeddings without MSAs/templates |
| colabfold | yes; default_msa | 5 | 0.842 | 0.819 | 4.718 | 618.1 | 11.15 | yes | fresh ColabFold/MMseqs search per target |
| openfold | yes; default_msa | 5 | 0.852 | 0.848 | 3.693 | 545.1 | 9.83 | yes | fresh ColabFold/MMseqs A3M passed to OpenFold |

### Shared-MSA experimental first-five benchmark

| Model | Mode / MSA | n_success | Mean lDDT-Ca | Mean TM-score | Mean Ca RMSD (A) | Mean model time (s) | Mean model CO2e (g) | Mean total time with shared MSA (s) | Mean total CO2e with shared MSA (g) | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| protenix | yes; shared_precomputed_msa | 5 | 0.867 | 0.855 | 4.708 | 82.1 | 2.45 | 545.3 | 15.75 | shared A3M converted to Protenix paired/unpaired inputs |
| openfold3 | yes; shared_precomputed_msa | 5 | 0.851 | 0.835 | 5.200 | 103.4 | 3.42 | 566.6 | 16.71 | shared A3M copied as cfdb_hits.a3m; low-memory experimental run |

### ColabFold single-sequence vs MSA ablation

| Model | Mode / MSA | n_success | Mean lDDT-Ca | Mean TM-score | Mean Ca RMSD (A) | Mean inference time (s) | Mean model CO2e (g) |
|---|---|---:|---:|---:|---:|---:|---:|
| colabfold_single | no; forced_single_sequence_ablation | 5 | 0.352 | 0.291 | 19.875 | 98.0 | 0.35 |
| colabfold_msa | yes; msa_ablation | 5 | 0.840 | 0.819 | 4.753 | 613.5 | 1.84 |

### OpenFold single-sequence vs MSA ablation

| Model | Mode / MSA | n_success | Mean lDDT-Ca | Mean TM-score | Mean Ca RMSD (A) | Mean inference time (s) | Mean model CO2e (g) |
|---|---|---:|---:|---:|---:|---:|---:|
| openfold_single | no; forced_single_sequence_ablation | 5 | 0.385 | 0.340 | 19.854 | 53.1 | 0.24 |
| openfold_msa | yes; msa_ablation | 5 | 0.819 | 0.812 | 4.148 | 545.3 | 1.66 |

## Result Sources

The README performance tables use:

- Default/native benchmark: `results/default_modes_first5_carbon_metadata/scores/all_targets_model_summary.csv` and `results/default_modes_first5_carbon_metadata/run_metadata.csv`
- Shared-MSA Protenix/OpenFold3: `results/protenix_openfold3_shared_msa_first5/scores/all_targets_model_summary.csv` and `results/protenix_openfold3_shared_msa_first5/shared_msa_score_cost_summary.csv`
- Shared-MSA generation cost: `results/shared_msa_colabfold_first5/msa_metadata.csv`
- ColabFold ablation: `results/colabfold_single_vs_msa_first5_carbon/`
- OpenFold ablation: `results/openfold_single_vs_msa_first5_carbon/`

Carbon4Science exports live under `/home/chen/projects/carbon4science.github.io/results/`.

## Environment Policy

Use one driver/scoring environment plus one isolated conda environment per folding model. Do not install all folding models into a single conda environment.

| Environment | Purpose |
|---|---|
| `folding-benchmark` | Driver and scoring environment only |
| `openfold` | OpenFold backend |
| `openfold3` | OpenFold3 experimental backend |
| `boltz` | Current working Boltz-2 backend environment; kept for compatibility |
| `chai1` | Chai-1 backend |
| `esmfold` | ESMFold backend |
| `colabfold` | ColabFold backend |
| `alphafold2` | Future/blocked AlphaFold2 backend |
| `alphafold3` | Future restricted AlphaFold3 backend |
| `omegafold` | OmegaFold backend |
| `protenix` | Protenix experimental backend |

The benchmark backend ID is `boltz2`, even though the current environment may remain named `boltz`.

## Current Blockers and Caveats

- Official AlphaFold2 is not benchmarked because official parameters and the AlphaFold database layout are not installed. ColabFold is reported as ColabFold, not AF2.
- AlphaFold3 remains a future restricted-access baseline; weights and output terms require separate review.
- OpenFold3 and Protenix are experimental shared-MSA backends and are disabled in `configs/models.yaml`.
- OpenFold3 uses a low-memory configuration that succeeded on a 24 GB RTX A5000, but broader validation is still needed.
- Historical CSVs from older runs may not include the full MSA provenance schema; current driver metadata does.

## Documentation

Model-specific setup notes are in `model-installation/`. Broader status and workflow notes are in:

- `docs/model_installation_status.md`
- `docs/multitarget_benchmark.md`
- `docs/project_handoff_20260515.md`

For every future Codex instruction, write a dated execution log under `codex-plan/` using the `YYYYMMDD_` filename prefix.
