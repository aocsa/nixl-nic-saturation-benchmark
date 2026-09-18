#!/usr/bin/env bash
# Hub only: HTTP rendezvous :8766 + file server :8765.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INV="${INVENTORY:-$ROOT/inventory.env}"
if [[ -f "$INV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$INV"
  set +a
fi
# shellcheck disable=SC1091
source "$ROOT/env.sh"
export NIXL_BENCH_ROOT="$ROOT"
mkdir -p "$ROOT/results"
cd "$ROOT"

kill_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

kill_port "${NIXL_RV_PORT:-8766}"
kill_port "${NIXL_FILES_PORT:-8765}"
sleep 0.3

nohup python3 -u "$ROOT/rendezvous.py" >"$ROOT/results/rendezvous.log" 2>&1 &
echo $! >"$ROOT/results/rendezvous.pid"
nohup python3 -u "$ROOT/fileserver.py" >"$ROOT/results/fileserver.log" 2>&1 &
echo $! >"$ROOT/results/fileserver.pid"
sleep 0.4
echo "rendezvous ${NIXL_RV:-http://127.0.0.1:8766}  pid=$(cat "$ROOT/results/rendezvous.pid")"
echo "files      ${NIXL_FILES:-http://127.0.0.1:8765}  pid=$(cat "$ROOT/results/fileserver.pid")"
curl -fsS --noproxy '*' "${NIXL_RV:-http://127.0.0.1:8766}/health" && echo
