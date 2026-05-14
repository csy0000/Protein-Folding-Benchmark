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
