#!/usr/bin/env bash
# Launch pairwise DRAM NIXL jobs (requires workers on zeno-01/03).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$ROOT/env.sh"
exec python3 -u "$ROOT/coord.py"
