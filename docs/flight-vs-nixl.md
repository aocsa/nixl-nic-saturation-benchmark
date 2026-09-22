# Flight DoPut vs NIXL WRITE

Canvas export, expanded with the scored iperf3 numbers and how to rerun the harness.

In this repo the portable harness is the top-level tree (`run.sh`, `profiles/`, `aws/`) plus [`flight/`](../flight/). The scripts that actually produced the 2026-09-17/18 JSON are under [`archive/spark-original/`](../archive/spark-original/). Paths below of the form `/home/aocsa/git/flight-bench` and `/home/aocsa/git/nixl-bench` are the original zeno-02 locations; the same files are in that archive.

Phase 1 rail-f0 · gRPC/TCP · hub zeno-02 · **2026-09-18 00:22 UTC**

SI GB/s on both 100G twins of one 200G QSFP. NIXL pairwise is rail-f0 UCX WRITE; NIXL 3-node bars are dual-rail (their only 3-node runs). Flight is DoPut, two client processes per QSFP.

| | GB/s |
|---|---:|
| Flight 1-to-1 | **13.34** |
| Flight 1-to-many | **21.59** |
| Flight many-to-1 | **13.84** |

**gRPC/CPU, not a bind miss.** After IPv6 source-bind, every Flight run split bytes evenly across `enp1s0f0np0` and `enP2p1s0f0np0`. one-to-one at 13.34 GB/s is both twins busy and still well under the 25.0 GB/s QSFP cap — copies plus one `perf_server`. one-to-many (21.59) matches iperf3 on the same rail (21.80).

Caps (same as NIXL): one twin **12.5 GB/s** · one 200G QSFP **25.0 GB/s** · host PCIe **31.5 GB/s**. Phase 1 is rail-f0 only, so the scheme cap is **25.0**. NIXL DRAM WRITE p12-f0 was **24.44 GB/s**.

## Schemes vs NIXL vs 25.0 GB/s cap

Y axis is SI GB/s. Reference line is one 200G QSFP. NIXL one-to-many / many-to-one used dual-rail and may exceed 25.

| Scheme | NIXL WRITE | Flight DoPut | TCP iperf3 | Cap |
|---|---:|---:|---:|---|
| one-to-one 02→01 | 24.44 f0 | 13.34 | 21.80 both twins | 25.0 |
| one-to-many 02→01+03 | 26.20 dual | 21.59 | — | 25.0 / 31.5 |
| many-to-one 01+03→02 | 21.84 dual | 13.84 | — | 25.0 / 31.5 |

```
GB/s          12.5        25.0              31.5
                |           |                 |
one-to-one  NIXL|===========|==  24.44
            Flight|=====     |    13.34
one-to-many NIXL|===========|====  26.20 dual
            Flight|========= |     21.59
many-to-one NIXL|=========== |     21.84 dual
            Flight|=====     |     13.84
```

Source: `flight-bench/results/*.json` and `nixl-bench` `p12-f0` / `o2m-i02` / `m2o-t02` · 2026-09-18 00:22 UTC. Twin floor 12.5 GB/s · QSFP 25.0 · host PCIe 31.5. IB `port_xmit_data` is 0 for TCP; split is sysfs `tx_bytes`.

## TCP iperf3 calibration (01–02, jumbo, f0)

Date of the scored coord rerun: 2026-09-18. Hub zeno-02. iperf3 `-t 10 -P 8 -J`. Pass gate: one twin ≥ ~11.25 GB/s (90 Gbps); both twins ≥ 20 GB/s.

| Flow | Bind → dest | App GB/s | Gbps | Eth tx (10 s) | Twin split |
|---|---|---:|---:|---|---|
| one f0 twin | `.68` → `.64` | **13.88** | 111.0 | 139.8 GB on `enp1s0f0np0` | sibling `enP2p1s0f0np0` idle |
| both f0 twins | `.68→.64:5201` + `.70→.66:5202` | **21.80** | 174.4 | 137.6 + 82.1 GB | **both PFs** |

Both-twin flows separately: **13.65 + 8.15 = 21.80 GB/s**.

Fill of the 25.0 GB/s rail-f0 cap:

| Run | GB/s | of 25.0 |
|---|---:|---:|
| iperf one twin (sibling idle) | 13.88 | 56% |
| iperf both twins | 21.80 | 87% |
| Flight 1-to-1 | 13.34 | 53% |
| Flight 1-to-many | 21.59 | 86% |
| Flight many-to-1 | 13.84 | 55% |

One PF with the sibling idle can take **more than 100 Gbps** of the shared 200G QSFP (ethtool advertises 200G per netdev). That is why the single-twin iperf sits at 13.88 GB/s instead of 12.5. It is not a units error (~50 / ~100 GB/s never appeared).

Both twins in parallel are short of NIXL’s 24.50 GB/s `ib_write_bw` (98.02 + 97.96 Gb/s on 01–02 f0) and short of the 23–24 GB/s TCP goal. iperf CPU was already saturated (`host_system` ~120%, `remote_system` ~330%). Flight cannot beat this TCP ceiling.

JSON: `flight-bench/results/iperf-f0a.json`, `iperf-f0-both.json`. Log: `coord-rerun.log`.

## Phase 1 Flight DoPut (rail-f0, two clients per QSFP)

Payload: DoPut, 65536 rec/batch (2 MiB), 67108864 rec/stream (~2 GiB), 8 streams × 8 threads, two client processes per QSFP. GB/s is SI (`bytes / 1e9 / s`) converted from Flight’s MiB/s (`bytes / 2^20 / s`) via `bytes / nanos`.

| Group | Scheme | GB/s | Gbps | vs 25.0 | f0 `tx_bytes` split | Verdict |
|---|---|---:|---:|---|---|---|
| o2o-f0 | 02→01 | **13.34** | 106.7 | 53% | 17.46 + 17.45 GB | both twins; **gRPC/CPU**, not one-PF |
| o2m-f0 | 02→01+03 | **21.59** | 172.7 | 86% | 34.70 + 34.69 GB | matches iperf both-twins |
| m2o-f0 | 01+03→02 | **13.84** | 110.7 | 55% | 01: 17.50+17.49; 03: 17.49+17.49 | two sources, one server process |

Per-process DoPut (SI GB/s):

- o2o: 6.91 (`.68→.64`) + 6.43 (`.70→.66`)
- o2m: 5.73 + 5.16 (→01) and 5.46 + 5.24 (→03)
- m2o: 01 3.52+3.46; 03 3.40+3.46 (into `.68` / `.70`)

Source bind (`LD_PRELOAD` `connect()` for AF_INET and AF_INET6 `::ffff:` plus `BIND_DEV`) is working: every Flight run moved ~equal bytes on `enp1s0f0np0` and `enP2p1s0f0np0`. A first pass without IPv6 bind stuffed both clients onto one PF (~6.6 GB/s) and is discarded.

## Score vs 12.5 / 25.0 / 31.5

| Pattern | Meaning | This run |
|---|---|---|
| ~12 GB/s on a “both twins” run | only one PF (bind/route bug) | Not on the scored run; both f0 PFs carried ~equal `tx_bytes` |
| 23–24 GB/s on f0 | 200G QSFP saturated | Not reached. iperf **21.80**; Flight o2m **21.59** |
| 5–15 GB/s, both PFs busy | protocol / CPU | o2o **13.34** and m2o **13.84** (one `perf_server`) |
| ~50 or ~100 GB/s | MiB vs MB vs GB | Not seen; bytes/nanos SI conversion |

NIXL comparison (WRITE, DRAM, UCX). NIXL 3-node runs were **dual-rail**; Phase 1 Flight is **rail-f0 only**.

| Scheme | NIXL GB/s | Flight GB/s | Cap used |
|---|---:|---:|---|
| one-to-one | 24.44 (p12-f0) | 13.34 | 25.0 one QSFP |
| one-to-many | 26.20 (o2m-i02 dual) | 21.59 | 25.0 Phase 1 / 31.5 NIXL dual |
| many-to-one | 21.84 (m2o-t02 dual) | 13.84 | 25.0 Phase 1 / 31.5 NIXL dual |

gRPC DoPut on this GB10/CX-7 path is a **protocol/CPU result**, not a fabric fail: iperf already tops out near 22 GB/s on f0, one-to-one Flight is ~13 GB/s even with both twins pinned, and one-to-many Flight rides the TCP ceiling because it has two destination hosts.

NIXL pairwise f0/f1 on all three pairs (p12, p13, p23) was 24.42–24.44 GB/s. Pairwise dual stayed 23.77–23.81. Full NIXL table: `nixl-bench/results/RESULTS.md` and `nixl-bench/docs/nixl-bandwidth-targets.md`.

Phase 2 (f1 / dual / other pairs) is out of scope until this rail-f0 matrix is accepted. DoGet, TLS, compression, and VRAM were not run.

## Where the code, scripts, and notes are

All of this lives on zeno-02 under `/home/aocsa/git`. Nothing was forked inside Arrow C++.

### Flight (this comparison)

| Path | Role |
|---|---|
| `/home/aocsa/git/flight-bench/` | Harness root |
| `env.sh` | Mgmt and CX-7 IPs, payload sizes, rendezvous `:8776`, files `:8775` |
| `coord.py` | Phase 1 driver: iperf one twin, iperf both twins, o2o, o2m, m2o |
| `run-schemes.sh` | `source env.sh` then `python3 coord.py` |
| `worker.py` | On zeno-01 and zeno-03: pull jobs from the rendezvous, run iperf server or Flight clients/server |
| `start-worker.sh` | Bootstrap a remote worker: pull `dist.tgz`, check in, exec `worker.py` |
| `rendezvous.py` | HTTP key/value on mgmt `10.87.131.182:8776` (not NIXL `:8766`) |
| `fileserver.py` | Serves `/home/aocsa/git` on `:8775` so workers can fetch the tree |
| `common.py` | NIC map, `tx_bytes` / IB counters, Flight argv, MiB/s → SI GB/s |
| `bind_connect.c` | `LD_PRELOAD` that binds `connect()` to `BIND_ADDR` (AF_INET and `::ffff:` AF_INET6) and optional `BIND_DEV` |
| `lib/bind_connect.so` | Built preload |
| `prefix/bin/arrow-flight-benchmark` | Stock client (`-test_put`, `-transport=grpc`) |
| `prefix/bin/arrow-flight-perf-server` | Stock server |
| `bin/iperf3` | Local iperf3 used by the coord (PATH prefers this over a system binary) |
| `results/RESULTS.md` | Scored write-up (shorter than this document) |
| `results/summary.csv` | One row per group |
| `results/iperf-f0a.json`, `iperf-f0-both.json` | iperf JSON + eth split |
| `results/o2o-f0.json`, `o2m-f0.json`, `m2o-f0.json` | Flight JSON |
| `results/coord-rerun.log` | Scored run log (2026-09-18 00:21–00:22 UTC) |
| `results/coord.log` | Earlier discarded pass (IPv4-only bind, traffic on one PF) |

### NIXL (the comparison baseline)

| Path | Role |
|---|---|
| `/home/aocsa/git/nixl-bench/` | Harness root. NIXL Python 1.4.1 UCX plugin, not native nixlbench |
| `env.sh` | `UCX_TLS=rc,ud,sm,self`, rail device lists, same IP map, rendezvous `:8766` |
| `sat.py` | DRAM UCX WRITE: 16 MiB × 8, 50 warmup + 200 timed iters |
| `run-sat.sh` | `run-sat.sh f0\|f1\|dual` then `sat.py` |
| `coord.py`, `run-2node.sh`, `run-3node.sh` | Pairwise and 3-node drivers |
| `worker.py`, `rendezvous.py`, `start-etcd.sh` | Control plane on mgmt 1G |
| `results/RESULTS.md` | Pairwise 24.42–24.44, dual ~23.8, m2o 21.84, o2m 26.20, `ib_write_bw` 24.50 |
| `results/p12-*.json`, `p13-*.json`, `p23-*.json`, `m2o-t02.json`, `o2m-i02.json`, `summary.csv` | Per-run JSON |
| `results/ibw-02to01-f0a.log`, `ibw-02to01-f0b.log` | `ib_write_bw` 98.02 and 97.96 Gb/s |
| `docs/nixl-bandwidth-targets.md` | Caps canvas export |

Topology notes: `zeno-fabric-topology.md` next to this file (LLDP 2026-09-17). Canvas sources: `zeno-fabric-topology.canvas.tsx`, `flight-vs-nixl.canvas.tsx`, `nixl-bandwidth-targets.canvas.tsx` under the Cursor canvases directory.

## How to reproduce Phase 1

Run this on the three Sparks as they are cabled (rail-f0 = tor-2). Control plane stays on the 1G mgmt addresses. Data plane is CX-7 TCP. Clear `http_proxy` / `https_proxy` on every host; the 10.87.131.0/25 fabric is not the proxy path.

### 1. Binaries (zeno-02)

Stock Apache Arrow **release** build of `arrow-flight-benchmark` and `arrow-flight-perf-server`, installed into `flight-bench/prefix`. Flight’s UCX transport is gone ([apache/arrow#43296](https://github.com/apache/arrow/issues/43296)); both binaries are gRPC/TCP only. Do not patch Arrow. The weak-host route on `10.87.131.0/25` is fixed outside the process.

```bash
# preload — gRPC connects with AF_INET6 v4-mapped sockets, so AF_INET-only bind is not enough
gcc -shared -fPIC -o /home/aocsa/git/flight-bench/lib/bind_connect.so \
  /home/aocsa/git/flight-bench/bind_connect.c -ldl
```

`iperf3` must be at `flight-bench/bin/iperf3` (or first on `PATH` after `env.sh`). Confirm with `command -v iperf3` after sourcing `env.sh`.

Pack what the workers fetch:

```bash
cd /home/aocsa/git/flight-bench
tar -czf dist.tgz \
  worker.py common.py env.sh bind_connect.c \
  bin/iperf3 lib/bind_connect.so \
  prefix/bin prefix/lib
```

`prefix/lib` is large (Arrow + gRPC). `start-worker.sh` skips a full re-fetch when `prefix/bin/arrow-flight-benchmark` is already present; `worker.py` still refreshes `common.py`, `env.sh`, and `lib/bind_connect.so`.

### 2. Control plane (zeno-02)

Two processes, mgmt only:

```bash
cd /home/aocsa/git
python3 -u flight-bench/fileserver.py
# listens 0.0.0.0:8775, serves /home/aocsa/git/flight-bench/

python3 -u flight-bench/rendezvous.py
# listens 0.0.0.0:8776
# health: curl --noproxy '*' http://10.87.131.182:8776/health
```

Restart the rendezvous with an empty store before a scored run. A leftover STORE from a killed coord will hand workers stale commands.

### 3. Workers (zeno-01 and zeno-03)

On each host, as the user that owns `~/git`:

```bash
export FLIGHT_BENCH_ROOT=$HOME/git/flight-bench
export FLIGHT_FILES=http://10.87.131.182:8775
export FLIGHT_RV=http://10.87.131.182:8776
# start-worker.sh zeno-01    # on zeno-01
# start-worker.sh zeno-03    # on zeno-03
bash "$FLIGHT_BENCH_ROOT/start-worker.sh" "$(hostname -s)"
```

The script PUTs `starting` then `ready` to `$FLIGHT_RV/k/worker/<host>`. `coord.py` blocks in `wait_workers()` until both keys exist. SSH from zeno-02 to 01/03 is not part of the harness; start the workers on those hosts directly.

### 4. Coordinator (zeno-02)

One coord only. Two coords at once fight over the iperf ports and the rendezvous sequence numbers.

```bash
cd /home/aocsa/git/flight-bench
bash run-schemes.sh
```

`coord.py` then, in order:

1. **iperf one twin.** zeno-01 `iperf3 -s` bound to `.64:5201`. zeno-02 client: `iperf3 -c 10.87.131.64 -B 10.87.131.68 -p 5201 -t 10 -P 8 -J`. `ok` if ≥ 90 Gbps.
2. **iperf both twins.** Servers on `.64:5201` and `.66:5202`. Clients `.68→.64` and `.70→.66` in parallel. Sum SI GB/s. `ok` if ≥ 20 GB/s.
3. **one-to-one.** `arrow-flight-perf-server` on zeno-01, `-server_host=10.87.131.64 -port=31337 -transport=grpc`. Two local clients, `LD_PRELOAD=lib/bind_connect.so`:
   - `BIND_ADDR=10.87.131.68` `BIND_DEV=enp1s0f0np0` → server `.64`
   - `BIND_ADDR=10.87.131.70` `BIND_DEV=enP2p1s0f0np0` → server `.66`
4. **one-to-many.** Servers on zeno-01 (`.64`) and zeno-03 (`.72`). Four clients on zeno-02: `.68/.70` → 01 `.64/.66` and `.68/.70` → 03 `.72/.74`.
5. **many-to-one.** Server on zeno-02 (`.68:31337`). Workers on 01 and 03 each run two clients into `.68` and `.70`.
6. Writes `results/summary.csv` and `results/<group>.json`, then posts `STOP` to the workers.

Client flags (from `common.py` / `env.sh`):

```
-test_put
-records_per_batch=65536
-records_per_stream=67108864
-num_streams=8
-num_threads=8
-num_perf_runs=1
-transport=grpc
```

### 5. How a number is scored

- Flight prints `Speed: … MB/s` in **MiB/s** (`1 << 20`). `parse_flight_output` prefers `Bytes written` / `Nanos`, and `bytes / nanos` is already SI GB/s. Do not quote the raw “MB/s” line as GB/s.
- iperf `-J`: `end.sum_received.bits_per_second`, else `sum_sent`, else `sum`. GB/s = bps / 8e9.
- Twin split for TCP is sysfs `/sys/class/net/<dev>/statistics/tx_bytes` before/after. A healthy both-twins run has > 1 GB on **both** `enp1s0f0np0` and `enP2p1s0f0np0`. IB `port_xmit_data` stays 0 on this TCP path; those counters are RDMA and are what NIXL uses.
- Pass/fail shortcuts: ~12 GB/s with one PF idle means the bind missed a twin. ~22 GB/s with both PFs busy is the TCP ceiling on this rail. ~23–24 GB/s is what NIXL RoCE did, not what gRPC did. ~50 or ~100 GB/s is a units error.

### 6. Bind check (do this if a run looks like one PF)

gRPC uses `AF_INET6`. An `AF_INET`-only preload binds nothing and the kernel weak-host route dumps both clients onto one netdev (~6.6 GB/s total). `bind_connect.c` handles both domains. Spot-check:

```bash
BIND_ADDR=10.87.131.70 BIND_DEV=enP2p1s0f0np0 \
  LD_PRELOAD=/home/aocsa/git/flight-bench/lib/bind_connect.so \
  python3 -c 'import socket; s=socket.socket(socket.AF_INET6, socket.SOCK_STREAM); s.connect(("10.87.131.64", 22)); print(s.getsockname())'
# expect ::ffff:10.87.131.70
```

### NIXL baseline (already scored; rerun only if you need a fresh RoCE number)

On zeno-02, with NIXL 1.4.1 and the UCX plugin on `PYTHONPATH`:

```bash
cd /home/aocsa/git/nixl-bench
# rendezvous on :8766, workers checked in, then:
bash run-2node.sh    # pairwise f0/f1/dual for p12, p13, p23
bash run-3node.sh    # m2o-t02 and o2m-i02, dual-rail
```

Data path is `UCX_TLS=rc,ud,sm,self`. Do not leave UCX on TCP if the question is whether the 200G QSFP fills. Message size in `sat.py` is 16 MiB × batch 8. Pairwise pass is ≥ 23 GB/s on one rail; dual pass would be ≥ 28 GB/s and was **not** met (23.8 GB/s, four PFs, one QSFP of bandwidth).
