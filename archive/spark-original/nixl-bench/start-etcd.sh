#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$ROOT/env.sh"
mkdir -p /tmp/etcd-nixl "$ROOT/results"
if curl -fsS --max-time 1 "$ETCD_ENDPOINTS/health" >/dev/null 2>&1; then
  echo "etcd already healthy at $ETCD_ENDPOINTS"
  exit 0
fi
"$ROOT/bin/etcd" \
  --name zeno-02 \
  --data-dir /tmp/etcd-nixl \
  --listen-client-urls http://0.0.0.0:2379 \
  --advertise-client-urls http://10.87.131.182:2379 \
  --listen-peer-urls http://127.0.0.1:2380 \
  --initial-advertise-peer-urls http://127.0.0.1:2380 \
  --initial-cluster zeno-02=http://127.0.0.1:2380
