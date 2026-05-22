# AlphaFold2 Setup Notes

Backend ID: `alphafold2`
Environment: `alphafold2`
Status: disabled / future optional backend.

AlphaFold2 requires official parameters and large sequence/template databases
for normal operation. These resources are not configured for the current
benchmark, and the backend is not enabled.

Do not download large databases unless explicitly requested.

## 2026-05-21 AF2 Smoke Attempt

Official AlphaFold2 source was inspected at `models/alphafold` (`c77e5d2a8961d1a353632c462914ff0a32a950f6`). The one-target `7ROA_chainA` smoke was not run because a distinct official AF2 backend is not locally configured: no `alphafold2`/`af2` environment exists, no official AlphaFold database layout was found under `/data/chen`, and the official pipeline requires AlphaFold model parameters plus full or reduced genetic/template databases. The task did not authorize downloading those large databases. Reusing ColabFold as AF2 was rejected because it would duplicate the existing `colabfold` backend under another name.

Diagnostic output: `results/backend_smoke/af2_default/BLOCKED.md`. Additional setup notes for the requested `af2` backend ID are in `model-installation/af2.md`.
