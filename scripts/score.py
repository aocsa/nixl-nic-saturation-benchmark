#!/usr/bin/env python3
"""Score results/summary.csv against CAP_GBS (default 12.5 for g7e.8xlarge)."""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = Path(os.environ.get("NIXL_RESULTS", ROOT / "results"))


def cap() -> float:
    return float(os.environ.get("CAP_GBS", "12.5"))


def main() -> int:
    path = RESULTS / "summary.csv"
    if not path.exists():
        print(f"missing {path}", file=sys.stderr)
        return 1
    c = cap()
    print(f"CAP_GBS={c}  PROFILE={os.environ.get('PROFILE', '')}")
    print(f"{'group':<22} {'scheme':<14} {'GB/s':>8} {'vs cap':>8}")
    with path.open() as f:
        rows = list(csv.DictReader(f))
    rc = 0
    for row in rows:
        try:
            gbs = float(row.get("gbs") or 0)
        except ValueError:
            gbs = 0.0
        pct = 100.0 * gbs / c if c else 0.0
        print(
            f"{row.get('group',''):<22} {row.get('scheme',''):<14} {gbs:8.3f} {pct:7.0f}%"
        )
        if row.get("scheme") == "iperf-tcp" and gbs < 0.5:
            rc = 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
