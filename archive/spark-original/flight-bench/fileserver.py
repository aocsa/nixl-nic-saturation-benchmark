#!/usr/bin/env python3
"""Serve /home/aocsa/git/flight-bench on mgmt :8775 for remote workers."""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import os

HOST = "0.0.0.0"
PORT = 8775
ROOT = "/home/aocsa/git"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def log_message(self, fmt, *args):
        print(f"{self.log_date_time_string()} {self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    os.chdir(ROOT)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"files http://{HOST}:{PORT}/flight-bench/", flush=True)
    httpd.serve_forever()
