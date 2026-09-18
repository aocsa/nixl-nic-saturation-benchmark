#!/usr/bin/env bash
# Spark Flight control plane on :8776 / :8775 (do not collide with NIXL :8766 / :8765).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export FLIGHT_BENCH_ROOT="$ROOT/flight"
export NIXL_BENCH_ROOT="$ROOT"
mkdir -p "$ROOT/results"
python3 -u "$ROOT/flight/rendezvous.py" >"$ROOT/results/flight-rendezvous.log" 2>&1 &
echo $! >"$ROOT/results/flight-rendezvous.pid"
python3 -u "$ROOT/flight/fileserver.py" >"$ROOT/results/flight-fileserver.log" 2>&1 &
echo $! >"$ROOT/results/flight-fileserver.pid"
sleep 0.3
echo "flight rendezvous :8776 pid=$(cat "$ROOT/results/flight-rendezvous.pid")"
echo "flight files      :8775 pid=$(cat "$ROOT/results/flight-fileserver.pid")"
