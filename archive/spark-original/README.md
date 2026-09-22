# Original Spark scripts

These are the files that produced `results/spark-zeno/` on zeno-02, copied without binaries.

| Tree | Produced |
|---|---|
| `nixl-bench/` | NIXL DRAM UCX WRITE, 2026-09-17. `run-2node.sh`, `run-3node.sh`, `sat.py`. Rendezvous `:8766`. |
| `flight-bench/` | Arrow Flight DoPut + iperf3, 2026-09-18. `run-schemes.sh`, `coord.py`, `bind_connect.c`. Rendezvous `:8776`, files `:8775`. |

Not included, on purpose:

- `nixl-bench/bin/etcd` and `etcdctl` (~39 MB, aarch64)
- `flight-bench/bin/iperf3`, `prefix/` (Arrow/gRPC), `dist.tgz`, `lib/bind_connect.so` (aarch64)

Rebuild the preload on the target machine:

```bash
mkdir -p flight-bench/lib
gcc -shared -fPIC -O2 -o flight-bench/lib/bind_connect.so flight-bench/bind_connect.c -ldl
```

The top-level tree (`run.sh`, `profiles/spark-zeno.env`, `flight/`) is the N-node replay, including AWS g7e. Use that on a new box. Use this archive when you need the exact argv and rendezvous ports from the scored Spark run.

Replay notes: [`docs/flight-vs-nixl.md`](../../docs/flight-vs-nixl.md), [`docs/spark-zeno.md`](../../docs/spark-zeno.md).
