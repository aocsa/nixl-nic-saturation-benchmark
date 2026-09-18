#!/usr/bin/env bash
# Run on Spark workers. Pulls Flight harness from the hub fileserver :8775.
set -euo pipefail
HOST="${1:?usage: start-worker.sh zeno-01|zeno-03}"
ROOT="${FLIGHT_BENCH_ROOT:-$HOME/nixl-nic-saturation-benchmark/flight}"
FILES="${FLIGHT_FILES:-http://10.87.131.182:8775}"
RV="${FLIGHT_RV:-http://10.87.131.182:8776}"
export FLIGHT_BENCH_ROOT="$ROOT"
export FLIGHT_RV="$RV"
export FLIGHT_FILES="$FILES"
mkdir -p "$ROOT"
cd "$ROOT"

export http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= all_proxy=
curl --noproxy '*' -fsS -X PUT --data "starting $(hostname) $(date -Is)" "$RV/k/worker/${HOST}" || true

echo "fetching dist.tgz from $FILES/flight/dist.tgz (optional binaries)"
curl --noproxy '*' -fL --retry 5 --retry-delay 1 -o dist.tgz "$FILES/flight/dist.tgz" || true
if [[ -f dist.tgz ]]; then
  tar -xzf dist.tgz || true
fi
for rel in worker.py common.py env.sh lib/bind_connect.so; do
  mkdir -p "$(dirname "$ROOT/$rel")"
  curl --noproxy '*' -fL -o "$ROOT/$rel" "$FILES/flight/$rel" || true
done
chmod +x worker.py bin/iperf3 prefix/bin/* lib/bind_connect.so 2>/dev/null || true
export PATH="$ROOT/prefix/bin:$ROOT/bin:${PATH}"
export LD_LIBRARY_PATH="$ROOT/prefix/lib:${LD_LIBRARY_PATH:-}"
curl --noproxy '*' -fsS -X PUT --data "ready $(hostname)" "$RV/k/worker/${HOST}" || true
exec python3 -u "$ROOT/worker.py" "$HOST"
