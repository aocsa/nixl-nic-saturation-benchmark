#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$ROOT/env.sh"
RAIL="${1:?usage: run-sat.sh f0|f1|dual <sat.py args>}"
shift
rail_env "$RAIL"
export PYTHONPATH="${HOME}/.local/lib/python3.12/site-packages:${PYTHONPATH:-}"
exec python3 "$ROOT/sat.py" --rail "$RAIL" "$@"
