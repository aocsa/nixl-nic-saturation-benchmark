# NIXL DRAM UCX saturation — zeno-01/02/03

Date: 2026-09-17. Harness: `sat.py` (NIXL Python 1.4.1 UCX plugin), not native nixlbench.
Control plane: HTTP rendezvous `http://10.87.131.182:8766` on mgmt 1G. Data plane: RoCE (`UCX_TLS=rc,ud,sm,self`).
Message: 16 MiB × batch 8 = 128 MiB WRITE, 50 warmup + 200 timed iters. GB/s is SI (1e9).

IB `port_xmit_data` is 4-byte words; GB_ib = words × 4 / 1e9 (includes warmup).

Caps: one twin 12.5 GB/s · one 200G QSFP 25.0 GB/s (pass ≥ 23) · host PCIe 31.5 GB/s (dual pass ≥ 28).

## Calibration (ib_write_bw, 01–02, jumbo, f0 twins in parallel)

| Flow | Device | Avg |
|---|---|---|
| 02 `.68` → 01 `.64` | rocep1s0f0 | **98.02 Gb/s** |
| 02 `.70` → 01 `.66` | roceP2p1s0f0 | **97.96 Gb/s** |
| Sum | both f0 twins / one QSFP | **195.98 Gb/s = 24.50 GB/s** |

Gate passed (~12 vs ~23): both twins of one QSFP carry traffic.

## Two-node pairwise (9 runs)

Pass: rail-f0/f1 ≥ 23 GB/s. Dual ≥ 28 GB/s or document UCX multi-rail shortfall.

| Group | Pair | Rail | GB/s | Gbps | vs cap | Twin split (IB xmit GB, both PFs) | Verdict |
|---|---|---|---:|---:|---|---|---|
| p12-f0 | 02→01 | f0 | **24.44** | 195.5 | 25.0 | 17.01 + 17.01 (f1 idle) | **PASS 200G QSFP** |
| p12-f1 | 02→01 | f1 | **24.44** | 195.5 | 25.0 | 17.01 + 17.01 (f0 idle) | **PASS 200G QSFP** |
| p12-dual | 02→01 | dual | 23.78 | 190.2 | 31.5 | 8.51 × 4 PFs | shortfall ~24 |
| p13-f0 | 01→03 | f0 | **24.42** | 195.4 | 25.0 | both f0 twins | **PASS 200G QSFP** |
| p13-f1 | 01→03 | f1 | **24.43** | 195.5 | 25.0 | both f1 twins | **PASS 200G QSFP** |
| p13-dual | 01→03 | dual | 23.77 | 190.2 | 31.5 | 4-way stripe | shortfall ~24 |
| p23-f0 | 02→03 | f0 | **24.44** | 195.5 | 25.0 | both f0 twins | **PASS 200G QSFP** |
| p23-f1 | 02→03 | f1 | **24.44** | 195.5 | 25.0 | both f1 twins | **PASS 200G QSFP** |
| p23-dual | 02→03 | dual | 23.81 | 190.5 | 31.5 | 8.51 × 4 PFs | shortfall ~24 |

Dual-rail always used **all four PFs equally**, but the sum stayed ~24 GB/s (same as one QSFP). UCX did not stack the second 200G cage onto a single pairwise WRITE. That is the PCIe/UCX multi-rail shortfall called out in the plan, not a units error (~50/100 GB/s never appeared).

## Three-node (dual-rail, all four PFs)

| Group | Scheme | GB/s | vs 31.5 | Notes |
|---|---|---:|---|---|
| m2o-t02 | manytoone, target 02 | 12.25 (01) + 9.58 (03) ≈ **21.84** into 02 | under | Two WRITEs share the target; not 15.8+15.8 |
| o2m-i02 | onetomany, initiator 02 | **26.20** (209.6 Gbps) | under 28 | Best dual-rail number; 4 PFs × 17.01 IB GB |

onetomany is the only dual-rail case that clearly exceeded one 200G QSFP (26.2 > 25.0) by posting two destinations per iteration. Still short of the 31.5 GB/s host PCIe cap.

## Score vs 12.5 / 25.0 / 31.5

| Pattern | Meaning | Observed |
|---|---|---|
| ~12 GB/s | one twin | **not seen** on pairwise rails (would fail UCX_NET_DEVICES) |
| 23–24 GB/s one rail | 200G QSFP saturated | **all six f0/f1 pairwise runs 24.42–24.44** |
| 28–31 GB/s dual | host PCIe saturated | **not reached**; pairwise dual 23.8, o2m 26.2 |
| ~50 or ~100 GB/s | units/counter error | **not seen** |

JSON per run: `p12-*.json`, `p13-*.json`, `p23-*.json`, `m2o-t02.json`, `o2m-i02.json`, `summary.csv`.
