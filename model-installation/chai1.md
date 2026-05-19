# Chai-1 Setup Notes

Backend ID: `chai1`
Environment: `chai1`
Status: enabled and working on this machine as of 2026-05-19.

Install used on this machine:

```bash
git clone https://github.com/chaidiscovery/chai-lab.git models/chai-lab
mamba create -n chai1 -c conda-forge python=3.11 pip --yes
conda run -n chai1 python -m pip install chai_lab==0.6.1
```

The installed package reports `chai_lab==0.6.1` and PyTorch `2.6.0+cu124` with CUDA visible. The local `models/chai-lab` checkout was used for setup inspection; the runtime package was installed from the pinned PyPI release.

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

Current real-controller smoke on this machine:

```bash
conda run -n folding-benchmark python scripts/run_benchmark_from_targets.py \
  --targets results/real_backend_smoke/targets_7ROA_chainA.csv \
  --config configs/models.yaml \
  --models chai1 \
  --top-k 1 \
  --predictions-dir results/real_backend_smoke/predictions \
  --sequences-dir results/real_backend_smoke/sequences \
  --logs-dir results/real_backend_smoke/logs \
  --results-dir results/real_backend_smoke \
  --run-metadata results/real_backend_smoke/run_metadata_chai1.csv \
  --run-status results/real_backend_smoke/run_status_chai1.csv \
  --max-trials 1 \
  --gpu-cleanup-sleep-sec 0
```

This produced `results/real_backend_smoke/predictions/7ROA_chainA/chai1/rank_001.pdb` and scored successfully with USalign.

Outputs are standardized to `rank_001.pdb` through `rank_005.pdb` plus
`metadata.json` when `top_k=5`; the real smoke above used `top_k=1`.

Weights and inference assets are cached under `weights/chai1` via `CHAI_DOWNLOADS_DIR`.
