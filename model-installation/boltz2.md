# Boltz-2 Setup Notes

Backend ID: `boltz2`
Environment: `boltz`
Status: enabled and working.

Current runner:

```bash
bash runners/run_boltz2.sh input.fasta output_dir top_k
```

The runner calls:

```bash
boltz predict input_boltz.fasta --diffusion_samples TOP_K --max_parallel_samples TOP_K --output_format pdb --accelerator cpu --no_kernels --override
```

Smoke test:

```bash
bash runners/run_boltz2.sh data/sequences/1UAO_chignolin.fasta /tmp/boltz2_test 5
```

Outputs are standardized to `rank_001.pdb` through `rank_005.pdb` plus
`metadata.json`.

Caveat: the backend ID is `boltz2`, but the current conda environment is named
`boltz` for compatibility.
