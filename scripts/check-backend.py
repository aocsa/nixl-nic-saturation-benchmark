#!/usr/bin/env python3
"""Create a throwaway NIXL agent to confirm the requested backend loads."""

from __future__ import annotations

import os
import socket
import sys

backend = os.environ.get("NIXL_BACKEND", "LIBFABRIC").upper()
port = int(os.environ.get("NIXL_LISTEN_PORT", "5999"))
try:
    from nixl import nixl_agent, nixl_agent_config
except Exception as e:
    print("import nixl failed:", e)
    sys.exit(2)
cfg = nixl_agent_config(True, True, port, backends=[backend], num_threads=1)
name = f"probe-{socket.gethostname()}"
agent = nixl_agent(name, cfg)
print(f"ok agent={name} backend={backend} host={socket.gethostname()}")
print("FI_PROVIDER", os.environ.get("FI_PROVIDER", ""))
print("UCX_TLS", os.environ.get("UCX_TLS", ""))
print("UCX_NET_DEVICES", os.environ.get("UCX_NET_DEVICES", ""))
