# Model Runner Interface

Every model runner must accept:

```bash
bash runners/run_MODEL.sh input.fasta output_dir top_k
```

Each runner must:

1. Accept input FASTA, output directory, and `top_k`.
2. Activate its own conda environment.
3. Run the model.
4. Copy or convert outputs to standardized names:
   ```text
   rank_001.pdb
   rank_002.pdb
   ...
   ```
5. Write `metadata.json`.

Example metadata:

```json
{
  "model": "esmfold",
  "top_k_requested": 5,
  "top_k_generated": 1,
  "environment": "esmfold",
  "note": "This model generated one deterministic prediction."
}
```

For runners that are not yet configured, fail clearly with exit code `2` and point to `docs/model_installation_status.md`.
