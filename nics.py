#!/usr/bin/env python3
"""Discover IB/RoCE/EFA devices and matching netdevs. Spark CX-7 names are a fallback."""

from __future__ import annotations

from pathlib import Path

SPARK_NICS = [
    ("rocep1s0f0", "enp1s0f0np0"),
    ("rocep1s0f1", "enp1s0f1np1"),
    ("roceP2p1s0f0", "enP2p1s0f0np0"),
    ("roceP2p1s0f1", "enP2p1s0f1np1"),
]


def ib_to_netdev(ib: str) -> str | None:
    netdir = Path(f"/sys/class/infiniband/{ib}/device/net")
    if netdir.is_dir():
        names = sorted(p.name for p in netdir.iterdir())
        if names:
            return names[0]
    return None


SKIP_NET = {
    "lo",
    "docker0",
    "virbr0",
    "cni0",
    "flannel.1",
    "tunl0",
}


def discover_nics() -> list[tuple[str, str]]:
    ib_root = Path("/sys/class/infiniband")
    pairs: list[tuple[str, str]] = []
    if ib_root.is_dir():
        for ib_path in sorted(ib_root.iterdir()):
            ib = ib_path.name
            eth = ib_to_netdev(ib) or ib
            pairs.append((ib, eth))
    if pairs:
        return pairs
    existing = [(ib, eth) for ib, eth in SPARK_NICS if Path(f"/sys/class/net/{eth}").exists()]
    return existing or list(SPARK_NICS)


def discover_eth_names() -> list[str]:
    """ENA / CX-7 / other netdevs, including those with no IB sysfs (TCP iperf)."""
    net = Path("/sys/class/net")
    if not net.is_dir():
        return []
    names = []
    for p in sorted(net.iterdir()):
        n = p.name
        if n in SKIP_NET or n.startswith(("veth", "br-", "docker", "cni", "flannel")):
            continue
        names.append(n)
    return names


def _eth_bytes(eth: str, rec: dict) -> None:
    tx = Path(f"/sys/class/net/{eth}/statistics/tx_bytes")
    rx = Path(f"/sys/class/net/{eth}/statistics/rx_bytes")
    if tx.exists():
        rec["tx_bytes"] = int(tx.read_text())
        rec["rx_bytes"] = int(rx.read_text())


def net_stats(nics: list[tuple[str, str]] | None = None) -> dict:
    nics = nics or discover_nics()
    out: dict = {}
    for ib, eth in nics:
        rec: dict = {"ib": ib}
        _eth_bytes(eth, rec)
        xmit = Path(f"/sys/class/infiniband/{ib}/ports/1/counters/port_xmit_data")
        rcv = Path(f"/sys/class/infiniband/{ib}/ports/1/counters/port_rcv_data")
        if xmit.exists():
            rec["port_xmit_data"] = int(xmit.read_text())
            rec["port_rcv_data"] = int(rcv.read_text())
        hw = Path(f"/sys/class/infiniband/{ib}/hw_counters/rdma_write_bytes")
        if hw.exists():
            rec["rdma_write_bytes"] = int(hw.read_text())
        out[eth] = rec
    for eth in discover_eth_names():
        if eth in out:
            continue
        rec = {"ib": None}
        _eth_bytes(eth, rec)
        if "tx_bytes" in rec:
            out[eth] = rec
    return out


def delta_stats(before: dict, after: dict) -> dict:
    d = {}
    for nic, b in before.items():
        a = after.get(nic, {})
        keys = (set(b) | set(a)) - {"ib"}
        rec = {k: (a.get(k, 0) or 0) - (b.get(k, 0) or 0) for k in keys}
        rec["ib"] = a.get("ib") or b.get("ib")
        d[nic] = rec
    return d


def ib_gb(delta: dict, key: str = "port_xmit_data") -> dict:
    """IB port_*_data counters are 4-byte words. TCP often leaves them at 0."""
    return {nic: rec.get(key, 0) * 4 / 1e9 for nic, rec in delta.items()}


def eth_gb(delta: dict, key: str = "tx_bytes") -> dict:
    return {nic: rec.get(key, 0) / 1e9 for nic, rec in delta.items()}
