# OpenFold3 Setup Notes

Backend ID: `openfold3`
Environment: `openfold3`
Source checkout: `models/openfold-3` at `c9bfe23d25dfa79caa22b5eb6b64202f7c2b27c7`
Status: installed experimentally / disabled by default.

OpenFold3 is installed in a separate conda environment and passed a one-target
7ROA smoke on 2026-05-21. It remains disabled in the canonical benchmark config
until broader validation is requested.

## Installed Components

- Conda environment: `openfold3`
- Python: 3.11
- Package: PyPI `openfold3==0.4.1`
- Torch stack: PyTorch `2.10.0+cu128`
- CUDA toolkit: `cuda-toolkit=12.8` installed inside the `openfold3` env
- Checkpoint: `weights/openfold3/of3-p2-155k.pt`
- CCD data: downloaded by `setup_openfold` into the environment's Biotite data path

`CUDA_HOME` must point at the conda environment when importing/running OpenFold3:

```bash
CONDA_BASE="$(conda info --base)"
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate openfold3
export CUDA_HOME="${CONDA_PREFIX}"
export LD_LIBRARY_PATH="${CONDA_PREFIX}/lib:${LD_LIBRARY_PATH:-}"
```

## Runner

The experimental benchmark runner is:

```text
runners/run_openfold3.sh
```

It preserves the standard runner interface:

```bash
bash runners/run_openfold3.sh input.fasta output_dir top_k
```

The runner currently supports `top_k=1`, writes `rank_001.pdb` and
`metadata.json`, disables the MSA server/templates, uses OpenFold3's low-memory
preset, and disables fused DeepSpeed/CUEQ/Triton triangle/evoformer kernels that
failed JIT compatibility on the local RTX A5000 setup.

Use the temporary smoke config for isolated OpenFold3 runs:

```text
tmp/backend_smoke/models_openfold3_only.yaml
```

## 2026-05-21 Smoke Result

Target: `7ROA_chainA`
Output root: `results/backend_smoke/openfold3_default/`
Prediction: `results/backend_smoke/openfold3_default/predictions/7ROA_chainA/openfold3/rank_001.pdb`

The one-target run succeeded on GPU 0 with one seed and one diffusion sample.
The benchmark driver recorded:

- Runtime: `82.752562` seconds
- Carbon emissions: `0.0023836289056808897` kg CO2e (`2.3836289056808897` g)
- Energy: `0.005018166117222926` kWh
- Mean GPU power during tracked run: `113.654` W
- lDDT-C-alpha: `0.4756351915054986`
- TM-score normalized by reference length: `0.39914`
- TM-align RMSD: `4.17`
- C-alpha RMSD: `9.56415825975804`

Scoring output:

```text
results/backend_smoke/openfold3_default/scores/7ROA_chainA_scores.csv
results/backend_smoke/openfold3_default/scores/all_targets_model_summary.csv
```

## Resolved Install Issues

- `CUDA_HOME does not exist`: resolved by installing `cuda-toolkit=12.8` in the
  `openfold3` environment and exporting `CUDA_HOME=${CONDA_PREFIX}`.
- `NVCC_PREPEND_FLAGS: unbound variable`: resolved by seeding
  `NVCC_PREPEND_FLAGS` before conda activation in the runner.
- Query schema rejected `use_msas` fields: removed unsupported fields for
  `openfold3==0.4.1`.
- DeepSpeed evoformer JIT compatibility failure: avoided by disabling fused
  evoformer/triangle kernels in the low-memory runner YAML.

## Notes

Upstream docs state a 32 GB GPU minimum for standard inference. The local smoke
succeeded on an RTX A5000 with about 24 GB VRAM only after using the low-memory
preset and disabling fused kernels. Treat this as an experimental path until it
has been validated on more targets.


## Shared MSA Smoke (2026-05-22)

The shared-MSA runner is:

```text
runners/run_openfold3_shared_msa.sh
```

It expects `SHARED_MSA_DIR` and `SHARED_MSA_A3M_FILE` from the benchmark driver, copies the A3M to an OpenFold3-compatible `cfdb_hits.a3m`, and sets query-level `main_msa_file_paths` with templates and paired MSAs disabled.

The first-five shared ColabFold/MMseqs2 MSA run succeeded for 5/5 targets under `results/protenix_openfold3_shared_msa_first5/`. OpenFold3 first-five summary: mean lDDT-C-alpha `0.8514732150023233`, mean TM-score normalized by reference `0.834862`, and mean successful predictions per target `1.0`.

One-target shared-MSA output is under `results/backend_smoke/openfold3_shared_msa/`; its combined MSA-plus-model score/cost table is `results/backend_smoke/openfold3_shared_msa/shared_msa_score_cost_summary.csv`.
