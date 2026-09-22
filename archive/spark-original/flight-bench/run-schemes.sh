#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$ROOT/env.sh"
export PATH="${HOME}/.local/bin:${PATH}"
exec python3 -u "$ROOT/coord.py"
