# OmegaFold Setup Notes

Backend ID: `omegafold`
Environment: `omegafold`
Status: enabled and working.

Current runner:

```bash
bash runners/run_omegafold.sh input.fasta output_dir top_k
```

The runner calls the `omegafold` executable and standardizes the first PDB as
`rank_001.pdb`.

Smoke test:

```bash
bash runners/run_omegafold.sh data/sequences/1UAO_chignolin.fasta /tmp/omegafold_test 5
```

Caveat: OmegaFold currently produces one prediction per sequence in this basic
wrapper, even when `top_k` is 5.

## NumPy Compatibility Guard

OmegaFold previously failed with native segmentation faults on small CASP
targets such as `7QIH_chainA` and `7ROA_chainA`. The issue was not sequence
length or target memory demand. The local OmegaFold stack used PyTorch binaries
built against the NumPy 1.x ABI while the environment had NumPy 2.x installed.

Known bad combination:

```text
torch 1.12.0+cu113
numpy 2.0.2
```

Fix:

```bash
conda activate omegafold
pip install "numpy==1.26.4" --force-reinstall
```

Sanity check:

```bash
python - <<'PY'
import numpy as np
major = int(np.__version__.split(".")[0])
assert major < 2, f"OmegaFold requires numpy<2, found numpy {np.__version__}"
print("OmegaFold NumPy check OK", np.__version__)
PY
```

`runners/run_omegafold.sh` now performs this check before calling the
`omegafold` executable, so the pipeline fails with a clear message instead of a
silent segmentation fault if NumPy 2.x is installed.
