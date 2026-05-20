# ColabFold Setup Notes

Backend ID: `colabfold`
Environment: `colabfold`
Status: enabled and working.

Current runner:

```bash
bash runners/run_colabfold.sh input.fasta output_dir top_k
```

The benchmark runner uses:

- `colabfold_batch`
- `--msa-mode single_sequence`
- `--model-type alphafold2_ptm`
- local parameter cache under `weights/colabfold`

Smoke test:

```bash
bash runners/run_colabfold.sh data/sequences/1UAO_chignolin.fasta /tmp/colabfold_test 5
```

Outputs should appear as `rank_001.pdb` through `rank_005.pdb` plus
`metadata.json`. The 2026-05-19 7ROA smoke used `top_k=1` and produced
`rank_001.pdb` under `results/backend_smoke/colabfold_single_sequence/`;
the combined six-backend smoke also passed under
`results/backend_smoke/six_backend_single_sequence/`.

Caveat: this benchmark smoke mode does not require full local sequence
databases. Full ColabFold/MMseqs workflows may need network or database setup.

GPU note: the `colabfold` environment was updated with the matching CUDA JAX
packages for `jax==0.5.3`:

```bash
conda run -n colabfold python -m pip install "jax[cuda12]==0.5.3"
```

After this update, `jax.devices()` reports CUDA devices and the 7ROA smoke
logs `Running on GPU`.

## Validated MSA Mode (2026-05-20)

The runner now supports explicit ColabFold variants via environment variables:

- `COLABFOLD_MSA_MODE=single_sequence` for no-MSA/single-sequence mode.
- `COLABFOLD_MSA_MODE=mmseqs2_uniref_env` for local ColabFold/MMseqs2 MSA mode.

For MSA-mode timing and carbon accounting, `runners/run_colabfold.sh` removes the run-local `tmp_colabfold_msa_search` directory, runs `colabfold_search` against `/data/chen/protein_folding_databases/colabfold`, then runs `colabfold_batch` on the generated A3M within the same benchmarked subprocess. This means `run_metadata.csv` timing and CodeCarbon fields include both MSA search and structure prediction.

The reusable smoke command is:

```bash
bash scripts/smoke_test_colabfold_single_vs_msa_first5_with_carbon.sh
```

It writes to `results/colabfold_single_vs_msa_first5_carbon/` and uses the model IDs `colabfold_single` and `colabfold_msa`.
