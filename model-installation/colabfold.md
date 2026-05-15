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
`metadata.json`.

Caveat: this benchmark smoke mode does not require full local sequence
databases. Full ColabFold/MMseqs workflows may need network or database setup.

GPU note: the `colabfold` environment was updated with the matching CUDA JAX
packages for `jax==0.5.3`:

```bash
conda run -n colabfold python -m pip install "jax[cuda12]==0.5.3"
```

After this update, `jax.devices()` reports `CudaDevice(id=0)` and the Chignolin
smoke run logs `Running on GPU`.
