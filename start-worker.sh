#!/usr/bin/env bash
# Run on every node except the hub (or on all nodes if the hub also uses a worker).
# Usage:
#   ./start-worker.sh node1
#   curl -fsSL http://HUB:8765/start-worker.sh | NIXL_RV=http://HUB:8766 NIXL_FILES=http://HUB:8765 bash -s node1
set -euo pipefail
HOST="${1:?usage: start-worker.sh <inventory-name>}"

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy || true

if [[ -n "${NIXL_BENCH_ROOT:-}" ]]; then
  ROOT="$NIXL_BENCH_ROOT"
elif [[ -f "$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)/worker.py" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
  ROOT="${HOME}/nixl-nic-saturation-benchmark"
fi
mkdir -p "$ROOT"
cd "$ROOT"
export NIXL_BENCH_ROOT="$ROOT"

INV="${INVENTORY:-$ROOT/inventory.env}"
if [[ -f "$INV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$INV"
  set +a
fi

if [[ -f "$ROOT/env.sh" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/env.sh"
fi

FILES="${NIXL_FILES:-http://127.0.0.1:8765}"
RV="${NIXL_RV:-http://127.0.0.1:8766}"
export NIXL_FILES="$FILES"
export NIXL_RV="$RV"

fetch() {
  local name="$1"
  curl --noproxy '*' -fsSL --retry 5 --retry-delay 1 -o "$ROOT/$name" "$FILES/$name" || true
  chmod +x "$ROOT/$name" 2>/dev/null || true
}

echo "worker $HOST fetching harness from $FILES into $ROOT"
for f in worker.py sat.py nics.py inventory.py env.sh coord.py; do
  fetch "$f"
done

export PATH="${ROOT}/bin:${HOME}/.local/bin:${PATH}"
if [[ -d /opt/amazon/efa ]]; then
  export PATH="/opt/amazon/efa/bin:${PATH}"
  export LD_LIBRARY_PATH="/opt/amazon/efa/lib:/opt/amazon/efa/lib64:${LD_LIBRARY_PATH:-}"
fi
export PYTHONPATH="${ROOT}:${HOME}/.local/lib/python3.12/site-packages:${PYTHONPATH:-}"

curl --noproxy '*' -fsS -X PUT --data "ready $(hostname) $(date -Is)" "$RV/k/worker/${HOST}" || true
exec python3 -u "$ROOT/worker.py" "$HOST"
