#!/usr/bin/env python3
"""Drive TCP iperf3 calibration then NIXL DRAM WRITE schemes.

Inventory: source profiles/*.env then run:
  python3 -u coord.py
Hub runs this. Other nodes run start-worker.sh <name>.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

from inventory import apply_env, hub_name, parse_hosts, repo_root
from nics import delta_stats, eth_gb, ib_gb, net_stats

ROOT = repo_root()
RESULTS = ROOT / "results"
RV = os.environ.get("NIXL_RV", "http://127.0.0.1:8766")
PYTHON = "python3"

SAT_FLAGS = [
    "--block-size",
    os.environ.get("NIXL_BLOCK_SIZE", "16777216"),
    "--batch",
    os.environ.get("NIXL_BATCH", "8"),
    "--iters",
    os.environ.get("NIXL_ITERS", "200"),
    "--warmup",
    os.environ.get("NIXL_WARMUP", "50"),
]

SPARK_RAILS = {
    "f0": ("rocep1s0f0:1,roceP2p1s0f0:1", "2"),
    "f1": ("rocep1s0f1:1,roceP2p1s0f1:1", "2"),
    "dual": (
        "rocep1s0f0:1,roceP2p1s0f0:1,rocep1s0f1:1,roceP2p1s0f1:1",
        "4",
    ),
}


def log(msg: str) -> None:
    print(f"# {time.strftime('%H:%M:%S')} {msg}", flush=True)


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


def hosts() -> dict:
    return parse_hosts()


def short(name: str) -> str:
    if name.startswith("zeno-"):
        return name[-2:]
    return name.replace("node", "n").replace("-", "")[:8]


SEQ: dict[str, int] = {}


def post_cmd(host: str, spec: dict) -> int:
    n = SEQ.setdefault(host, 0)
    SEQ[host] = n + 1
    rv_put(f"/k/cmd/{host}/{n}", json.dumps(spec).encode())
    log(f"posted {host}/{n} {spec.get('op', spec.get('role'))} {spec.get('group')}")
    return n


def wait_ack(host: str, n: int, timeout_s: float = 240.0) -> str:
    return rv_get(f"/k/ack/{host}/{n}", timeout_s=timeout_s).decode()


def wait_result(group: str, name: str, timeout_s: float = 240.0) -> dict:
    return json.loads(rv_get(f"/k/{group}/result/{name}", timeout_s=timeout_s))


def wait_workers(names: list[str], timeout_s: float = 3600.0) -> None:
    pending = set(names)
    log(f"wait workers {pending}")
    deadline = time.time() + timeout_s
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


def kill_local_sat() -> None:
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
        if "sat.py" in cmd:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass


def transport_fields(rail: str) -> dict:
    backend = os.environ.get("NIXL_BACKEND", "UCX")
    rec: dict = {"backend": backend, "rail": rail or os.environ.get("RAIL", "default")}
    if backend == "LIBFABRIC":
        rec["fi_provider"] = os.environ.get("FI_PROVIDER", "efa")
        rec["fi_efa_use_device_rdma"] = os.environ.get("FI_EFA_USE_DEVICE_RDMA", "1")
        rec["fi_efa_enable_shm"] = os.environ.get("FI_EFA_ENABLE_SHM", "0")
        return rec
    rec["ucx_tls"] = os.environ.get("UCX_TLS", "rc,ud,sm,self")
    if rail in SPARK_RAILS:
        devices, n = SPARK_RAILS[rail]
        rec["ucx_net_devices"] = devices
        rec["ucx_max_rma_rails"] = n
    elif os.environ.get("UCX_NET_DEVICES"):
        rec["ucx_net_devices"] = os.environ["UCX_NET_DEVICES"]
        rec["ucx_max_rma_rails"] = os.environ.get("UCX_MAX_RMA_RAILS", "1")
    return rec


def local_env(spec: dict) -> dict:
    env = os.environ.copy()
    env["NIXL_RV"] = RV
    env["NIXL_BACKEND"] = spec.get("backend") or env.get("NIXL_BACKEND", "UCX")
    if spec.get("ucx_net_devices"):
        env["UCX_NET_DEVICES"] = spec["ucx_net_devices"]
        env["UCX_MAX_RMA_RAILS"] = str(spec.get("ucx_max_rma_rails", "1"))
        env["UCX_TLS"] = spec.get("ucx_tls", "rc,ud,sm,self")
        env["UCX_IB_ROCE_REACHABILITY_MODE"] = "all"
        env["UCX_WARN_UNUSED_ENV_VARS"] = "n"
    if spec.get("fi_provider"):
        env["FI_PROVIDER"] = spec["fi_provider"]
        env["FI_EFA_USE_DEVICE_RDMA"] = spec.get("fi_efa_use_device_rdma", "1")
        env["FI_EFA_ENABLE_SHM"] = spec.get("fi_efa_enable_shm", "0")
        env["RDMAV_FORK_SAFE"] = "1"
    return env


def run_local(spec: dict) -> subprocess.Popen:
    kill_local_sat()
    time.sleep(0.2)
    argv = [PYTHON, "-u", str(ROOT / "sat.py")]
    if spec.get("rail"):
        argv += ["--rail", spec["rail"]]
    argv += spec["args"]
    log("LOCAL " + " ".join(argv))
    return subprocess.Popen(argv, env=local_env(spec))


def tgt_ep(hname: str) -> str:
    h = hosts()[hname]
    return f"tgt-{short(hname)}@{h['ip']}:{h['port']}"


def target_spec(group, rail, host, scheme, initiators) -> dict:
    h = hosts()[host]
    name = f"tgt-{short(host)}"
    args = [
        "--role", "target", "--name", name, "--scheme", scheme,
        "--initiators", initiators, "--listen-port", str(h["port"]),
        "--group", group,
    ] + SAT_FLAGS
    rec = transport_fields(rail)
    rec.update({"group": group, "role": "target", "host": host, "name": name, "args": args})
    return rec


def initiator_spec(group, rail, host, scheme, targets) -> dict:
    h = hosts()[host]
    name = f"init-{short(host)}"
    args = [
        "--role", "initiator", "--name", name, "--scheme", scheme,
        "--targets", targets, "--listen-port", str(h["port"]),
        "--group", group,
    ] + SAT_FLAGS
    rec = transport_fields(rail)
    rec.update({"group": group, "role": "initiator", "host": host, "name": name, "args": args})
    return rec


def save(group: str, rec: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{group}.json"
    path.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    log(f"saved {path}")


def is_hub(name: str) -> bool:
    return name == hub_name()


def pairwise(group: str, rail: str, tgt_host: str, init_host: str) -> dict:
    rv_delete(f"/k/{group}")
    tspec = target_spec(group, rail, tgt_host, "pairwise", f"init-{short(init_host)}")
    ispec = initiator_spec(group, rail, init_host, "pairwise", tgt_ep(tgt_host))
    local_proc = None
    remote_acks = []
    if is_hub(tgt_host):
        local_proc = run_local(tspec)
    else:
        remote_acks.append((tgt_host, post_cmd(tgt_host, tspec)))
    time.sleep(1.0)
    if is_hub(init_host):
        if local_proc is not None:
            raise RuntimeError("hub cannot be both initiator and target")
        local_proc = run_local(ispec)
    else:
        remote_acks.append((init_host, post_cmd(init_host, ispec)))
    rec = wait_result(group, ispec["name"], timeout_s=240)
    if local_proc is not None:
        local_proc.wait(timeout=60)
    for host, n in remote_acks:
        try:
            wait_ack(host, n, timeout_s=60)
        except Exception as e:
            log(f"ack {host}/{n}: {e}")
    rec.setdefault("group", group)
    save(group, rec)
    return rec


def iperf_bin() -> str:
    return shutil.which("iperf3") or "iperf3"


def _iperf_bps(js: dict) -> float:
    end = js.get("end") or {}
    for key in ("sum_received", "sum_sent", "sum"):
        block = end.get(key)
        if isinstance(block, dict) and "bits_per_second" in block:
            return float(block["bits_per_second"])
    raise KeyError("no bits_per_second in iperf json")


def iperf_pair(init_host: str, tgt_host: str, seconds: int = 10) -> dict:
    """TCP iperf3 from init to tgt using inventory IPs. Server on tgt."""
    group = f"iperf-{short(init_host)}-{short(tgt_host)}"
    dest = hosts()[tgt_host]["ip"]
    bind = hosts()[init_host]["ip"]
    port = int(os.environ.get("IPERF_PORT", "5201"))
    if is_hub(tgt_host):
        argv_s = [iperf_bin(), "-s", "-B", dest, "-p", str(port)]
        log("LOCAL " + " ".join(argv_s))
        srv = subprocess.Popen(argv_s, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        time.sleep(0.8)
        try:
            rec = _iperf_client(group, bind, dest, port, seconds)
        finally:
            srv.terminate()
        save(group, rec)
        return rec
    n = post_cmd(
        tgt_host,
        {"op": "iperf_server", "group": group, "bind": dest, "port": port},
    )
    wait_ack(tgt_host, n, timeout_s=60)
    time.sleep(1.0)
    rec = _iperf_client(group, bind, dest, port, seconds)
    post_cmd(tgt_host, {"op": "kill"})
    save(group, rec)
    return rec


def _iperf_client(group, bind, dest, port, seconds) -> dict:
    argv = [iperf_bin(), "-c", dest, "-B", bind, "-p", str(port), "-t", str(seconds), "-P", "8", "-J"]
    log("LOCAL " + " ".join(argv))
    before = net_stats()
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=seconds + 30)
    after = net_stats()
    rec: dict = {
        "group": group,
        "scheme": "iperf-tcp",
        "rc": proc.returncode,
        "bind": bind,
        "dest": dest,
    }
    rec["stdout"] = (proc.stdout or "")[-2500:]
    rec["stderr"] = (proc.stderr or "")[-1000:]
    try:
        bps = _iperf_bps(json.loads(proc.stdout))
        rec["gbps"] = bps / 1e9
        rec["gbs"] = bps / 8e9
        rec["ok"] = rec["gbs"] >= 0.5
    except Exception as e:
        rec["ok"] = False
        rec["error"] = str(e)
        rec["gbs"] = 0.0
        rec["gbps"] = 0.0
    d = delta_stats(before, after)
    rec["eth_tx_gb"] = eth_gb(d)
    rec["ib_xmit_gb"] = ib_gb(d)
    rec["nic_delta"] = d
    return rec


def manytoone(rail: str, tgt_host: str, init_hosts: list[str]) -> dict:
    group = f"m2o-{short(tgt_host)}"
    rv_delete(f"/k/{group}")
    inits = ",".join(f"init-{short(h)}" for h in init_hosts)
    tspec = target_spec(group, rail, tgt_host, "manytoone", inits)
    local = None
    acks = []
    if is_hub(tgt_host):
        local = run_local(tspec)
    else:
        acks.append((tgt_host, post_cmd(tgt_host, tspec)))
    time.sleep(1.5)
    names = []
    for h in init_hosts:
        spec = initiator_spec(group, rail, h, "pairwise", tgt_ep(tgt_host))
        names.append(spec["name"])
        if is_hub(h):
            raise RuntimeError("hub initiator + remote target m2o not wired; pick hub as target")
        acks.append((h, post_cmd(h, spec)))
    recs = {n: wait_result(group, n, timeout_s=240) for n in names}
    if local:
        local.wait(timeout=60)
    for host, n in acks:
        try:
            wait_ack(host, n, timeout_s=60)
        except Exception as e:
            log(f"ack {host}/{n}: {e}")
    rec = {"group": group, "rail": rail, "scheme": "manytoone", **recs}
    rec["gbs"] = sum(r.get("gbs") or 0 for r in recs.values())
    rec["gbps"] = rec["gbs"] * 8
    save(group, rec)
    return rec


def onetomany(rail: str, init_host: str, tgt_hosts: list[str]) -> dict:
    group = f"o2m-{short(init_host)}"
    rv_delete(f"/k/{group}")
    acks = []
    for t in tgt_hosts:
        spec = target_spec(group, rail, t, "onetomany", f"init-{short(init_host)}")
        if is_hub(t):
            raise RuntimeError("hub as o2m target not wired; pick hub as initiator")
        acks.append((t, post_cmd(t, spec)))
    time.sleep(2.0)
    ispec = initiator_spec(
        group, rail, init_host, "onetomany", ",".join(tgt_ep(t) for t in tgt_hosts)
    )
    local = None
    if is_hub(init_host):
        local = run_local(ispec)
    else:
        acks.append((init_host, post_cmd(init_host, ispec)))
    rec = wait_result(group, ispec["name"], timeout_s=240)
    if local:
        local.wait(timeout=60)
    for host, n in acks:
        try:
            wait_ack(host, n, timeout_s=60)
        except Exception as e:
            log(f"ack {host}/{n}: {e}")
    rec.setdefault("group", group)
    save(group, rec)
    return rec


def summarize(rows: list[dict]) -> None:
    lines = ["group,scheme,rail,gbs,gbps,host"]
    for rec in rows:
        gbs = rec.get("gbs")
        if gbs is None and any(k.startswith("init-") for k in rec):
            gbs = sum((rec[k].get("gbs") or 0) for k in rec if k.startswith("init-"))
        lines.append(
            f"{rec.get('group')},{rec.get('scheme', rec.get('role'))},"
            f"{rec.get('rail')},{gbs},{rec.get('gbps')},{rec.get('host')}"
        )
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "summary.csv").write_text("\n".join(lines) + "\n")
    log("summary:\n" + "\n".join(lines))
    _write_score(rows)


def _write_score(rows: list[dict]) -> None:
    cap = float(os.environ.get("CAP_GBS", "12.5"))
    profile = os.environ.get("PROFILE", "aws-g7e")
    lines = [
        f"# Score vs CAP_GBS={cap} PROFILE={profile}",
        "",
        "| group | scheme | GB/s | vs cap | notes |",
        "|---|---|---:|---:|---|",
    ]
    for rec in rows:
        gbs = rec.get("gbs")
        if gbs is None and any(isinstance(rec.get(k), dict) and k.startswith("init-") for k in rec):
            gbs = sum((rec[k].get("gbs") or 0) for k in rec if k.startswith("init-"))
        try:
            gbs_f = float(gbs) if gbs is not None else None
        except (TypeError, ValueError):
            gbs_f = None
        pct = (100.0 * gbs_f / cap) if gbs_f is not None and cap else 0.0
        err = rec.get("error", "")
        lines.append(
            f"| {rec.get('group')} | {rec.get('scheme', rec.get('role'))} | "
            f"{gbs_f if gbs_f is not None else ''} | {pct:.0f}% | {err} |"
        )
    path = RESULTS / "SCORE.md"
    path.write_text("\n".join(lines) + "\n")
    log(f"wrote {path}")


def spark_jobs(hnames: list[str]) -> None:
    if len(hnames) < 3:
        raise SystemExit("spark profile needs 3 hosts (zeno-01,02,03)")
    a, b, c = hnames[0], hnames[1], hnames[2]
    rows = []
    jobs = [
        ("p12-f0", "f0", a, b),
        ("p12-f1", "f1", a, b),
        ("p12-dual", "dual", a, b),
        ("p13-f0", "f0", c, a),
        ("p13-f1", "f1", c, a),
        ("p13-dual", "dual", c, a),
        ("p23-f0", "f0", c, b),
        ("p23-f1", "f1", c, b),
        ("p23-dual", "dual", c, b),
    ]
    for group, rail, tgt, init in jobs:
        log(f"==== {group} {tgt}->{init} rail={rail} ====")
        try:
            rec = pairwise(group, rail, tgt, init)
            rows.append(rec)
            log(f"{group} {rec.get('gbs')} GB/s")
        except Exception as e:
            err = {"group": group, "rail": rail, "error": str(e)}
            rows.append(err)
            save(group, err)
            log(f"{group} FAILED {e}")
        time.sleep(1.0)
    log("==== m2o ====")
    try:
        rows.append(manytoone("dual", b, [a, c]))
    except Exception as e:
        save("m2o", {"error": str(e)})
        log(f"m2o FAILED {e}")
    log("==== o2m ====")
    try:
        rows.append(onetomany("dual", b, [a, c]))
    except Exception as e:
        save("o2m", {"error": str(e)})
        log(f"o2m FAILED {e}")
    summarize(rows)


def aws_jobs(hnames: list[str]) -> None:
    hub = hub_name()
    others = [h for h in hnames if h != hub]
    rail = os.environ.get("RAIL", "efa")
    rows = []
    log("==== iperf TCP hub -> each peer ====")
    for peer in others:
        try:
            rec = iperf_pair(hub, peer)
            rows.append(rec)
            log(f"iperf {hub}->{peer} {rec.get('gbs')} GB/s")
        except Exception as e:
            err = {"group": f"iperf-{short(hub)}-{short(peer)}", "error": str(e)}
            rows.append(err)
            save(err["group"], err)
            log(f"iperf {peer} FAILED {e}")
    for peer in others:
        group = f"p-{short(hub)}-{short(peer)}"
        log(f"==== NIXL WRITE {hub}->{peer} ====")
        try:
            rec = pairwise(group, rail, peer, hub)
            rows.append(rec)
            log(f"{group} {rec.get('gbs')} GB/s")
        except Exception as e:
            err = {"group": group, "error": str(e)}
            rows.append(err)
            save(group, err)
            log(f"{group} FAILED {e}")
    if len(others) >= 2:
        log("==== m2o into hub ====")
        try:
            rows.append(manytoone(rail, hub, others))
        except Exception as e:
            save("m2o", {"error": str(e)})
            log(f"m2o FAILED {e}")
        log("==== o2m from hub ====")
        try:
            rows.append(onetomany(rail, hub, others))
        except Exception as e:
            save("o2m", {"error": str(e)})
            log(f"o2m FAILED {e}")
    summarize(rows)


def main():
    inv = os.environ.get("INVENTORY", "")
    if inv:
        apply_env(inv)
        global RV
        RV = os.environ.get("NIXL_RV", RV)
    RESULTS.mkdir(parents=True, exist_ok=True)
    h = list(hosts())
    hub = hub_name()
    remote = [n for n in h if n != hub]
    wait_workers(remote)
    profile = os.environ.get("PROFILE", "aws-g7e")
    log(f"profile={profile} hub={hub} hosts={h} backend={os.environ.get('NIXL_BACKEND')} cap={os.environ.get('CAP_GBS')} GB/s")
    if profile == "spark-zeno":
        spark_jobs(h)
    else:
        aws_jobs(h)
    for name in remote:
        rv_put(f"/k/cmd/{name}/{SEQ.get(name, 0)}", b"STOP")
    log("posted STOP")


if __name__ == "__main__":
    main()
