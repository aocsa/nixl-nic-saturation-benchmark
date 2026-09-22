#!/usr/bin/env python3
"""Shared helpers: counters, Flight client/server launch, output parse."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from pathlib import Path

NICS = [
    ("rocep1s0f0", "enp1s0f0np0"),
    ("rocep1s0f1", "enp1s0f1np1"),
    ("roceP2p1s0f0", "enP2p1s0f0np0"),
    ("roceP2p1s0f1", "enP2p1s0f1np1"),
]

# Same netdev names on all three Sparks; IPs are per-host f0/f1 twins.
IP_TO_DEV = {
    "10.87.131.64": "enp1s0f0np0",
    "10.87.131.65": "enp1s0f1np1",
    "10.87.131.66": "enP2p1s0f0np0",
    "10.87.131.67": "enP2p1s0f1np1",
    "10.87.131.68": "enp1s0f0np0",
    "10.87.131.69": "enp1s0f1np1",
    "10.87.131.70": "enP2p1s0f0np0",
    "10.87.131.71": "enP2p1s0f1np1",
    "10.87.131.72": "enp1s0f0np0",
    "10.87.131.73": "enp1s0f1np1",
    "10.87.131.74": "enP2p1s0f0np0",
    "10.87.131.75": "enP2p1s0f1np1",
}

ROOT = Path(os.environ.get("FLIGHT_BENCH_ROOT", "/home/aocsa/git/flight-bench"))
PREFIX = ROOT / "prefix"
BIND_SO = ROOT / "lib" / "bind_connect.so"


def log(msg: str) -> None:
    print(f"# {time.strftime('%H:%M:%S')} {msg}", flush=True)


def bench_bin() -> Path:
    p = PREFIX / "bin" / "arrow-flight-benchmark"
    if p.exists():
        return p
    return ROOT / "bin" / "arrow-flight-benchmark"


def server_bin() -> Path:
    p = PREFIX / "bin" / "arrow-flight-perf-server"
    if p.exists():
        return p
    return ROOT / "bin" / "arrow-flight-perf-server"


def lib_env() -> dict:
    env = os.environ.copy()
    lib = str(PREFIX / "lib")
    extra = str(ROOT / "lib")
    env["PATH"] = f"{PREFIX / 'bin'}:{ROOT / 'bin'}:{env.get('PATH', '')}"
    prev = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = f"{lib}:{extra}:{prev}" if prev else f"{lib}:{extra}"
    return env


def net_stats() -> dict:
    out = {}
    for ib, eth in NICS:
        rec = {}
        tx = Path(f"/sys/class/net/{eth}/statistics/tx_bytes")
        rx = Path(f"/sys/class/net/{eth}/statistics/rx_bytes")
        if tx.exists():
            rec["tx_bytes"] = int(tx.read_text())
            rec["rx_bytes"] = int(rx.read_text())
        xmit = Path(f"/sys/class/infiniband/{ib}/ports/1/counters/port_xmit_data")
        rcv = Path(f"/sys/class/infiniband/{ib}/ports/1/counters/port_rcv_data")
        if xmit.exists():
            rec["port_xmit_data"] = int(xmit.read_text())
            rec["port_rcv_data"] = int(rcv.read_text())
        out[eth] = rec
    return out


def delta_stats(before: dict, after: dict) -> dict:
    d = {}
    for nic, b in before.items():
        a = after.get(nic, {})
        d[nic] = {k: a.get(k, 0) - b.get(k, 0) for k in set(b) | set(a)}
    return d


def ib_gb(delta: dict, key: str = "port_xmit_data") -> dict:
    """IB counters are 4-byte words. TCP often leaves these at 0; use eth_gb."""
    return {nic: rec.get(key, 0) * 4 / 1e9 for nic, rec in delta.items()}


def eth_gb(delta: dict, key: str = "tx_bytes") -> dict:
    return {nic: rec.get(key, 0) / 1e9 for nic, rec in delta.items()}


def f0_split(eth: dict) -> dict:
    """Rail-f0 twin split from ethtool/sysfs byte counters."""
    a = eth.get("enp1s0f0np0", 0) or 0
    b = eth.get("enP2p1s0f0np0", 0) or 0
    return {
        "enp1s0f0np0_gb": a,
        "enP2p1s0f0np0_gb": b,
        "f0_sum_gb": a + b,
        "both_twins": a > 1.0 and b > 1.0,
    }


def parse_flight_output(text: str) -> dict:
    """arrow-flight-benchmark prints MiB/s (1<<20). Convert to SI GB/s from bytes+nanos."""
    rec: dict = {"raw_tail": text[-2000:]}
    m_bytes = re.search(r"Bytes (?:written|read):\s*(\d+)", text)
    m_nanos = re.search(r"Nanos:\s*(\d+)", text)
    m_speed = re.search(r"Speed:\s*([0-9.]+)\s*MB/s", text)
    if m_bytes:
        rec["bytes"] = int(m_bytes.group(1))
    if m_nanos:
        rec["nanos"] = int(m_nanos.group(1))
    if m_speed:
        rec["mib_s"] = float(m_speed.group(1))
    if "bytes" in rec and "nanos" in rec and rec["nanos"] > 0:
        rec["gbs"] = rec["bytes"] / rec["nanos"]  # bytes/ns == SI GB/s
        rec["gbps"] = rec["gbs"] * 8
    elif "mib_s" in rec:
        rec["gbs"] = rec["mib_s"] * (1 << 20) / 1e9
        rec["gbps"] = rec["gbs"] * 8
    return rec


def flight_flags() -> list[str]:
    return [
        "-test_put",
        f"-records_per_batch={os.environ.get('FLIGHT_RECORDS_PER_BATCH', '65536')}",
        f"-records_per_stream={os.environ.get('FLIGHT_RECORDS_PER_STREAM', '67108864')}",
        f"-num_streams={os.environ.get('FLIGHT_NUM_STREAMS', '8')}",
        f"-num_threads={os.environ.get('FLIGHT_NUM_THREADS', '8')}",
        "-num_perf_runs=1",
    ]


def start_server(advertise_host: str, port: int) -> subprocess.Popen:
    env = lib_env()
    argv = [
        str(server_bin()),
        f"-server_host={advertise_host}",
        f"-port={port}",
        "-transport=grpc",
    ]
    log("SERVER " + " ".join(argv))
    return subprocess.Popen(
        argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )


def run_clients_parallel(clients: list[dict], timeout_s: float = 600.0) -> dict:
    """Run several arrow-flight-benchmark processes at once; sum SI GB/s."""
    before = net_stats()
    env_base = lib_env()
    procs = []
    for c in clients:
        env = env_base.copy()
        bind = c.get("bind", "")
        if BIND_SO.exists() and bind:
            env["LD_PRELOAD"] = str(BIND_SO) + (
                (":" + env["LD_PRELOAD"]) if env.get("LD_PRELOAD") else ""
            )
            env["BIND_ADDR"] = bind
            if bind in IP_TO_DEV:
                env["BIND_DEV"] = IP_TO_DEV[bind]
        argv = [
            str(bench_bin()),
            f"-server_host={c['server_host']}",
            f"-server_port={int(c.get('port', 31337))}",
            "-transport=grpc",
        ] + flight_flags()
        log("CLIENT " + " ".join(argv) + f" BIND_ADDR={bind}")
        procs.append(
            (
                c,
                subprocess.Popen(
                    argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                ),
            )
        )
    results = []
    for c, p in procs:
        out, _ = p.communicate(timeout=timeout_s)
        rec = parse_flight_output(out or "")
        rec.update(
            {
                "rc": p.returncode,
                "server_host": c["server_host"],
                "bind_addr": c.get("bind"),
                "port": int(c.get("port", 31337)),
            }
        )
        if p.returncode != 0:
            rec["error"] = (out or "")[-4000:]
        results.append(rec)
    after = net_stats()
    delta = delta_stats(before, after)
    return {
        "ok": all(r.get("rc") == 0 for r in results),
        "results": results,
        "gbs_sum": sum(r.get("gbs") or 0 for r in results),
        "gbps_sum": sum(r.get("gbps") or 0 for r in results),
        "ib_xmit_gb": ib_gb(delta, "port_xmit_data"),
        "ib_rcv_gb": ib_gb(delta, "port_rcv_data"),
        "eth_tx_gb": eth_gb(delta, "tx_bytes"),
        "eth_rx_gb": eth_gb(delta, "rx_bytes"),
        "f0_tx": f0_split(eth_gb(delta, "tx_bytes")),
        "eth_delta": delta,
        "host": os.uname().nodename,
    }


def run_client(server_host: str, port: int, bind_addr: str, timeout_s: float = 600.0) -> dict:
    env = lib_env()
    if BIND_SO.exists() and bind_addr:
        env["LD_PRELOAD"] = str(BIND_SO) + (
            (":" + env["LD_PRELOAD"]) if env.get("LD_PRELOAD") else ""
        )
        env["BIND_ADDR"] = bind_addr
        if bind_addr in IP_TO_DEV:
            env["BIND_DEV"] = IP_TO_DEV[bind_addr]
    argv = [
        str(bench_bin()),
        f"-server_host={server_host}",
        f"-server_port={port}",
        "-transport=grpc",
    ] + flight_flags()
    log("CLIENT " + " ".join(argv) + f" BIND_ADDR={bind_addr}")
    t0 = time.time()
    proc = subprocess.run(
        argv, env=env, capture_output=True, text=True, timeout=timeout_s
    )
    elapsed = time.time() - t0
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    rec = parse_flight_output(text)
    rec.update(
        {
            "rc": proc.returncode,
            "wall_s": elapsed,
            "server_host": server_host,
            "bind_addr": bind_addr,
            "port": port,
        }
    )
    if proc.returncode != 0:
        rec["error"] = text[-4000:]
    return rec


def kill_flight() -> None:
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
        if (
            "arrow-flight-benchmark" in cmd
            or "arrow-flight-perf-server" in cmd
            or cmd.strip().startswith("iperf3")
            or "/iperf3" in cmd
        ):
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass


def iperf3_bin() -> str:
    for c in (
        ROOT / "bin" / "iperf3",
        Path.home() / ".local" / "bin" / "iperf3",
    ):
        if c.exists():
            return str(c)
    return "iperf3"
