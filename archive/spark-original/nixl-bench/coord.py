#!/usr/bin/env python3
"""Drive the 9 pairwise + 2 three-node DRAM NIXL saturation jobs from zeno-02."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

RV = os.environ.get("NIXL_RV", "http://10.87.131.182:8766")
ROOT = Path("/home/aocsa/git/nixl-bench")
RESULTS = ROOT / "results"
PYTHON = "python3"

HOSTS = {
    "zeno-01": {
        "mgmt": "10.87.131.181",
        "port": 5551,
        "cmd": "zeno-01",
    },
    "zeno-02": {
        "mgmt": "10.87.131.182",
        "port": 5552,
        "cmd": None,
    },
    "zeno-03": {
        "mgmt": "10.87.131.183",
        "port": 5553,
        "cmd": "zeno-03",
    },
}

RAILS = {
    "f0": ("rocep1s0f0:1,roceP2p1s0f0:1", "2"),
    "f1": ("rocep1s0f1:1,roceP2p1s0f1:1", "2"),
    "dual": (
        "rocep1s0f0:1,roceP2p1s0f0:1,rocep1s0f1:1,roceP2p1s0f1:1",
        "4",
    ),
}

SAT_FLAGS = [
    "--block-size",
    "16777216",
    "--batch",
    "8",
    "--iters",
    "200",
    "--warmup",
    "50",
]


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


SEQ = {
    "zeno-01": int(os.environ.get("COORD_SEQ_01", "0")),
    "zeno-03": int(os.environ.get("COORD_SEQ_03", "0")),
}


def post_cmd(host: str, spec: dict) -> int:
    n = SEQ[host]
    SEQ[host] = n + 1
    rv_put(f"/k/cmd/{host}/{n}", json.dumps(spec).encode())
    log(f"posted {host}/{n} {spec['group']} {spec['role']}")
    return n


def wait_ack(host: str, n: int, timeout_s: float = 240.0) -> str:
    raw = rv_get(f"/k/ack/{host}/{n}", timeout_s=timeout_s)
    return raw.decode()


def wait_result(group: str, name: str, timeout_s: float = 240.0) -> dict:
    raw = rv_get(f"/k/{group}/result/{name}", timeout_s=timeout_s)
    return json.loads(raw)


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


def local_env(rail: str) -> dict:
    devices, rails = RAILS[rail]
    env = os.environ.copy()
    env["UCX_TLS"] = "rc,ud,sm,self"
    env["UCX_IB_ROCE_REACHABILITY_MODE"] = "all"
    env["UCX_WARN_UNUSED_ENV_VARS"] = "n"
    env["UCX_NET_DEVICES"] = devices
    env["UCX_MAX_RMA_RAILS"] = rails
    env["NIXL_RV"] = RV
    env["PYTHONPATH"] = (
        str(Path.home() / ".local/lib/python3.12/site-packages")
        + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    )
    return env


def run_local(spec: dict) -> subprocess.Popen:
    kill_local_sat()
    time.sleep(0.2)
    argv = [PYTHON, "-u", str(ROOT / "sat.py"), "--rail", spec["rail"]] + spec["args"]
    log("LOCAL " + " ".join(argv))
    return subprocess.Popen(argv, env=local_env(spec["rail"]))


def target_spec(group, rail, host, scheme, initiators):
    h = HOSTS[host]
    name = f"tgt-{host[-2:]}"
    args = [
        "--role",
        "target",
        "--name",
        name,
        "--scheme",
        scheme,
        "--initiators",
        initiators,
        "--listen-port",
        str(h["port"]),
        "--group",
        group,
    ] + SAT_FLAGS
    return {
        "group": group,
        "rail": rail,
        "role": "target",
        "host": host,
        "name": name,
        "args": args,
    }


def initiator_spec(group, rail, host, scheme, targets):
    h = HOSTS[host]
    name = f"init-{host[-2:]}"
    args = [
        "--role",
        "initiator",
        "--name",
        name,
        "--scheme",
        scheme,
        "--targets",
        targets,
        "--listen-port",
        str(h["port"]),
        "--group",
        group,
    ] + SAT_FLAGS
    return {
        "group": group,
        "rail": rail,
        "role": "initiator",
        "host": host,
        "name": name,
        "args": args,
    }


def tgt_ep(host: str) -> str:
    h = HOSTS[host]
    return f"tgt-{host[-2:]}@{h['mgmt']}:{h['port']}"


def save(group: str, rec: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{group}.json"
    path.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    log(f"saved {path}")


def pairwise(group: str, rail: str, tgt_host: str, init_host: str) -> dict:
    rv_delete(f"/k/{group}")
    tspec = target_spec(group, rail, tgt_host, "pairwise", f"init-{init_host[-2:]}")
    ispec = initiator_spec(group, rail, init_host, "pairwise", tgt_ep(tgt_host))
    local_proc = None
    remote_acks = []
    if tgt_host == "zeno-02":
        local_proc = run_local(tspec)
    else:
        remote_acks.append((tgt_host, post_cmd(tgt_host, tspec)))
    time.sleep(1.0)
    if init_host == "zeno-02":
        if local_proc is not None:
            raise RuntimeError("cannot be both")
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
    save(group, rec)
    return rec


def manytoone() -> dict:
    group, rail = "m2o-t02", "dual"
    rv_delete(f"/k/{group}")
    tspec = target_spec(
        group, rail, "zeno-02", "manytoone", "init-01,init-03"
    )
    i1 = initiator_spec(group, rail, "zeno-01", "pairwise", tgt_ep("zeno-02"))
    i3 = initiator_spec(group, rail, "zeno-03", "pairwise", tgt_ep("zeno-02"))
    local = run_local(tspec)
    time.sleep(1.5)
    n1 = post_cmd("zeno-01", i1)
    n3 = post_cmd("zeno-03", i3)
    r1 = wait_result(group, "init-01", timeout_s=240)
    r3 = wait_result(group, "init-03", timeout_s=240)
    local.wait(timeout=60)
    wait_ack("zeno-01", n1, timeout_s=60)
    wait_ack("zeno-03", n3, timeout_s=60)
    rec = {"group": group, "init-01": r1, "init-03": r3}
    save(group, rec)
    return rec


def onetomany() -> dict:
    group, rail = "o2m-i02", "dual"
    rv_delete(f"/k/{group}")
    t1 = target_spec(group, rail, "zeno-01", "onetomany", "init-02")
    t3 = target_spec(group, rail, "zeno-03", "onetomany", "init-02")
    ispec = initiator_spec(
        group,
        rail,
        "zeno-02",
        "onetomany",
        f"{tgt_ep('zeno-01')},{tgt_ep('zeno-03')}",
    )
    n1 = post_cmd("zeno-01", t1)
    n3 = post_cmd("zeno-03", t3)
    time.sleep(2.0)
    local = run_local(ispec)
    rec = wait_result(group, "init-02", timeout_s=240)
    local.wait(timeout=60)
    wait_ack("zeno-01", n1, timeout_s=60)
    wait_ack("zeno-03", n3, timeout_s=60)
    save(group, rec)
    return rec


def summarize(rows: list[dict]) -> None:
    lines = ["group,rail,gbs,gbps,host,ucx_net_devices"]
    for rec in rows:
        if "init-01" in rec:
            for k in ("init-01", "init-03"):
                r = rec[k]
                lines.append(
                    f"{rec['group']},{r.get('rail')},{r.get('gbs')},{r.get('gbps')},{r.get('host')},{r.get('ucx_net_devices')}"
                )
        else:
            lines.append(
                f"{rec.get('group')},{rec.get('rail')},{rec.get('gbs')},{rec.get('gbps')},{rec.get('host')},{rec.get('ucx_net_devices')}"
            )
    (RESULTS / "summary.csv").write_text("\n".join(lines) + "\n")
    log("summary:\n" + "\n".join(lines))


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows = []
    jobs = [
        ("p12-f0", "f0", "zeno-01", "zeno-02"),
        ("p12-f1", "f1", "zeno-01", "zeno-02"),
        ("p12-dual", "dual", "zeno-01", "zeno-02"),
        ("p13-f0", "f0", "zeno-03", "zeno-01"),
        ("p13-f1", "f1", "zeno-03", "zeno-01"),
        ("p13-dual", "dual", "zeno-03", "zeno-01"),
        ("p23-f0", "f0", "zeno-03", "zeno-02"),
        ("p23-f1", "f1", "zeno-03", "zeno-02"),
        ("p23-dual", "dual", "zeno-03", "zeno-02"),
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

    log("==== m2o-t02 ====")
    try:
        rows.append(manytoone())
    except Exception as e:
        save("m2o-t02", {"error": str(e)})
        log(f"m2o FAILED {e}")

    log("==== o2m-i02 ====")
    try:
        rows.append(onetomany())
    except Exception as e:
        save("o2m-i02", {"error": str(e)})
        log(f"o2m FAILED {e}")

    summarize(rows)
    rv_put(f"/k/cmd/zeno-01/{SEQ['zeno-01']}", b"STOP")
    rv_put(f"/k/cmd/zeno-03/{SEQ['zeno-03']}", b"STOP")
    log("posted STOP")


if __name__ == "__main__":
    main()
