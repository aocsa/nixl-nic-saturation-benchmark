#!/usr/bin/env python3
"""Pull Flight jobs from mgmt rendezvous :8776 and run them."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ROOT,
    delta_stats,
    eth_gb,
    ib_gb,
    iperf3_bin,
    kill_flight,
    log,
    net_stats,
    run_clients_parallel,
    start_server,
)

RV = os.environ.get("FLIGHT_RV", "http://10.87.131.182:8776")
FILES = os.environ.get("FLIGHT_FILES", "http://10.87.131.182:8775")
SERVERS: list[subprocess.Popen] = []


def rv_get(key: str, timeout_s: float = 900.0) -> bytes:
    url = f"{RV}{key}?wait={int(timeout_s)}"
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=timeout_s + 5) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(0.4)
    raise TimeoutError(f"rv_get {key}: {last}")


def rv_put(key: str, data: bytes) -> None:
    req = urllib.request.Request(RV + key, data=data, method="PUT")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def _wget(rel: str, dest: Path, timeout: int = 120) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{FILES}/flight/{rel}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            dest.write_bytes(r.read())
        dest.chmod(0o755)
        log(f"got {rel} -> {dest} ({dest.stat().st_size}B)")
        return True
    except Exception as e:
        log(f"skip {rel}: {e}")
        return False


def fetch_tree() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    bench = ROOT / "prefix" / "bin" / "arrow-flight-benchmark"
    tgz = ROOT / "dist.tgz"
    if not bench.exists() or bench.stat().st_size < 1_000_000:
        if _wget("dist.tgz", tgz, timeout=180):
            subprocess.run(["tar", "-xzf", str(tgz), "-C", str(ROOT)], check=False)
            log(f"extracted dist.tgz into {ROOT}")
    # Always refresh the small harness so bind_connect.so / parser stay current.
    for rel in ("common.py", "env.sh", "lib/bind_connect.so"):
        _wget(rel, ROOT / rel)


def stop_servers() -> None:
    for p in SERVERS:
        try:
            p.terminate()
        except Exception:
            pass
    SERVERS.clear()
    kill_flight()


def run_job(spec: dict) -> dict:
    op = spec.get("op")
    if op == "kill":
        stop_servers()
        return {"ok": True, "op": "kill"}

    if op == "fetch":
        fetch_tree()
        return {"ok": True, "op": "fetch"}

    if op == "server":
        fetch_tree()
        stop_servers()
        p = start_server(spec["server_host"], int(spec.get("port", 31337)))
        SERVERS.append(p)
        time.sleep(0.8)
        return {"ok": True, "op": "server", "pid": p.pid}

    if op == "clients":
        fetch_tree()
        rec = run_clients_parallel(spec["clients"], timeout_s=float(spec.get("timeout_s", 600)))
        rec["op"] = "clients"
        return rec

    if op == "iperf_server":
        port = int(spec.get("port", 5201))
        bind = spec["bind"]
        argv = [iperf3_bin(), "-s", "-B", bind, "-p", str(port)]
        log("IPERF3S " + " ".join(argv))
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        SERVERS.append(p)
        time.sleep(0.5)
        return {"ok": True, "op": "iperf_server", "pid": p.pid, "bin": argv[0]}

    if op == "iperf_client":
        bind = spec["bind"]
        dest = spec["dest"]
        port = int(spec.get("port", 5201))
        seconds = int(spec.get("seconds", 10))
        argv = [
            iperf3_bin(),
            "-c",
            dest,
            "-B",
            bind,
            "-p",
            str(port),
            "-t",
            str(seconds),
            "-P",
            str(spec.get("parallel", 8)),
            "-J",
        ]
        log("IPERF3C " + " ".join(argv))
        before = net_stats()
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=seconds + 30)
        after = net_stats()
        rec = {"rc": proc.returncode, "stdout": proc.stdout[-8000:], "stderr": proc.stderr[-2000:]}
        try:
            js = json.loads(proc.stdout)
            bps = js["end"]["sum_received"]["bits_per_second"]
            rec["gbps"] = bps / 1e9
            rec["gbs"] = bps / 8e9
        except Exception as e:
            rec["parse_error"] = str(e)
        rec["ib_xmit_gb"] = ib_gb(delta_stats(before, after), "port_xmit_data")
        rec["bind"] = bind
        rec["dest"] = dest
        return rec

    raise ValueError(f"unknown op {op}")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "zeno-unknown"
    log(f"worker {host} root={ROOT}")
    fetch_tree()
    rv_put(f"/k/worker/{host}", b"ready")
    log("READY")
    n = 0
    while True:
        log(f"waiting cmd {host}/{n}")
        raw = rv_get(f"/k/cmd/{host}/{n}", timeout_s=900)
        if raw.strip() in (b"STOP", b"stop"):
            log("STOP")
            stop_servers()
            rv_put(f"/k/ack/{host}/{n}", b"STOP")
            break
        spec = json.loads(raw)
        log(f"job {n} {spec.get('op')} {spec.get('group')}")
        try:
            result = run_job(spec)
            rc = 0 if result.get("ok", True) else 1
            if spec.get("result_key"):
                rv_put(spec["result_key"], json.dumps(result).encode())
        except Exception as e:
            log(f"job failed: {e}")
            rc = 99
            result = {"ok": False, "error": str(e), "host": host}
            if spec.get("result_key"):
                rv_put(spec["result_key"], json.dumps(result).encode())
        rv_put(f"/k/ack/{host}/{n}", f"rc={rc}".encode())
        n += 1


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        stop_servers()
