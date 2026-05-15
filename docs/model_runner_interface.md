# Model Runner Interface

Every model runner must accept:

```bash
bash runners/run_MODEL.sh input.fasta output_dir top_k
```

Backend IDs are:

- `openfold`
- `openfold3`
- `boltz2`
- `chai1`
- `esmfold`
- `colabfold`
- `alphafold2`
- `alphafold3`
- `omegafold`

Each runner must:

1. Accept input FASTA, output directory, and `top_k`.
2. Activate its own conda environment.
3. Run the model.
4. Copy or convert outputs to standardized names:
   ```text
   rank_001.pdb
   rank_002.pdb
   rank_003.pdb
   rank_004.pdb
   rank_005.pdb
   metadata.json
   ```
5. Write `metadata.json`.

Required metadata shape:

```json
{
  "model": "backend_id",
  "environment": "conda_env_name",
  "top_k_requested": 5,
  "top_k_generated": 5,
  "top_k_policy": "genuine generated samples only; no artificial duplication",
  "source_files": []
}
```

`top_k` is a request, not a guarantee. Do not duplicate one deterministic structure into multiple `rank_*.pdb` files. `top_k_generated` must reflect the number of genuine structures the model produced.

Current runner expectations:

- Chai-1 and Boltz-2 may generate five genuine samples.
- ESMFold and OmegaFold generally generate one prediction by default.
- ColabFold currently produces five ranked outputs with the local `--msa-mode single_sequence` smoke configuration.
- OpenFold is integrated and enabled through `runners/run_openfold.sh` and `scripts/run_openfold.py`; existing score rows come from prior single-sequence smoke outputs, while fresh runner invocations default to MSA mode and require configured `OPENFOLD_REPO`, `OPENFOLD_PARAMS_DIR`, `OPENFOLD_DATA_DIR`, and related variables.
- AlphaFold2 and OpenFold may produce multiple ranked outputs depending on configuration.
- AlphaFold3 and OpenFold3 runner behavior is pending implementation.
- `boltz2` is the canonical Boltz backend ID. The legacy `boltz` ID is deprecated, and `runners/run_boltz.sh` is kept only as a compatibility wrapper around `runners/run_boltz2.sh`.

`scripts/standardize_structure_outputs.py` can be used by runners that emit PDB, CIF, or mmCIF files under a model-specific temporary directory. It converts or copies the first `top_k` discovered structures into standardized ranks and writes standardized metadata.

For runners that are not yet configured, fail clearly with exit code `2` and point to `docs/model_installation_status.md` when useful.

## OpenFold Runner

The OpenFold shell runner follows the same benchmark contract:

```bash
bash runners/run_openfold.sh input.fasta output_dir top_k
```

It activates the `openfold` conda environment and delegates to:

```bash
python scripts/run_openfold.py \
  --fasta-path input.fasta \
  --output-dir output_dir \
  --num-models top_k
```

Default MSA resources:

- `OPENFOLD_REPO`: defaults to `models/openfold`.
- `OPENFOLD_PARAMS_DIR`: defaults to `weights/colabfold/params`.
- `OPENFOLD_PARAM_PATH`: defaults to `weights/colabfold/params/params_model_1.npz`.
- `OPENFOLD_DATA_DIR`: defaults to `work/openfold_inputs`.
- `OPENFOLD_TEMPLATE_MMCIF_DIR`: defaults to `$OPENFOLD_DATA_DIR/pdb_mmcif/mmcif_files`.
- `OPENFOLD_MODE`: defaults to `msa`.

Override environment variables for full OpenFold runs:

- `OPENFOLD_REPO`: OpenFold repository path containing `run_pretrained_openfold.py`.
- `OPENFOLD_PARAMS_DIR`: directory or file containing OpenFold/AlphaFold parameter files.
- `OPENFOLD_DATA_DIR`: AlphaFold/OpenFold-compatible data directory for templates/databases.

Optional environment variables:

- `OPENFOLD_PARAM_PATH`: explicit `.npz`, `.pt`, `.pth`, or `.ckpt` parameter file.
- `OPENFOLD_TEMPLATE_MMCIF_DIR`: explicit template mmCIF directory.
- `OPENFOLD_MODE=single_sequence`: explicit smoke-test mode.
- `OPENFOLD_PRECOMPUTED_ALIGNMENTS`: precomputed alignment directory, accepted only for explicit single-sequence smoke mode in the project wrapper.
- `OPENFOLD_CONFIG_PRESET`: OpenFold config preset, default `model_1`.
- `OPENFOLD_DEVICE`: torch device, default `cuda:0` in the runner.

The higher-level CSV benchmark driver, `scripts/run_benchmark_from_targets.py`,
also injects GPU defaults for supported backends unless the caller has already
set the corresponding environment variable: `BOLTZ_ACCELERATOR=gpu`,
`CHAI1_DEVICE=cuda:0`, `ESMFOLD_CPU_ONLY=0`, and `OPENFOLD_DEVICE=cuda:0`.

Raw OpenFold outputs are written under `output_dir/raw/`, and genuine PDB outputs are copied to `rank_001.pdb`, `rank_002.pdb`, and so on. The runner does not duplicate outputs to satisfy `top_k`. If required MSA databases are absent, the wrapper fails before inference and leaves existing standardized predictions in place.

## Scoring Interface

The scoring script supports:

1. C-alpha RMSD using sequential residue order:
   ```bash
   --match-mode sequential
   ```
2. C-alpha RMSD using residue sequence numbers:
   ```bash
   --match-mode resseq
   ```
3. TM-align / US-align structural alignment:
   ```bash
   --use-tmalign --tmalign-bin auto
   ```
4. C-alpha-only lDDT in `lddt_ca` using the matched C-alpha atoms and a default reference-distance cutoff of 15.0 A:
   ```bash
   --lddt-cutoff 15.0
   ```
5. Optional lDDT disabling for diagnostics:
   ```bash
   --disable-lddt
   ```
6. TM-score normalized by reference length in `tmalign_tm_score_ref`.
7. TM-score normalized by prediction length in `tmalign_tm_score_pred`.
8. TM-align RMSD and aligned length in `tmalign_rmsd` and `tmalign_aligned_length`.

For benchmark comparison against one fixed reference, use `lddt_ca` as the primary metric and `tmalign_tm_score_ref` as the secondary metric. C-alpha RMSD remains a diagnostic metric.

For canonical benchmark CSV generation, pass:

```bash
--config configs/models.yaml --only-enabled-models
```

This scores only enabled backend IDs from the config and warns about ignored stale prediction folders.

All standardized `rank_*.pdb` files are scored individually in the raw score CSV. After that, `scripts/03_summarize_scores.py` aggregates the per-prediction rows into one row per model/backend and records the best prediction according to the configured ranking metrics.
