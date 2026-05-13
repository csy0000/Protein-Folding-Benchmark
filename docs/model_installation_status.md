# Model Installation Status

| Model | Environment | Repo path | Installed? | Runner exists? | Tested on 1UAO? | Notes |
|---|---|---|---|---|---|---|
| ESMFold | esmfold | models/esmfold and models/esm | env repaired | yes | yes | `openfold` now imports. Runner uses local ESM source, CPU-only mode, project-local Torch cache, and a checkpoint-key compatibility shim. Produced `rank_001.pdb`; scoring succeeded. |
| OmegaFold | omegafold | models/omegafold and models/OmegaFold | env repaired | yes | yes | Initial PyPI install failed, then `pip install -e models/OmegaFold` succeeded. Produced `rank_001.pdb`; scoring succeeded. |
| Boltz | boltz | models/boltz | env created | placeholder | no | Runner exists but intentionally exits until command mapping is configured; no `rank_001.pdb` generated. |
| Chai-1 | chai1 | models/chai1 and models/chai-lab | env created | placeholder | no | Runner exists but intentionally exits until command mapping is configured; no `rank_001.pdb` generated. |
| ColabFold | colabfold | models/colabfold and models/ColabFold | env created | placeholder | no | Runner placeholder only; do not download databases unless requested; no `rank_001.pdb` generated. |
| AlphaFold2 | alphafold2 | models/alphafold2 and models/alphafold | env created | placeholder | no | Official installation and parameters are required; no full database download attempted; no `rank_001.pdb` generated. |
| OpenFold | openfold | models/openfold | env created | placeholder | no | Repository-specific dependencies may be required after cloning; no `rank_001.pdb` generated. |
| RoseTTAFold | rosettafold | models/rosettafold and models/RoseTTAFold | env created | placeholder | no | May require legacy dependency adjustments and external databases; no `rank_001.pdb` generated. |
