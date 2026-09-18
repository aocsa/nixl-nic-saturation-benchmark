#!/usr/bin/env bash
# Kill leftover sat.py / iperf3 / duplicate control-plane (the usual "server busy" cause).
set -euo pipefail
pkill -f '[s]at.py' 2>/dev/null || true
pkill -f '[i]perf3' 2>/dev/null || true
pkill -f '[r]endezvous.py' 2>/dev/null || true
pkill -f '[f]ileserver.py' 2>/dev/null || true
echo "cleared sat/iperf/rendezvous/fileserver (if any)"
