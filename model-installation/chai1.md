# Chai-1 Setup Notes

Backend ID: `chai1`
Environment: `chai1`
Status: enabled and working.

Current runner:

```bash
bash runners/run_chai1.sh input.fasta output_dir top_k
```

The runner calls:

```bash
chai-lab fold input_chai1.fasta tmp_chai1 --num-diffn-samples TOP_K --device "$CHAI1_DEVICE"
```

`CHAI1_DEVICE` defaults to `cpu`. For a CUDA smoke test, run:

```bash
CHAI1_DEVICE=cuda:0 bash runners/run_chai1.sh data/sequences/1UAO_chignolin.fasta /tmp/chai1_gpu_test 1
```

Smoke test:

```bash
bash runners/run_chai1.sh data/sequences/1UAO_chignolin.fasta /tmp/chai1_test 5
```

Outputs are standardized to `rank_001.pdb` through `rank_005.pdb` plus
`metadata.json`.

Caveat: exact installation commands should be verified against the local
`chai1` environment and upstream Chai-1 documentation.
