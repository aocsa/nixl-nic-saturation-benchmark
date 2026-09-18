# Spark zeno-01/02/03 (original cluster)

Three NVIDIA DGX Spark nodes, ConnectX-7 **multi-host** twins: **4 OS netdevs**, **2× 200G QSFP**.

## Addressing

Management (1G, control plane):

| Host | mgmt |
|---|---|
| zeno-01 | 10.87.131.181 |
| zeno-02 | 10.87.131.182 (hub) |
| zeno-03 | 10.87.131.183 |

Rail **f0** (one 200G QSFP, two PFs) and **f1** (the other cage):

| Host | f0 twins | f1 twins |
|---|---|---|
| zeno-01 | .64 / .66 | .65 / .67 |
| zeno-02 | .68 / .70 | .69 / .71 |
| zeno-03 | .72 / .74 | .73 / .75 |

UCX device lists (do **not** pin GID index; zeno-03 f0 RoCEv2 IPv4 is index 4, others 3):

```
RAIL_F0=rocep1s0f0:1,roceP2p1s0f0:1
RAIL_F1=rocep1s0f1:1,roceP2p1s0f1:1
RAIL_DUAL= all four :1
UCX_TLS=rc,ud,sm,self          # never tcp on the data path
UCX_IB_ROCE_REACHABILITY_MODE=all
```

Netdev map: `rocep1s0f0` → `enp1s0f0np0`, `roceP2p1s0f0` → `enP2p1s0f0np0`, same for f1.

## What ran

NIXL Python 1.4.1, UCX plugin, DRAM WRITE, 16 MiB × batch 8, 50 warmup + 200 timed iters. Control plane HTTP `http://10.87.131.182:8766`.

Calibration: `ib_write_bw` 02→01 both f0 twins in parallel ≈ **195.98 Gb/s = 24.50 GB/s**.

Pairwise: all six f0/f1 runs **24.42–24.44 GB/s** (PASS 200G QSFP). Dual-rail striped all four PFs equally but stayed ~24 GB/s (UCX multi-rail shortfall vs 31.5 host PCIe).

Three-node dual-rail: m2o into 02 ≈ **21.84 GB/s**; o2m from 02 **26.20 GB/s** (only dual-rail case clearly above one QSFP).

Full tables: [`results/spark-zeno/nixl/RESULTS.md`](../results/spark-zeno/nixl/RESULTS.md).

## Flight (TCP) comparison

Arrow Flight DoPut, gRPC/TCP (Flight UCX removed, [GH-43296](https://github.com/apache/arrow/issues/43296)). Rail-f0 only. Source bind via `LD_PRELOAD` `flight/bind_connect.c` (`AF_INET` + `AF_INET6 ::ffff:` + `SO_BINDTODEVICE`).

| Scheme | NIXL GB/s | Flight GB/s | iperf |
|---|---:|---:|---|
| one-to-one | 24.44 (p12-f0) | 13.34 | one twin 13.88; both 21.80 |
| one-to-many | 26.20 (dual) | 21.59 | matches both-twin TCP |
| many-to-one | 21.84 (dual) | 13.84 | one `perf_server` |

NIXL is faster because RDMA writes into **registered DRAM**; Flight copies through gRPC/TCP. o2m Flight ≈ iperf because it uses two destination hosts (two servers). Binaries are **not** in git (`dist.tgz` was ~22 MB). Source: [`flight/`](../flight/).

## Replay

```bash
cp profiles/spark-zeno.env inventory.env
# zeno-02
./scripts/start-control-plane.sh
./run.sh
# zeno-01 / 03
./start-worker.sh zeno-01
```

`PROFILE=spark-zeno` selects `spark_jobs()` in `coord.py`. Jumbo MTU on CX-7 data IPs is assumed.
