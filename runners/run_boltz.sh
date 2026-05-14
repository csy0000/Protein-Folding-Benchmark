#!/usr/bin/env bash
set -euo pipefail

echo "WARNING: runners/run_boltz.sh is deprecated; use runners/run_boltz2.sh" >&2
exec bash runners/run_boltz2.sh "$@"
