# Arrow Flight DoPut vs NIXL — Phase 1 rail-f0

Date: 2026-09-18. Hub: zeno-02. Nodes: zeno-01 / zeno-02 / zeno-03.
Harness: `/home/aocsa/git/flight-bench` wrapping stock `arrow-flight-benchmark` / `arrow-flight-perf-server` (gRPC/TCP). Flight UCX was removed ([GH-43296](https://github.com/apache/arrow/issues/43296)).
Control plane: HTTP rendezvous `http://10.87.131.182:8776` (not NIXL `:8766`). Data plane: CX-7 TCP only.
Payload: DoPut, 65536 rec/batch (2 MiB), 67108864 rec/stream (~2 GiB), 8 streams × 8 threads, two client processes per QSFP. GB/s is SI (`bytes / 1e9 / s`) converted from Flight’s MiB/s (`bytes / 2^20 / s`).

TCP does not increment IB `port_xmit_data` (those counters are RDMA). Twin split is from sysfs `tx_bytes`.

Caps (same as NIXL): one twin **12.5 GB/s** · one 200G QSFP **25.0 GB/s** · host PCIe **31.5 GB/s**. Phase 1 is rail-f0 only, so the scheme cap is **25.0**. NIXL DRAM WRITE p12-f0 was **24.44 GB/s**.

## Calibration (iperf3, 01–02, jumbo, f0)

| Flow | Bind → dest | App GB/s | Eth tx (10 s) | Twin split |
|---|---|---:|---|---|
| one f0 twin | `.68` → `.64` | **13.88** (111.0 Gbps) | 139.8 GB on `enp1s0f0np0` | sibling `enP2p1s0f0np0` idle |
| both f0 twins | `.68→.64` + `.70→.66` | **21.80** (174.4 Gbps) | 137.6 + 82.1 GB | **both PFs** |

One PF with the sibling idle can take **more than 100 Gbps** of the shared 200G QSFP (ethtool advertises 200G per netdev). That is why the single-twin iperf sits at 13.88 GB/s instead of 12.5. It is not a units error (~50 / ~100 GB/s never appeared).

Both twins in parallel: **13.65 + 8.15 = 21.80 GB/s**. Short of NIXL’s 24.5 GB/s `ib_write_bw` and the 23–24 GB/s TCP goal; iperf CPU was already saturated (`host_system` ~120%, `remote_system` ~330%). Flight cannot beat this TCP ceiling.

## Phase 1 DoPut (rail-f0, two clients per QSFP)

| Group | Scheme | GB/s | Gbps | vs 25.0 | f0 `tx_bytes` split | Verdict |
|---|---|---:|---:|---|---|---|
| o2o-f0 | 02→01 | **13.34** | 106.7 | 53% | 17.46 + 17.45 GB | both twins; **gRPC/CPU**, not one-PF |
| o2m-f0 | 02→01+03 | **21.59** | 172.7 | 86% | 34.70 + 34.69 GB | matches iperf both-twins |
| m2o-f0 | 01+03→02 | **13.84** | 110.7 | 55% | 01: 17.50+17.49; 03: 17.49+17.49 | two sources, one server process |

Source bind (`LD_PRELOAD` `connect()` for AF_INET and AF_INET6 `::ffff:` plus `BIND_DEV`) is working: every Flight run moved ~equal bytes on `enp1s0f0np0` and `enP2p1s0f0np0`. A first pass without IPv6 bind stuffed both clients onto one PF (~6.6 GB/s) and is discarded.

### Per-process DoPut (SI GB/s)

- o2o: 6.91 (`.68→.64`) + 6.43 (`.70→.66`)
- o2m: 5.73 + 5.16 (→01) and 5.46 + 5.24 (→03)
- m2o: 01 3.52+3.46; 03 3.40+3.46 (into `.68` / `.70`)

## Score vs 12.5 / 25.0 / 31.5

| Pattern | Meaning | Observed |
|---|---|---|
| ~12 GB/s on a “both twins” run | only one PF (bind/route bug) | **not** on the scored run; both PFs busy |
| 23–24 GB/s on f0 | 200G QSFP saturated | **not** reached. TCP iperf 21.80; Flight o2m 21.59 |
| 5–15 GB/s with both PFs busy | protocol/CPU limit | **o2o 13.34** and **m2o 13.84** — gRPC copies + one `perf_server` |
| ~50 / ~100 GB/s | MiB vs MB vs GB error | **not seen** (Flight MiB/s converted via bytes/nanos) |

NIXL comparison (WRITE, DRAM, UCX). NIXL 3-node runs were **dual-rail**; Phase 1 Flight is **rail-f0 only**.

| Scheme | NIXL GB/s | Flight GB/s | Cap used |
|---|---:|---:|---|
| one-to-one | 24.44 (p12-f0) | 13.34 | 25.0 one QSFP |
| one-to-many | 26.20 (o2m-i02 dual) | 21.59 | 25.0 Phase 1 / 31.5 NIXL dual |
| many-to-one | 21.84 (m2o-t02 dual) | 13.84 | 25.0 Phase 1 / 31.5 NIXL dual |

gRPC DoPut on this GB10/CX-7 path is a **protocol/CPU result**, not a fabric fail: iperf already tops out near 22 GB/s on f0, one-to-one Flight is ~13 GB/s even with both twins pinned, and one-to-many Flight rides the TCP ceiling because it has two destination hosts.

Phase 2 (f1 / dual / other pairs) is out of scope until this rail-f0 matrix is accepted.

JSON: `iperf-f0a.json`, `iperf-f0-both.json`, `o2o-f0.json`, `o2m-f0.json`, `m2o-f0.json`, `summary.csv`. Log: `coord-rerun.log`.
