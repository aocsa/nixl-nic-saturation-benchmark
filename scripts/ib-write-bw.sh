#!/usr/bin/env bash
# Spark CX-7 calibration: ib_write_bw on one twin. Run server on tgt, client here.
# Example (zeno-02 -> zeno-01 f0-A):
#   tgt zeno-01:  ./scripts/ib-write-bw.sh server rocep1s0f0
#   init zeno-02: ./scripts/ib-write-bw.sh client rocep1s0f0 10.87.131.64
set -euo pipefail
ROLE="${1:?usage: ib-write-bw.sh server|client <ibdev> [dest_ip]}"
DEV="${2:?ibdev e.g. rocep1s0f0}"
# Jumbo, RC, 16 QPs — matches archived ibw-02to01-f0*.log
FLAGS=(-d "$DEV" -F -q 16 --tclass 106 -s $((1 << 20)) -n 5000)
case "$ROLE" in
  server) exec ib_write_bw "${FLAGS[@]}" ;;
  client)
    DEST="${3:?dest IP on that twin}"
    exec ib_write_bw "${FLAGS[@]}" "$DEST"
    ;;
  *) echo "server|client" >&2; exit 1 ;;
esac
