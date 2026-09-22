#!/usr/bin/env bash
# Run on zeno-01 or zeno-03. Pulls harness from zeno-02 and loops on rendezvous.
set -euo pipefail
HOST="${1:?usage: start-worker.sh zeno-01|zeno-03}"
ROOT="${FLIGHT_BENCH_ROOT:-$HOME/git/flight-bench}"
FILES="${FLIGHT_FILES:-http://10.87.131.182:8775}"
RV="${FLIGHT_RV:-http://10.87.131.182:8776}"
export FLIGHT_BENCH_ROOT="$ROOT"
export FLIGHT_RV="$RV"
export FLIGHT_FILES="$FILES"
mkdir -p "$ROOT"
cd "$ROOT"

export http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= all_proxy=
# Check in immediately so zeno-02 can see we launched.
curl --noproxy '*' -fsS -X PUT --data "starting $(hostname) $(date -Is)" "$RV/k/worker/${HOST}" || true

echo "fetching dist.tgz from $FILES"
curl --noproxy '*' -fL --retry 5 --retry-delay 1 -o dist.tgz "$FILES/flight-bench/dist.tgz"
tar -xzf dist.tgz
chmod +x worker.py bin/iperf3 prefix/bin/* lib/bind_connect.so || true
export PATH="$ROOT/prefix/bin:$ROOT/bin:${PATH}"
export LD_LIBRARY_PATH="$ROOT/prefix/lib:${LD_LIBRARY_PATH:-}"
curl --noproxy '*' -fsS -X PUT --data "ready $(hostname)" "$RV/k/worker/${HOST}" || true
exec python3 -u "$ROOT/worker.py" "$HOST"
