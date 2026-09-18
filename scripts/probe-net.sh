#!/usr/bin/env bash
# Print fabric / NIC facts used to decide UCX vs LIBFABRIC and the GB/s cap.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/env.sh" 2>/dev/null || true
echo "=== host ==="
hostname
uname -a
echo "=== IPs ==="
ip -br addr || true
echo "=== MTU ==="
ip -o link | awk '{print $2,$14,$15}' || true
echo "=== netdevs ==="
ls -1 /sys/class/net || true
echo "=== infiniband ==="
ls -1 /sys/class/infiniband 2>/dev/null || echo "(none)"
if command -v ibstat >/dev/null 2>&1; then ibstat || true; fi
if command -v ibv_devinfo >/dev/null 2>&1; then ibv_devinfo -v 2>/dev/null | head -n 80 || true; fi
echo "=== ethtool (up devices) ==="
for d in /sys/class/net/*; do
  n="$(basename "$d")"
  [[ "$n" == lo ]] && continue
  ethtool "$n" 2>/dev/null | awk -v d="$n" '
    /Speed:|Duplex:|Link detected:/ {print d, $0}
  ' || true
done
echo "=== EFA / libfabric ==="
if [[ -x /opt/amazon/efa/bin/fi_info ]]; then
  /opt/amazon/efa/bin/fi_info -p efa -t FI_EP_RDM || true
elif command -v fi_info >/dev/null 2>&1; then
  fi_info -p efa -t FI_EP_RDM || fi_info -l || true
else
  echo "fi_info not found"
fi
ls /dev/infiniband 2>/dev/null || true
echo "=== IMDS (AWS) ==="
TOKEN="$(curl -fsS -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' \
  http://169.254.169.254/latest/api/token 2>/dev/null || true)"
if [[ -n "$TOKEN" ]]; then
  H="X-aws-ec2-metadata-token: $TOKEN"
  echo -n "instance-type="; curl -fsS -H "$H" http://169.254.169.254/latest/meta-data/instance-type; echo
  echo -n "placement/availability-zone="; curl -fsS -H "$H" http://169.254.169.254/latest/meta-data/placement/availability-zone; echo
  echo -n "macs="; curl -fsS -H "$H" http://169.254.169.254/latest/meta-data/network/interfaces/macs/; echo
else
  echo "(not on EC2 or IMDS blocked)"
fi
echo "=== python nics ==="
python3 - "$ROOT" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[1])
from nics import discover_eth_names, discover_nics, net_stats
print("ib_pairs", discover_nics())
print("eth", discover_eth_names())
print(json.dumps(net_stats(), indent=2, default=str)[:4000])
PY
echo "=== nixl import ==="
python3 -c "import nixl; print('nixl', getattr(nixl,'__file__', nixl))" 2>&1 || echo "nixl not importable"
