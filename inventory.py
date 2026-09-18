#!/usr/bin/env python3
"""Load a KEY=value inventory file (see inventory.example.env)."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path) -> dict[str, str]:
    out: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def apply_env(path: str | Path) -> dict[str, str]:
    vals = load_env_file(path)
    for k, v in vals.items():
        os.environ.setdefault(k, v)
    return vals


def parse_hosts(spec: str | None = None) -> dict[str, dict]:
    """HOSTS=name:ip:port,name:ip:port"""
    spec = spec or os.environ.get("HOSTS", "")
    hosts = {}
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        name, ip, port = item.split(":")
        hosts[name] = {"name": name, "ip": ip, "port": int(port)}
    if not hosts:
        raise SystemExit("HOSTS is empty; set inventory (see inventory.example.env)")
    return hosts


def hub_name() -> str:
    return os.environ.get("HUB", next(iter(parse_hosts())))


def repo_root() -> Path:
    return Path(os.environ.get("NIXL_BENCH_ROOT", Path(__file__).resolve().parent))
