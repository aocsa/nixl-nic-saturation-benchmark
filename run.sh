#!/usr/bin/env bash
# Hub: drive TCP iperf3 then NIXL DRAM WRITE. Workers must already be READY.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
INV="${1:-${INVENTORY:-$ROOT/inventory.env}}"
if [[ ! -f "$INV" ]]; then
  echo "missing inventory $INV" >&2
  echo "copy inventory.example.env or profiles/aws-g7e.env -> inventory.env and fill IPs" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$INV"
# shellcheck disable=SC1091
source "$ROOT/env.sh"
set +a
export NIXL_BENCH_ROOT="$ROOT"
export INVENTORY="$INV"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"
exec python3 -u "$ROOT/coord.py"
