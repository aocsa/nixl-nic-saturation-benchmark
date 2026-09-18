#!/usr/bin/env python3
"""HTTP KV control plane. Bind 0.0.0.0 so workers can reach the hub on any IP."""

from __future__ import annotations

import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

STORE: dict[str, bytes] = {}
CV = threading.Condition()
HOST = os.environ.get("NIXL_RV_BIND", "0.0.0.0")
PORT = int(os.environ.get("NIXL_RV_PORT", "8766"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"{self.log_date_time_string()} {fmt % args}", flush=True)

    def _key(self) -> str:
        return urlparse(self.path).path

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        wait = float(parse_qs(parsed.query).get("wait", ["180"])[0])
        key = parsed.path
        deadline = time.time() + wait
        with CV:
            while key not in STORE and time.time() < deadline:
                CV.wait(timeout=0.2)
            val = STORE.get(key)
        if val is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"missing")
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(val)))
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(val)

    def do_PUT(self):
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n)
        key = self._key()
        with CV:
            STORE[key] = body
            CV.notify_all()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        print(f"PUT {key} {len(body)}B keys={len(STORE)}", flush=True)

    def do_DELETE(self):
        prefix = self._key()
        with CV:
            drop = [k for k in STORE if k.startswith(prefix)]
            for k in drop:
                del STORE[k]
            CV.notify_all()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(str(len(drop)).encode())
        print(f"DELETE {prefix} dropped={len(drop)}", flush=True)


if __name__ == "__main__":
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"rendezvous http://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()
