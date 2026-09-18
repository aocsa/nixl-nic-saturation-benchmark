#!/usr/bin/env python3
"""Pull sat.py / iperf jobs from the hub rendezvous."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RV = os.environ.get("NIXL_RV", "http://127.0.0.1:8766")
FILES = os.environ.get("NIXL_FILES", "http://127.0.0.1:8765")
ROOT = Path(os.environ.get("NIXL_BENCH_ROOT", str(Path(__file__).resolve().parent)))


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
    for name in (
        "sat.py",
        "nics.py",
        "inventory.py",
        "env.sh",
        "worker.py",
        "coord.py",
    ):
        url = f"{FILES}/{name}"
        dest = ROOT / name
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                dest.write_bytes(r.read())
            dest.chmod(0o755)
        except Exception as e:
            log(f"skip {name}: {e}")


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
        if "/iperf3" in cmd or cmd.strip().startswith("iperf3"):
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass


def rail_env(spec: dict) -> dict:
    env = os.environ.copy()
    env["NIXL_RV"] = RV
    env["NIXL_BACKEND"] = spec.get("backend") or env.get("NIXL_BACKEND", "UCX")
    if spec.get("ucx_tls"):
        env["UCX_TLS"] = spec["ucx_tls"]
    if spec.get("ucx_net_devices"):
        env["UCX_NET_DEVICES"] = spec["ucx_net_devices"]
        env["UCX_MAX_RMA_RAILS"] = str(spec.get("ucx_max_rma_rails", "1"))
        env["UCX_IB_ROCE_REACHABILITY_MODE"] = "all"
        env["UCX_WARN_UNUSED_ENV_VARS"] = "n"
    if spec.get("fi_provider"):
        env["FI_PROVIDER"] = spec["fi_provider"]
        env["FI_EFA_USE_DEVICE_RDMA"] = spec.get("fi_efa_use_device_rdma", "1")
        env["FI_EFA_ENABLE_SHM"] = spec.get("fi_efa_enable_shm", "0")
        env["RDMAV_FORK_SAFE"] = "1"
    site = Path.home() / ".local/lib/python3.12/site-packages"
    if site.is_dir():
        env["PYTHONPATH"] = str(site) + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
    return env


def run_job(spec: dict) -> int:
    op = spec.get("op", "sat")
    if op == "iperf_server":
        bind = spec["bind"]
        port = int(spec.get("port", 5201))
        argv = ["iperf3", "-s", "-B", bind, "-p", str(port)]
        log("IPERF3S " + " ".join(argv))
        subprocess.Popen(argv)
        time.sleep(0.4)
        return 0
    if op == "kill":
        kill_sat()
        return 0
    env = rail_env(spec)
    argv = ["python3", "-u", str(ROOT / "sat.py")]
    if spec.get("rail"):
        argv += ["--rail", spec["rail"]]
    argv += spec["args"]
    log("RUN " + " ".join(argv))
    log(
        f"backend={env.get('NIXL_BACKEND')} UCX_NET_DEVICES={env.get('UCX_NET_DEVICES','')} "
        f"FI_PROVIDER={env.get('FI_PROVIDER','')}"
    )
    return subprocess.run(argv, env=env).returncode


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
        log(f"job {n} {spec.get('op', spec.get('role'))} {spec.get('group')}")
        try:
            fetch_scripts()
            if spec.get("op") != "iperf_server":
                kill_sat()
                time.sleep(0.3)
            rc = run_job(spec)
        except Exception as e:
            log(f"job failed: {e}")
            rc = 99
            rv_put(
                f"/k/{spec.get('group', 'x')}/result/{host}-error",
                json.dumps({"error": str(e), "host": host}).encode(),
            )
        rv_put(f"/k/ack/{host}/{n}", f"rc={rc}".encode())
        n += 1


if __name__ == "__main__":
    main()
