# AF2 Setup Notes

Backend ID: `af2` (not enabled)  
Related existing placeholder: `alphafold2`  
Environment: `af2` or `alphafold2` (not installed)  
Source checkout: `models/alphafold` at `c77e5d2a8961d1a353632c462914ff0a32a950f6`  
Status: blocked / not validated as of 2026-05-21.

Official AlphaFold2 source was inspected, but no AF2 benchmark runner was added.
A valid `af2` backend must be distinct from the existing `colabfold` backend.
Reusing ColabFold with AlphaFold2-style weights would duplicate an already
enabled implementation and must not be reported as AF2.

Exact blocker for the 7ROA one-target smoke:

- No separate AF2 conda environment is installed.
- No official AlphaFold database layout was found under `/data/chen`.
- Official AlphaFold2 inference expects model parameters plus full or reduced
  genetic/template databases, including paths such as UniRef90, MGnify, PDB70,
  PDB mmCIF, and small BFD for reduced DB mode.
- Upstream documentation reports about 556 GB to download and 2.62 TB
  uncompressed for the full database setup; reduced DB mode still requires
  hundreds of GB.
- The task did not authorize downloading full AlphaFold/OpenFold databases.
- Existing local ColabFold/MMseqs assets support the `colabfold` backend, not a
  distinct official AF2 backend.
- `--use_precomputed_msas` is not a complete bypass for official setup here; the
  official script still validates required parameter/database/template paths and
  expects AlphaFold-compatible precomputed output layout.

Output diagnostic: `results/backend_smoke/af2_default/BLOCKED.md`.

A future approved route would create an isolated `af2`/`alphafold2` environment,
install the official AlphaFold dependencies, download parameters plus the reduced
or full official database tree to an explicit `/data/chen/...` location, and then
add a real runner around `models/alphafold/run_alphafold.py`.
