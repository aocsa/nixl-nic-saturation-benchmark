#!/usr/bin/env python3
"""Serve the repo root on :8775 so workers can curl /flight/..."""

from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "0.0.0.0"
PORT = int(os.environ.get("FLIGHT_FILES_PORT", "8775"))
ROOT = os.environ.get("FLIGHT_FILES_ROOT", str(Path(__file__).resolve().parent.parent))


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        print(f"{self.log_date_time_string()} {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"files http://{HOST}:{PORT}/flight/  root={ROOT}", flush=True)
    httpd.serve_forever()
