# Scoring and units

Always report **SI GB/s** (`bytes / 1e9 / seconds`) and **Gbps** (`GB/s × 8`).

## How each path computes GB/s

| Tool | Raw | Conversion |
|---|---|---|
| NIXL `sat.py` | `block_size * batch * iters * npeers / elapsed` | already SI bytes |
| iperf3 `-J` | `end.sum_received.bits_per_second` | `/ 8e9` → GB/s |
| Arrow Flight | `Bytes written` / `Nanos` | bytes/ns **is** SI GB/s. Do **not** use the printed `MB/s` (that is MiB/s = 2^20). |
| IB sysfs `port_xmit_data` | 4-byte words | `words * 4 / 1e9`. Includes warmup. TCP usually stays 0. |
| Ethernet `tx_bytes` | bytes | `/ 1e9` |

## Caps

| Name | GB/s | When |
|---|---:|---|
| `CAP_GBS` env | default 12.5 | AWS g7e.8xlarge / one 100G path |
| Spark twin | 12.5 | one PF of a 200G QSFP with sibling idle |
| Spark QSFP | 25.0 | both twins, one cage. Pass pairwise ≥ 23 |
| Spark host | 31.5 | dual cage. Pass ≥ 28 |

`coord.py` writes `results/SCORE.md` vs `CAP_GBS`. `python3 scripts/score.py` reprints `summary.csv`.

## Sanity patterns (reject these)

| Number | Likely bug |
|---|---|
| ~50 or ~100 GB/s on 100/200G | bits vs bytes, or 10^9 vs 2^30, or counting both directions |
| NIXL on AWS ≈ 1–3 GB/s | UCX/TCP fallback, not EFA |
| Spark “both twins” run with only one PF busy | `UCX_NET_DEVICES` or TCP bind stuck on one netdev |
| iperf “server busy” | second `iperf3 -s` / leftover from a duplicate coordinator — `scripts/kill-stale.sh` |
| Flight ~6.6 GB/s on f0 | IPv6 connect skipped source bind (fixed in `bind_connect.c`) |

## Spark scored result (2026-09-17/18)

NIXL pairwise f0/f1 **24.44 GB/s**. Dual ~23.8. o2m **26.20**. iperf both f0 twins **21.80**. Flight o2o **13.34**, o2m **21.59**, m2o **13.84**.
