#!/usr/bin/env python3
"""Drive Phase 1 Flight DoPut schemes + iperf3 calibration from zeno-02."""

from __future__ import annotations

import json
import os
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
    f0_split,
    ib_gb,
    iperf3_bin,
    kill_flight,
    log,
    net_stats,
    run_clients_parallel,
    start_server,
)

RV = os.environ.get("FLIGHT_RV", "http://10.87.131.182:8776")
RESULTS = ROOT / "results"
PORT = int(os.environ.get("FLIGHT_PORT", "31337"))

HOSTS = {
    "zeno-01": {
        "mgmt": "10.87.131.181",
        "f0": [("10.87.131.64", 0), ("10.87.131.66", 1)],
    },
    "zeno-02": {
        "mgmt": "10.87.131.182",
        "f0": [("10.87.131.68", 0), ("10.87.131.70", 1)],
    },
    "zeno-03": {
        "mgmt": "10.87.131.183",
        "f0": [("10.87.131.72", 0), ("10.87.131.74", 1)],
    },
}

SEQ = {"zeno-01": 0, "zeno-03": 0}
LOCAL_SERVERS: list[subprocess.Popen] = []


def rv_put(key: str, data: bytes) -> None:
    req = urllib.request.Request(RV + key, data=data, method="PUT")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def rv_get(key: str, timeout_s: float = 300.0) -> bytes:
    url = f"{RV}{key}?wait={int(timeout_s)}"
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=timeout_s + 5) as r:
                return r.read()
        except Exception as e:
            last = e
            time.sleep(0.3)
    raise TimeoutError(f"rv_get {key}: {last}")


def rv_delete(prefix: str) -> None:
    req = urllib.request.Request(RV + prefix, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except Exception:
        pass


def post_cmd(host: str, spec: dict) -> int:
    n = SEQ[host]
    SEQ[host] = n + 1
    rv_put(f"/k/cmd/{host}/{n}", json.dumps(spec).encode())
    log(f"posted {host}/{n} {spec.get('op')} {spec.get('group')}")
    return n


def wait_ack(host: str, n: int, timeout_s: float = 240.0) -> str:
    raw = rv_get(f"/k/ack/{host}/{n}", timeout_s=timeout_s)
    return raw.decode()


def wait_result(key: str, timeout_s: float = 300.0) -> dict:
    raw = rv_get(key, timeout_s=timeout_s)
    return json.loads(raw)


def save(group: str, rec: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{group}.json"
    path.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    log(f"saved {path}")


def wait_workers(timeout_s: float = 3600.0) -> None:
    deadline = time.time() + timeout_s
    pending = {"zeno-01", "zeno-03"}
    log(f"wait workers {pending} up to {timeout_s:.0f}s")
    log("on zeno-01: curl -fsSL http://10.87.131.182:8775/flight-bench/start-worker.sh | bash -s zeno-01")
    log("on zeno-03: curl -fsSL http://10.87.131.182:8775/flight-bench/start-worker.sh | bash -s zeno-03")
    while pending and time.time() < deadline:
        done = set()
        for host in pending:
            try:
                rv_get(f"/k/worker/{host}", timeout_s=3)
                log(f"worker {host} ready")
                done.add(host)
            except Exception:
                pass
        pending -= done
        if pending:
            time.sleep(2.0)
    if pending:
        raise TimeoutError(f"workers not ready: {pending}")


def remote_server(host: str, advertise: str, group: str) -> int:
    spec = {
        "op": "server",
        "group": group,
        "server_host": advertise,
        "port": PORT,
    }
    n = post_cmd(host, spec)
    ack = wait_ack(host, n, timeout_s=60)
    log(f"server ack {host} {ack}")
    time.sleep(0.8)
    return n


def remote_kill(host: str) -> None:
    n = post_cmd(host, {"op": "kill"})
    try:
        wait_ack(host, n, timeout_s=30)
    except Exception as e:
        log(f"kill ack {host}: {e}")


def remote_clients(host: str, group: str, clients: list[dict], result_key: str) -> dict:
    spec = {
        "op": "clients",
        "group": group,
        "clients": clients,
        "result_key": result_key,
        "timeout_s": 600,
    }
    n = post_cmd(host, spec)
    rec = wait_result(result_key, timeout_s=600)
    ack = wait_ack(host, n, timeout_s=60)
    rec["ack"] = ack
    return rec


def local_kill() -> None:
    for p in LOCAL_SERVERS:
        try:
            p.terminate()
        except Exception:
            pass
    LOCAL_SERVERS.clear()
    kill_flight()
    time.sleep(0.4)


def local_start_server(advertise: str) -> None:
    local_kill()
    p = start_server(advertise, PORT)
    LOCAL_SERVERS.append(p)
    time.sleep(1.0)


def summarize(rows: list[dict]) -> None:
    lines = ["group,scheme,gbs,gbps,ok,notes"]
    for rec in rows:
        lines.append(
            f"{rec.get('group')},{rec.get('scheme')},{rec.get('gbs')},{rec.get('gbps')},"
            f"{rec.get('ok')},{rec.get('notes', '')}"
        )
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "summary.csv").write_text("\n".join(lines) + "\n")
    log("summary:\n" + "\n".join(lines))


def _iperf_bps(js: dict) -> float:
    end = js.get("end") or {}
    for key in ("sum_received", "sum_sent", "sum"):
        block = end.get(key)
        if isinstance(block, dict) and "bits_per_second" in block:
            return float(block["bits_per_second"])
    raise KeyError("no bits_per_second in iperf json")


def iperf_one_twin() -> dict:
    """02 .68 -> 01 .64, 10s, 8 parallel streams."""
    group = "iperf-f0a"
    dest, bind = "10.87.131.64", "10.87.131.68"
    n = post_cmd(
        "zeno-01",
        {"op": "iperf_server", "group": group, "bind": dest, "port": 5201},
    )
    wait_ack("zeno-01", n, timeout_s=60)
    time.sleep(1.5)
    argv = [iperf3_bin(), "-c", dest, "-B", bind, "-p", "5201", "-t", "10", "-P", "8", "-J"]
    log("LOCAL " + " ".join(argv))
    before = net_stats()
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=40)
    after = net_stats()
    rec: dict = {"group": group, "scheme": "iperf-one-twin", "rc": proc.returncode}
    rec["stdout"] = (proc.stdout or "")[-2500:]
    rec["stderr"] = (proc.stderr or "")[-1000:]
    try:
        js = json.loads(proc.stdout)
        bps = _iperf_bps(js)
        rec["gbps"] = bps / 1e9
        rec["gbs"] = bps / 8e9
        rec["ok"] = rec["gbps"] >= 90.0  # ~11.25 GB/s
    except Exception as e:
        rec["ok"] = False
        rec["error"] = str(e)
        rec["gbs"] = 0.0
        rec["gbps"] = 0.0
    d = delta_stats(before, after)
    rec["ib_xmit_gb"] = ib_gb(d, "port_xmit_data")
    rec["eth_tx_gb"] = eth_gb(d, "tx_bytes")
    rec["f0_tx"] = f0_split(rec["eth_tx_gb"])
    rec["bind"] = bind
    rec["dest"] = dest
    remote_kill("zeno-01")
    save(group, rec)
    return rec


def iperf_both_twins() -> dict:
    """Both f0 twins in parallel: .68→.64:5201 and .70→.66:5202."""
    group = "iperf-f0-both"
    n1 = post_cmd(
        "zeno-01",
        {"op": "iperf_server", "group": group, "bind": "10.87.131.64", "port": 5201},
    )
    wait_ack("zeno-01", n1, timeout_s=60)
    n2 = post_cmd(
        "zeno-01",
        {"op": "iperf_server", "group": group, "bind": "10.87.131.66", "port": 5202},
    )
    wait_ack("zeno-01", n2, timeout_s=60)
    time.sleep(1.5)
    pairs = [
        ("10.87.131.68", "10.87.131.64", 5201),
        ("10.87.131.70", "10.87.131.66", 5202),
    ]
    before = net_stats()
    procs = []
    for bind, dest, port in pairs:
        argv = [iperf3_bin(), "-c", dest, "-B", bind, "-p", str(port), "-t", "10", "-P", "8", "-J"]
        log("LOCAL " + " ".join(argv))
        procs.append(
            subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        )
    flows = []
    for p, (bind, dest, port) in zip(procs, pairs):
        out, _ = p.communicate(timeout=40)
        flow = {"rc": p.returncode, "bind": bind, "dest": dest, "port": port}
        try:
            js = json.loads(out)
            bps = _iperf_bps(js)
            flow["gbps"] = bps / 1e9
            flow["gbs"] = bps / 8e9
        except Exception as e:
            flow["error"] = str(e)
            flow["stdout"] = (out or "")[-2000:]
        flows.append(flow)
    after = net_stats()
    gbs = sum(f.get("gbs") or 0 for f in flows)
    d = delta_stats(before, after)
    rec = {
        "group": group,
        "scheme": "iperf-both-twins",
        "flows": flows,
        "gbs": gbs,
        "gbps": gbs * 8,
        "ok": gbs >= 20.0,
        "ib_xmit_gb": ib_gb(d, "port_xmit_data"),
        "eth_tx_gb": eth_gb(d, "tx_bytes"),
        "f0_tx": f0_split(eth_gb(d, "tx_bytes")),
    }
    remote_kill("zeno-01")
    save(group, rec)
    return rec


def one_to_one() -> dict:
    """02 writes 01 on both f0 twins."""
    group = "o2o-f0"
    remote_server("zeno-01", "10.87.131.64", group)
    time.sleep(0.5)
    clients = [
        {"bind": "10.87.131.68", "server_host": "10.87.131.64", "port": PORT},
        {"bind": "10.87.131.70", "server_host": "10.87.131.66", "port": PORT},
    ]
    rec = run_clients_parallel(clients)
    rec.update({"group": group, "scheme": "one-to-one", "gbs": rec.get("gbs_sum"), "gbps": rec.get("gbps_sum")})
    rec["notes"] = "02->01 f0 both twins"
    remote_kill("zeno-01")
    save(group, rec)
    return rec


def one_to_many() -> dict:
    """02 writes 01 and 03, both f0 twins each."""
    group = "o2m-f0"
    remote_server("zeno-01", "10.87.131.64", group)
    remote_server("zeno-03", "10.87.131.72", group)
    time.sleep(0.8)
    clients = [
        {"bind": "10.87.131.68", "server_host": "10.87.131.64", "port": PORT},
        {"bind": "10.87.131.70", "server_host": "10.87.131.66", "port": PORT},
        {"bind": "10.87.131.68", "server_host": "10.87.131.72", "port": PORT},
        {"bind": "10.87.131.70", "server_host": "10.87.131.74", "port": PORT},
    ]
    rec = run_clients_parallel(clients)
    rec.update({"group": group, "scheme": "one-to-many", "gbs": rec.get("gbs_sum"), "gbps": rec.get("gbps_sum")})
    rec["notes"] = "02->01+03 f0"
    remote_kill("zeno-01")
    remote_kill("zeno-03")
    save(group, rec)
    return rec


def many_to_one() -> dict:
    """01+03 write 02, both f0 twins."""
    group = "m2o-f0"
    local_start_server("10.87.131.68")
    time.sleep(0.5)
    k1 = f"/k/{group}/result/zeno-01"
    k3 = f"/k/{group}/result/zeno-03"
    rv_delete(f"/k/{group}")
    c1 = [
        {"bind": "10.87.131.64", "server_host": "10.87.131.68", "port": PORT},
        {"bind": "10.87.131.66", "server_host": "10.87.131.70", "port": PORT},
    ]
    c3 = [
        {"bind": "10.87.131.72", "server_host": "10.87.131.68", "port": PORT},
        {"bind": "10.87.131.74", "server_host": "10.87.131.70", "port": PORT},
    ]
    n1 = post_cmd(
        "zeno-01",
        {"op": "clients", "group": group, "clients": c1, "result_key": k1, "timeout_s": 600},
    )
    n3 = post_cmd(
        "zeno-03",
        {"op": "clients", "group": group, "clients": c3, "result_key": k3, "timeout_s": 600},
    )
    r1 = wait_result(k1, timeout_s=600)
    r3 = wait_result(k3, timeout_s=600)
    wait_ack("zeno-01", n1, timeout_s=60)
    wait_ack("zeno-03", n3, timeout_s=60)
    gbs = (r1.get("gbs_sum") or 0) + (r3.get("gbs_sum") or 0)
    rec = {
        "group": group,
        "scheme": "many-to-one",
        "ok": r1.get("ok") and r3.get("ok"),
        "gbs": gbs,
        "gbps": gbs * 8,
        "zeno-01": r1,
        "zeno-03": r3,
        "notes": "01+03->02 f0",
    }
    local_kill()
    save(group, rec)
    return rec


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    wait_workers()
    rows = []

    log("==== iperf one twin ====")
    r = iperf_one_twin()
    rows.append(r)
    log(f"iperf-f0a {r.get('gbs')} GB/s ok={r.get('ok')}")
    if not r.get("ok"):
        log("one-twin iperf did not hit ~12 GB/s; continuing to document")

    log("==== iperf both twins ====")
    r = iperf_both_twins()
    rows.append(r)
    log(f"iperf-f0-both {r.get('gbs')} GB/s ok={r.get('ok')}")
    if not r.get("ok"):
        log("both-twin TCP gate failed; Flight cannot beat this")

    log("==== one-to-one DoPut ====")
    rows.append(one_to_one())
    log("==== one-to-many DoPut ====")
    rows.append(one_to_many())
    log("==== many-to-one DoPut ====")
    rows.append(many_to_one())

    summarize(rows)
    post_cmd("zeno-01", {"op": "STOP"}) if False else rv_put(
        f"/k/cmd/zeno-01/{SEQ['zeno-01']}", b"STOP"
    )
    rv_put(f"/k/cmd/zeno-03/{SEQ['zeno-03']}", b"STOP")
    log("posted STOP")


if __name__ == "__main__":
    try:
        main()
    finally:
        local_kill()
