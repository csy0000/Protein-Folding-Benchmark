# Boltz-2 Setup Notes

Backend ID: `boltz2`
Environment: `boltz`
Status: enabled and working on this machine as of 2026-05-19.

Install used on this machine:

```bash
git clone https://github.com/jwohlwend/boltz.git models/boltz
mamba create -n boltz -c conda-forge python=3.11 pip --yes
conda run -n boltz python -m pip install -e models/boltz
```

The installed package reports `boltz==2.2.1` from the local editable checkout and PyTorch `2.12.0+cu130` with CUDA visible.

Current runner:

```bash
bash runners/run_boltz2.sh input.fasta output_dir top_k
```

The runner calls:

```bash
boltz predict input_boltz.fasta --diffusion_samples TOP_K --max_parallel_samples TOP_K --output_format pdb --accelerator "$BOLTZ_ACCELERATOR" --no_kernels --override
```

If the benchmark driver provides `SHARED_MSA_A3M_FILE`, the same runner switches to a YAML input with `protein.msa` pointing at the shared ColabFold/MMseqs2 `.a3m`, so Boltz-2 can reuse the cached MSA without regenerating it.

`BOLTZ_ACCELERATOR` defaults to `cpu`. For a CUDA smoke test, run:

```bash
BOLTZ_ACCELERATOR=gpu bash runners/run_boltz2.sh data/sequences/1UAO_chignolin.fasta /tmp/boltz2_gpu_test 1
```

Smoke test:

```bash
bash runners/run_boltz2.sh data/sequences/1UAO_chignolin.fasta /tmp/boltz2_test 5
```

Current real-controller smoke on this machine:

```bash
conda run -n folding-benchmark python scripts/run_benchmark_from_targets.py \
  --targets results/real_backend_smoke/targets_7ROA_chainA.csv \
  --config configs/models.yaml \
  --models boltz2 \
  --top-k 1 \
  --predictions-dir results/real_backend_smoke/predictions \
  --sequences-dir results/real_backend_smoke/sequences \
  --logs-dir results/real_backend_smoke/logs \
  --results-dir results/real_backend_smoke \
  --run-metadata results/real_backend_smoke/run_metadata_boltz2.csv \
  --run-status results/real_backend_smoke/run_status_boltz2.csv \
  --max-trials 1 \
  --gpu-cleanup-sleep-sec 0
```

This produced `results/real_backend_smoke/predictions/7ROA_chainA/boltz2/rank_001.pdb` and scored successfully with USalign.

Outputs are standardized to `rank_001.pdb` through `rank_005.pdb` plus
`metadata.json` when `top_k=5`; the real smoke above used `top_k=1`.

Caveat: the backend ID is `boltz2`, but the current conda environment is named
`boltz` for compatibility.
