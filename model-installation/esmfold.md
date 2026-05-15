# ESMFold Setup Notes

Backend ID: `esmfold`
Environment: `esmfold`
Status: enabled and working.

Current runner:

```bash
bash runners/run_esmfold.sh input.fasta output_dir top_k
```

The runner uses local source under `models/esmfold`, sets `PYTHONPATH`, and
calls:

```bash
python models/esmfold/scripts/fold.py
```

The wrapper defaults to CPU-only mode by adding `--cpu-only`. For a CUDA smoke
test, disable that flag:

```bash
ESMFOLD_CPU_ONLY=0 bash runners/run_esmfold.sh data/sequences/1UAO_chignolin.fasta /tmp/esmfold_gpu_test 1
```

Smoke test:

```bash
bash runners/run_esmfold.sh data/sequences/1UAO_chignolin.fasta /tmp/esmfold_test 5
```

Caveat: ESMFold currently produces one deterministic prediction in this
wrapper, even when `top_k` is 5.
