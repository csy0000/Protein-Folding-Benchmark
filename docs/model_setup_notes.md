# Model Setup Notes

This file summarizes model-specific setup for the benchmark backends. The
canonical runner contract remains:

```bash
bash runners/run_MODEL.sh input.fasta output_dir top_k
```

Outputs are written under `data/predictions/<target_id>/<backend>/` as
`rank_*.pdb` plus `metadata.json`.

| Backend | Environment | Enabled | Local status | Validation command |
|---|---|---:|---|---|
| `boltz2` | `boltz` | yes | Working; produces five genuine sampled structures. | `bash runners/run_boltz2.sh data/sequences/1UAO_chignolin.fasta /tmp/boltz2_test 5` |
| `chai1` | `chai1` | yes | Working; produces five genuine sampled structures. | `bash runners/run_chai1.sh data/sequences/1UAO_chignolin.fasta /tmp/chai1_test 5` |
| `esmfold` | `esmfold` | yes | Working; single-output baseline. | `bash runners/run_esmfold.sh data/sequences/1UAO_chignolin.fasta /tmp/esmfold_test 5` |
| `colabfold` | `colabfold` | yes | Working; smoke mode uses `--msa-mode single_sequence` and five ranked AF2-PTM models. | `bash runners/run_colabfold.sh data/sequences/1UAO_chignolin.fasta /tmp/colabfold_test 5` |
| `omegafold` | `omegafold` | yes | Working; single-output baseline. | `bash runners/run_omegafold.sh data/sequences/1UAO_chignolin.fasta /tmp/omegafold_test 5` |
| `openfold` | `openfold` | yes | Working in single-sequence smoke mode; see `models/openfold/README.md`. | `bash runners/run_openfold.sh data/sequences/1UAO_chignolin.fasta /tmp/openfold_test 1` |
| `openfold3` | `openfold3` | no | Future backend; repository present, not validated. | Not yet available. |
| `alphafold2` | `alphafold2` | no | Optional/future backend; parameters and databases not configured for this benchmark. | Not yet available. |
| `alphafold3` | `alphafold3` | no | Future restricted/non-commercial-use backend; keep disabled unless usage terms are resolved. | Not yet available. |

OpenFold currently uses AlphaFold-style parameters from
`weights/colabfold/params/params_model_1.npz` for the benchmark smoke path.
For production OpenFold runs, provide a real parameter directory, template
mmCIF directory, and MSA databases or precomputed alignments via the
`OPENFOLD_*` environment variables documented in `models/openfold/README.md`.
