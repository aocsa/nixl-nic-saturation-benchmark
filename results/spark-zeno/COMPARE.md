# Spark zeno (archived) — TCP iperf3 vs NIXL WRITE vs Flight DoPut

Date: 2026-09-17 (NIXL) / 2026-09-18 (Flight + iperf). Hub zeno-02. SI GB/s.

| Scheme | NIXL WRITE | TCP iperf3 | Flight DoPut |
|---|---:|---:|---:|
| one-to-one (rail-f0) | **24.44** (p12-f0) | 13.88 one twin; **21.80** both twins | **13.34** |
| one-to-many | **26.20** (dual-rail o2m-i02) | — | **21.59** (rail-f0, two servers) |
| many-to-one | **21.84** (dual-rail m2o-t02) | — | **13.84** (one perf_server) |

Caps: twin 12.5 · QSFP 25.0 · host PCIe 31.5. NIXL pairwise f0/f1 all **PASS 200G**. Dual-rail pairwise stayed ~24 (did not stack the second cage). AWS g7e.8xlarge cap is **12.5** (100G), not these Spark numbers.

Details: [`nixl/RESULTS.md`](nixl/RESULTS.md), [`flight/RESULTS.md`](flight/RESULTS.md).
