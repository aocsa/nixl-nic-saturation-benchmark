#!/usr/bin/env python3
"""Pull NIXL sat.py jobs from the mgmt rendezvous and run them."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RV = os.environ.get("NIXL_RV", "http://10.87.131.182:8766")
FILES = os.environ.get("NIXL_FILES", "http://10.87.131.182:8765")
ROOT = Path(os.environ.get("NIXL_BENCH_ROOT", str(Path.home() / "nixl-bench")))
RAILS = {
    "f0": ("rocep1s0f0:1,roceP2p1s0f0:1", "2"),
    "f1": ("rocep1s0f1:1,roceP2p1s0f1:1", "2"),
    "dual": (
        "rocep1s0f0:1,roceP2p1s0f0:1,rocep1s0f1:1,roceP2p1s0f1:1",
        "4",
    ),
}


def log(msg: str) -> None:
    print(f"# {time.strftime('%H:%M:%S')} {msg}", flush=True)


def rv_get(key: str, timeout_s: float = 600.0) -> bytes:
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


def fetch_scripts() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("sat.py", "env.sh"):
        url = f"{FILES}/{name}"
        dest = ROOT / name
        with urllib.request.urlopen(url, timeout=30) as r:
            dest.write_bytes(r.read())
        dest.chmod(0o755)


def kill_sat() -> None:
    me = os.getpid()
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        pid = int(p.name)
        if pid == me:
            continue
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\x00", b" ").decode(errors="replace")
        except Exception:
            continue
        if "sat.py" in cmd and "worker.py" not in cmd:
            try:
                os.kill(pid, signal.SIGTERM)
                log(f"killed {pid}")
            except Exception:
                pass


def run_job(spec: dict) -> int:
    rail = spec["rail"]
    devices, rails = RAILS[rail]
    env = os.environ.copy()
    env["UCX_TLS"] = env.get("UCX_TLS", "rc,ud,sm,self")
    env["UCX_IB_ROCE_REACHABILITY_MODE"] = "all"
    env["UCX_WARN_UNUSED_ENV_VARS"] = "n"
    env["UCX_NET_DEVICES"] = devices
    env["UCX_MAX_RMA_RAILS"] = rails
    env["NIXL_RV"] = RV
    env["PYTHONPATH"] = (
        str(Path.home() / ".local/lib/python3.12/site-packages")
        + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    argv = ["python3", "-u", str(ROOT / "sat.py"), "--rail", rail] + spec["args"]
    log("RUN " + " ".join(argv))
    log(f"UCX_NET_DEVICES={devices} UCX_MAX_RMA_RAILS={rails}")
    proc = subprocess.run(argv, env=env)
    return proc.returncode


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else os.uname().nodename
    log(f"worker {host} root={ROOT}")
    fetch_scripts()
    rv_put(f"/k/worker/{host}", b"ready")
    log("READY")
    n = 0
    while True:
        log(f"waiting cmd {host}/{n}")
        raw = rv_get(f"/k/cmd/{host}/{n}", timeout_s=900)
        if raw.strip() in (b"STOP", b"stop"):
            log("STOP")
            rv_put(f"/k/ack/{host}/{n}", b"STOP")
            break
        spec = json.loads(raw)
        log(f"job {n} {spec.get('group')} {spec.get('rail')} {spec.get('role')}")
        try:
            fetch_scripts()
            kill_sat()
            time.sleep(0.3)
            rc = run_job(spec)
        except Exception as e:
            log(f"job failed: {e}")
            rc = 99
            rv_put(
                f"/k/{spec.get('group','x')}/result/{host}-error",
                json.dumps({"error": str(e), "host": host}).encode(),
            )
        rv_put(f"/k/ack/{host}/{n}", f"rc={rc}".encode())
        n += 1


if __name__ == "__main__":
    main()
