#!/usr/bin/env python3
"""DRAM NIXL WRITE saturation: pairwise / many-to-one / one-to-many.

Control plane: HTTP rendezvous (metadata + xfer descs).
Data plane: NIXL backend from NIXL_BACKEND (UCX on Spark RoCE, LIBFABRIC on AWS EFA).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

import numpy as np
from nixl import nixl_agent, nixl_agent_config

from nics import delta_stats, net_stats

RV = os.environ.get("NIXL_RV", "http://127.0.0.1:8766")


def log(msg: str) -> None:
    print(f"# {time.strftime('%H:%M:%S')} {msg}", flush=True)


def emit(obj) -> None:
    print(json.dumps(obj, sort_keys=True), flush=True)


def rv_put(key: str, data: bytes) -> None:
    req = urllib.request.Request(RV + key, data=data, method="PUT")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def rv_get(key: str, timeout_s: float = 180.0) -> bytes:
    url = f"{RV}{key}?wait={int(timeout_s)}"
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=timeout_s + 5) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code != 404:
                raise
            time.sleep(0.25)
        except Exception as e:
            last = e
            time.sleep(0.25)
    raise TimeoutError(f"rendezvous miss {key}: {last}")


def wait_done(agent, handle, timeout_s=180.0):
    t0 = time.time()
    while True:
        st = agent.check_xfer_state(handle)
        if st == "DONE":
            return
        if st == "ERR":
            raise RuntimeError("transfer ERR")
        if time.time() - t0 > timeout_s:
            raise TimeoutError("transfer timeout")


def timed_writes(agent, handle, iters, warmup):
    for _ in range(warmup):
        st = agent.transfer(handle)
        if st == "ERR":
            raise RuntimeError("warmup post failed")
        if st != "DONE":
            wait_done(agent, handle)
    t0 = time.perf_counter()
    for _ in range(iters):
        st = agent.transfer(handle)
        if st == "ERR":
            raise RuntimeError("timed post failed")
        if st != "DONE":
            wait_done(agent, handle)
    return time.perf_counter() - t0


def make_registered(agent, nbytes: int, batch: int):
    buf = np.zeros(nbytes, dtype=np.uint8)
    addr = int(buf.ctypes.data)
    block = nbytes // batch
    tuples_xfer = [(addr + i * block, block, 0) for i in range(batch)]
    tuples_reg = [(addr + i * block, block, 0, f"b{i}") for i in range(batch)]
    reg = agent.register_memory(tuples_reg, mem_type="DRAM")
    if not reg:
        raise RuntimeError("register_memory failed")
    xfer = agent.get_xfer_descs(tuples_xfer, mem_type="DRAM")
    if not xfer:
        raise RuntimeError("get_xfer_descs failed")
    return buf, reg, xfer


def backend_name() -> str:
    return os.environ.get("NIXL_BACKEND", "UCX").upper()


def make_agent(name: str, listen_port: int):
    backend = backend_name()
    config = nixl_agent_config(
        True, True, listen_port, backends=[backend], num_threads=4
    )
    agent = nixl_agent(name, config)
    log(f"agent {name} listen={listen_port} host={socket.gethostname()} backend={backend}")
    return agent


def publish_md(agent, group: str, name: str) -> None:
    md = agent.get_agent_metadata()
    rv_put(f"/k/{group}/md/{name}", md)
    log(f"published md {name} {len(md)}B")


def load_md(agent, group: str, name: str) -> str:
    md = rv_get(f"/k/{group}/md/{name}")
    remote = agent.add_remote_agent(md)
    log(f"loaded md {name} -> {remote}")
    return remote


def parse_targets(spec: str):
    peers = []
    for item in spec.split(","):
        if not item:
            continue
        name, rest = item.split("@", 1)
        ip, port = rest.split(":")
        peers.append((name, ip, int(port)))
    return peers


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--role", choices=["target", "initiator"], required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--scheme", choices=["pairwise", "manytoone", "onetomany"], default="pairwise")
    p.add_argument("--listen-port", type=int, default=5555)
    p.add_argument("--initiators", default="", help="comma names expected by target")
    p.add_argument("--targets", default="", help="name@ip:port,... for initiator")
    p.add_argument("--block-size", type=int, default=16 * 1024 * 1024)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--iters", type=int, default=200)
    p.add_argument("--warmup", type=int, default=50)
    p.add_argument("--group", default="default")
    p.add_argument("--rail", default="")
    return p.parse_args()


def run_target(args):
    agent = make_agent(args.name, args.listen_port)
    print(
        f"LISTENING name={args.name} port={args.listen_port} host={socket.gethostname()}",
        flush=True,
    )
    total = args.block_size * args.batch
    names = [n for n in args.initiators.split(",") if n] or ["initiator"]
    bufs, regs, xfer_descs = [], [], []
    for _ in names:
        b, r, x = make_registered(agent, total, args.batch)
        bufs.append(b)
        regs.append(r)
        xfer_descs.append(x)
    log(f"registered {len(names)} x {total}B")
    publish_md(agent, args.group, args.name)
    for i, n in enumerate(names):
        ser = agent.get_serialized_descs(xfer_descs[i])
        rv_put(f"/k/{args.group}/descs/{args.name}/{n}", ser)
        log(f"published descs for {n} {len(ser)}B")
    for n in names:
        load_md(agent, args.group, n)
        try:
            agent.make_connection(n)
        except Exception as e:
            log(f"make_connection {n}: {e}")
    rv_put(f"/k/{args.group}/ready/{args.name}", b"1")
    before = net_stats()
    t0 = time.perf_counter()
    for n in names:
        rv_get(f"/k/{args.group}/done/{n}", timeout_s=400)
        log(f"rendezvous DONE {n}")
    wall = time.perf_counter() - t0
    after = net_stats()
    rec = {
        "role": "target",
        "name": args.name,
        "scheme": args.scheme,
        "group": args.group,
        "rail": args.rail,
        "backend": backend_name(),
        "host": socket.gethostname(),
        "ucx_net_devices": os.environ.get("UCX_NET_DEVICES", ""),
        "ucx_tls": os.environ.get("UCX_TLS", ""),
        "fi_provider": os.environ.get("FI_PROVIDER", ""),
        "wait_s": wall,
        "nic_delta": delta_stats(before, after),
    }
    emit(rec)
    rv_put(f"/k/{args.group}/result/{args.name}", json.dumps(rec).encode())
    for r in regs:
        agent.deregister_memory(r)


def run_initiator(args, peers: list[tuple[str, str, int]]):
    agent = make_agent(args.name, args.listen_port)
    total = args.block_size * args.batch
    buf, reg, local_descs = make_registered(agent, total, args.batch)
    log(f"registered {total}B batch={args.batch}")
    publish_md(agent, args.group, args.name)

    handles = []
    for name, _ip, _port in peers:
        load_md(agent, args.group, name)
        ser = rv_get(f"/k/{args.group}/descs/{name}/{args.name}")
        remote_descs = agent.deserialize_descs(ser)
        try:
            agent.make_connection(name)
        except Exception as e:
            log(f"make_connection {name}: {e}")
        h = agent.initialize_xfer("WRITE", local_descs, remote_descs, name, b"")
        if not h:
            raise RuntimeError(f"initialize_xfer failed for {name}")
        handles.append((name, h))
        log(f"xfer handle ready for {name}")

    rv_put(f"/k/{args.group}/ready/{args.name}", b"1")
    for name, _, _ in peers:
        rv_get(f"/k/{args.group}/ready/{name}")
        log(f"peer ready {name}")

    before = net_stats()
    if len(handles) == 1:
        elapsed = timed_writes(agent, handles[0][1], args.iters, args.warmup)
        npeers = 1
    else:
        for _ in range(args.warmup):
            for _, h in handles:
                st = agent.transfer(h)
                if st == "ERR":
                    raise RuntimeError("warmup post failed")
            for _, h in handles:
                wait_done(agent, h)
        t0 = time.perf_counter()
        for _ in range(args.iters):
            for _, h in handles:
                st = agent.transfer(h)
                if st == "ERR":
                    raise RuntimeError("timed post failed")
            for _, h in handles:
                wait_done(agent, h)
        elapsed = time.perf_counter() - t0
        npeers = len(handles)
    after = net_stats()
    gb = (total * args.iters * npeers) / 1e9
    gbs = gb / elapsed
    for name, h in handles:
        try:
            h.release()
        except Exception:
            pass
        rv_put(f"/k/{args.group}/done/{args.name}", b"1")
        try:
            agent.remove_remote_agent(name)
        except Exception:
            pass
    rec = {
        "role": "initiator",
        "name": args.name,
        "scheme": args.scheme,
        "group": args.group,
        "rail": args.rail,
        "backend": backend_name(),
        "host": socket.gethostname(),
        "ucx_net_devices": os.environ.get("UCX_NET_DEVICES", ""),
        "ucx_tls": os.environ.get("UCX_TLS", ""),
        "fi_provider": os.environ.get("FI_PROVIDER", ""),
        "peers": [n for n, _, _ in peers],
        "block_size": args.block_size,
        "batch": args.batch,
        "iters": args.iters,
        "elapsed_s": elapsed,
        "gb_moved": gb,
        "gbs": gbs,
        "gbps": gbs * 8,
        "nic_delta": delta_stats(before, after),
    }
    emit(rec)
    rv_put(f"/k/{args.group}/result/{args.name}", json.dumps(rec).encode())
    agent.deregister_memory(reg)


def main():
    args = parse_args()
    log(
        f"role={args.role} name={args.name} scheme={args.scheme} "
        f"group={args.group} rail={args.rail} backend={backend_name()} "
        f"UCX_NET_DEVICES={os.environ.get('UCX_NET_DEVICES','')} "
        f"UCX_MAX_RMA_RAILS={os.environ.get('UCX_MAX_RMA_RAILS','')}"
    )
    if args.role == "target":
        if args.scheme == "pairwise":
            args.initiators = args.initiators or "initiator"
        run_target(args)
        return
    peers = parse_targets(args.targets)
    if not peers:
        raise SystemExit("initiator requires --targets name@ip:port")
    run_initiator(args, peers)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        rec = {"error": str(e), "host": socket.gethostname(), "role": sys.argv}
        emit(rec)
        group = "unknown"
        name = "unknown"
        if "--group" in sys.argv:
            group = sys.argv[sys.argv.index("--group") + 1]
        if "--name" in sys.argv:
            name = sys.argv[sys.argv.index("--name") + 1]
        try:
            rv_put(f"/k/{group}/result/{name}", json.dumps(rec).encode())
            rv_put(f"/k/{group}/done/{name}", b"1")
        except Exception:
            pass
        raise
