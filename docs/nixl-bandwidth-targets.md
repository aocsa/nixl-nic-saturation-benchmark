# NIXL saturation · zeno-01/02/03

Export of [NIXL bandwidth targets](/home/aocsa/.cursor/projects/home-aocsa-git/canvases/nixl-bandwidth-targets.canvas.tsx) · DRAM WRITE 2026-09-17 · NIXL 1.4.1 UCX · 16 MiB × 8

Measured SI GB/s vs the fabric caps. One 200G QSFP is filled on every pairwise rail. Dual-rail pairwise does not reach the 31.5 GB/s host PCIe cap.

| | |
|---|---|
| Pairwise one rail (6/6 pass vs 23) | **24.4 GB/s** |
| Pairwise dual (short of 28–31) | **23.8 GB/s** |
| 3-node onetomany TX from 02 | **26.2 GB/s** |
| `ib_write_bw` both f0 twins | **24.5 GB/s** |

**200G QSFP is saturated.** Every f0 and f1 pairwise run landed at 24.42–24.44 GB/s (195 Gbps). IB counters split evenly across both twins of that QSFP and were idle on the other cage. That matches `ib_write_bw` 98.02 + 97.96 Gb/s = 24.50 GB/s on 01–02 f0. NIXL filled the cable.

## Measured pairwise DRAM WRITE (GB/s)

Y-axis in the canvas is NIXL initiator throughput in SI GB/s. Caps: one twin 12.5 · QSFP 25.0 · host PCIe 31.5.

| Pair | Rail | GB/s | vs QSFP 25.0 | vs PCIe 31.5 |
|---|---|---:|---|---|
| 01–02 | f0 | 24.44 | filled | — |
| 01–02 | f1 | 24.44 | filled | — |
| 01–02 | dual | 23.78 | — | short |
| 01–03 | f0 | 24.42 | filled | — |
| 01–03 | f1 | 24.43 | filled | — |
| 01–03 | dual | 23.77 | — | short |
| 02–03 | f0 | 24.44 | filled | — |
| 02–03 | f1 | 24.44 | filled | — |
| 02–03 | dual | 23.81 | — | short |

```
GB/s    12.5          25.0                31.5
          |             |                   |
01-02 f0  |=============|====  24.44
01-02 f1  |=============|====  24.44
01-02 dual|=============|===   23.78
01-03 f0  |=============|====  24.42
01-03 f1  |=============|====  24.43
01-03 dual|=============|===   23.77
02-03 f0  |=============|====  24.44
02-03 f1  |=============|====  24.44
02-03 dual|=============|===   23.81
```

Source: `sat.py` DRAM UCX WRITE, 200 timed iters after 50 warmup, 2026-09-17. Dual bars use all four PFs equally but the sum stays at one-QSFP rate.

## Score vs 12.5 / 25.0 / 31.5 GB/s

| Run | GB/s | Cap | IB twin split | Verdict |
|---|---|---|---|---|
| p12/p13/p23 × f0 or f1 | 24.42–24.44 | 25.0 | 50/50 on that QSFP; other cage idle | PASS · 200G filled |
| p12/p13/p23 × dual | 23.77–23.81 | 31.5 | 25% each of 4 PFs, same ~24 GB/s sum | UCX multi-rail shortfall |
| m2o-t02 (01+03 → 02) | 12.25 + 9.58 ≈ 21.8 | 31.5 into 02 | all 4 PFs on each initiator | Under cap; two flows contend |
| o2m-i02 (02 → 01+03) | 26.20 | 31.5 from 02 | 17.0 GB IB xmit per PF × 4 | Above one QSFP, short of PCIe |
| ib_write_bw 01–02 f0 both twins | 24.50 | 25.0 | 98.02 + 97.96 Gb/s | NIC path OK before NIXL |

## Dual-rail: four PFs, still one QSFP of bandwidth

- p12-dual: **23.8 / 31.5 GB/s** host cap
- o2m-i02: **26.2 / 31.5 GB/s** host cap

Pairwise dual stripes one WRITE across four PFs instead of stacking the second 200G cage. onetomany (two destinations per iteration) is the only run that clearly beat 25.0 GB/s. Nothing landed near 50 or 100 GB/s.

## Theoretical caps (unchanged)

| Cap | Meaning |
|---|---|
| **25.0 GB/s** | One QSFP · 200 Gbps line |
| **31.5 GB/s** | Host cap · 2× PCIe x4 |
| **12.5 GB/s** | One twin only · misconfig |
| **100 GB/s** | 4×200G ethtool · not real |

**Do not aim for 800 Gbps.** Each Spark presents four 200G netdevs, but those are CX-7 multi-host twins of two physical QSFPs, each backed by a PCIe Gen5 x4 (~126 Gbps). One cable saturates at 200 Gbps only if both twins of that QSFP carry traffic. Two cables cannot deliver 400 Gbps into the SoC — the two x4s cap the host at ~252 Gbps.

## What “saturated” should look like

Pairwise NIXL (any two of zeno-01 / 02 / 03) does not get faster with the third node. Use DRAM RDMA with large blocks. VRAM on GB10 bounces through host memory and will not hit these numbers.

| NIXL setup | Line / bus cap | Aim (large-msg RoCE) | If you land here |
|---|---|---|---|
| One PF / one twin | 12.5 GB/s (100 Gbps MAC) | 12.0 GB/s | UCX not using the twin pair — not a fabric fail |
| One QSFP, both twins (one ToR) | 25.0 GB/s (200 Gbps wire) | 23–24 GB/s (184–192 Gbps) | Rail saturated. This is the primary target. |
| Both QSFPs, all 4 PFs (both ToRs) | 31.5 GB/s (252 Gbps PCIe) | 28–31 GB/s | Host PCIe saturated. Ethernet still has headroom. |
| Both QSFPs, wire-only fantasy | 50.0 GB/s (400 Gbps) | Not reachable | SoC has only two x4 root ports to the CX-7 |
| 4× ethtool 200G | 100 GB/s (800 Gbps) | Not reachable | Four OS interfaces ≠ four independent 200G pipes |

RoCE aim is ~96% of the binding constraint at ≥1–8 MB blocks, jumbo 9000, RS-FEC. ServeTheHome measured 185–190 Gbps (23.1–23.8 GB/s) `ib_write_bw` on one QSFP when both twins were used; ~92–98 Gbps if both flows piled onto one x4.

## Where the 31.5 GB/s cap comes from

Real budget vs 4×200G illusion: **31.5 / 100 GB/s** host-real.

- Green in the canvas = one 200G QSFP (25 GB/s)
- Blue = extra PCIe if the second QSFP is also loaded (~6.5 GB/s)
- Gray remainder = the 800 Gbps ethtool figure that cannot enter GB10

| Layer | Formula | Gbps | GB/s |
|---|---|---:|---:|
| PCIe Gen5 x4 (one root port) | 4 × 32 GT/s × 128/130 | 126.03 | 15.754 |
| Host to CX-7 (two root ports) | 2 × x4 | 252.06 | 31.508 |
| One 100G MAC / twin | per PF | 100 | 12.5 |
| One physical QSFP | 2 twins on one cage | 200 | 25.0 |
| Two QSFPs on the wire | f0 + f1 cages | 400 | 50.0 |

## Twin pairs NIXL must use together

Same function number on both PCI devices is one QSFP. Mixing f0 with f1 on a single x4 is the 12.5 GB/s failure mode.

| Rail | ToR | RoCE twins | zeno-01 | zeno-02 | zeno-03 |
|---|---|---|---|---|---|
| f0 QSFP | h25-sae-dp-tor-2 | `rocep1s0f0` + `roceP2p1s0f0` | .64 + .66 | .68 + .70 | .72 + .74 |
| f1 QSFP | h25-sae-dp-tor-1 | `rocep1s0f1` + `roceP2p1s0f1` | .65 + .67 | .69 + .71 | .73 + .75 |

Prefix `10.87.131.0/25`. zeno-01 is `swp11s1`, zeno-02 `swp11s0`, zeno-03 `swp12s1` — same two ToRs, different breakout ports. Switch is not the bottleneck (SN5610).

## Three-node arithmetic

### Pairwise (recommended saturation test)

Any pair is identical: 25.0 GB/s on one rail, 31.5 GB/s host cap if both rails are used. Adding zeno-03 does not raise that pair’s line rate.

### Concurrent all-to-all

Each Spark still has only 31.5 GB/s of NIC PCIe. Split across two peers that is 15.8 GB/s theoretical per destination (126 Gbps) if both rails and both twins stay balanced. Sum of all unidirectional flows is 3 × 31.5 = 94.5 GB/s of host TX, not 300 GB/s.

### VRAM vs DRAM

`nvidia-smi topo` is NODE from GPU0 to every CX-7 PF — no GPUDirect path. Published Spark NIXL VRAM figures sit around 4 Gbps because of the host bounce. To test whether NIXL saturates the network, use DRAM segments (or `ib_write_bw` on the same twin pair). VRAM results diagnose the GB10 memory path, not the fabric.

## Pass / fail shortcuts

- **~12 GB/s** → only one twin
- **~23–24 GB/s** → 200G QSFP saturated (the number to quote as “we filled the cable”)
- **~28–31 GB/s** → both QSFPs plus both x4s, which is the real box maximum
- Anything near **50 or 100 GB/s** is a units or counter error, not a better fabric

Sources: live LLDP + PCIe width on all three Sparks (x4 @ 32 GT/s); NVIDIA note on GB10 CX-7 multi-host (STH 2025-12-01); RoCE jumbo efficiency as ~96% of the binding constraint.
