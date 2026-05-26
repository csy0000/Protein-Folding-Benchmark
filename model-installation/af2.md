# AF2 Setup Notes

Backend ID: `af2`
Environment: `af2`
Source checkout: `models/alphafold` at `c77e5d2a8961d1a353632c462914ff0a32a950f6`
Database root: `/data/chen/protein_folding_databases/alphafold`
Status: validated on 2026-05-26 for the first-five CASP smoke set.

Official AlphaFold2 is implemented as a distinct backend and is not an alias for
ColabFold. The runner uses the standard benchmark interface:

```bash
bash runners/run_af2.sh input.fasta output_dir top_k
```

The current wrapper calls `scripts/run_af2_split_pipeline.py`, which imports the
official DeepMind AlphaFold source from `models/alphafold`, runs full official
MSA/template feature generation, writes `features.pkl`, then runs JAX inference
for the requested top-k subset of official monomer models. The 2026-05-26 run
used `top_k=1`, `model_1`, `model_preset=monomer`, `db_preset=full_dbs`, and
disabled Amber relaxation.

MSA metadata for `af2` is:

- `msa_used=true`
- `msa_source=alphafold2_default`
- `msa_mode=official_af2_database_search`
- `msa_database=alphafold`
- `msa_database_path=/data/chen/protein_folding_databases/alphafold`
- `msa_generation_included_in_timing=true`
- `msa_generation_included_in_carbon=true`
- `msa_reused=false`

Split-stage outputs are recorded in:

- `results/af2_first5_split_carbon/run_metadata.csv`
- `results/af2_first5_split_carbon/af2_stage_metadata.csv`
- per-target `metadata.json` under `results/af2_first5_split_carbon/predictions/<target>/af2/`

First-five result summary from `results/af2_first5_split_carbon/scores/all_targets_model_summary.csv`:

- `n_targets_success=5`
- mean lDDT-C-alpha: `0.8754336456168662`
- mean TM-score normalized by reference length: `0.852168`
- mean C-alpha RMSD: `4.02535248453391`

Mean split cost from `run_metadata.csv`:

- MSA/features runtime: `1723.634842` seconds per target
- MSA/features CO2e: `45.1201802476462` g per target
- AF2 inference runtime: `130.4129638` seconds per target
- AF2 inference CO2e: `4.496196255893913` g per target
- Total runtime: `1854.0478058` seconds per target
- Total CO2e: `49.61637650354013` g per target

The backend remains disabled in `configs/models.yaml` so routine canonical runs
do not unexpectedly launch the full official AlphaFold database search. Use
`tmp/backend_smoke/models_af2_only.yaml` for isolated AF2 runs.
