#!/usr/bin/env bash
# Three-node DRAM NIXL is included in coord.py after the 9 pairwise jobs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$ROOT/env.sh"
exec python3 -u "$ROOT/coord.py"
