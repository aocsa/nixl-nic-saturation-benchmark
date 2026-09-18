#!/usr/bin/env python3
"""Serve this repo so remote workers can curl sat.py / start-worker.sh."""

from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = os.environ.get("NIXL_FILES_BIND", "0.0.0.0")
PORT = int(os.environ.get("NIXL_FILES_PORT", "8765"))
ROOT = os.environ.get("NIXL_BENCH_ROOT", str(Path(__file__).resolve().parent))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        print(
            f"{self.log_date_time_string()} {self.address_string()} {fmt % args}",
            flush=True,
        )


if __name__ == "__main__":
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"files http://{HOST}:{PORT}/  root={ROOT}", flush=True)
    httpd.serve_forever()
