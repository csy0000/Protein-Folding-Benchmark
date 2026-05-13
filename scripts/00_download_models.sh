#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/models" "$ROOT/envs" "$ROOT/data/predictions" "$ROOT/data/scores"

cd "$ROOT/models"

clone_or_update () {
    local name="$1"
    local url="$2"

    if [ -d "$name/.git" ]; then
        echo "[update] $name"
        git -C "$name" pull --ff-only || true
    else
        echo "[clone] $name"
        git clone "$url" "$name"
    fi
}

clone_or_update alphafold2     https://github.com/google-deepmind/alphafold.git
clone_or_update colabfold      https://github.com/sokrypton/ColabFold.git
clone_or_update openfold       https://github.com/aqlaboratory/openfold.git
clone_or_update unifold        https://github.com/dptech-corp/Uni-Fold.git
clone_or_update rosettafold    https://github.com/RosettaCommons/RoseTTAFold.git
clone_or_update esmfold        https://github.com/facebookresearch/esm.git
clone_or_update omegafold      https://github.com/HeliXonProtein/OmegaFold.git
clone_or_update boltz          https://github.com/jwohlwend/boltz.git
clone_or_update chai1          https://github.com/chaidiscovery/chai-lab.git
clone_or_update spired         https://github.com/Gonglab-THU/SPIRED-Fitness.git
clone_or_update raptorx_single https://github.com/AndersJing/RaptorX-Single.git

echo "Model repositories downloaded."
echo "Next: install each model environment separately, because CUDA/JAX/PyTorch dependencies conflict."
