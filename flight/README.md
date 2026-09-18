# Arrow Flight DoPut (Spark TCP archive)

Phase 1 replica of the NIXL 1-to-1 / 1-to-many / many-to-one matrix on **rail-f0**, using stock `arrow-flight-benchmark` / `arrow-flight-perf-server` (gRPC/TCP). Flight’s UCX transport was removed ([apache/arrow#43296](https://github.com/apache/arrow/issues/43296)).

**Binaries are not in this repo** (`dist.tgz` / `prefix/` are gitignored). Build Arrow with the Flight perf examples, or copy `prefix/bin/arrow-flight-*` onto the hub and let `start-worker.sh` distribute `dist.tgz`.

## Build bind preload

```bash
mkdir -p lib
gcc -shared -fPIC -O2 -ldl -o lib/bind_connect.so bind_connect.c
```

`BIND_ADDR` + optional `BIND_DEV`. Handles `AF_INET` and `AF_INET6` `::ffff:` (gRPC dual-stack). Without the IPv6 path, both twins collapse onto one PF.

## Run (Spark)

Hub zeno-02, rendezvous **:8776**, files **:8775** (not NIXL :8766/:8765).

```bash
source env.sh
python3 fileserver.py &
python3 rendezvous.py &
python3 -u coord.py
# zeno-01 / 03:
curl -fsSL http://10.87.131.182:8775/flight/start-worker.sh | bash -s zeno-01
```

Payload: 65536 rec/batch (2 MiB), 67108864 rec/stream, 8 streams × 8 threads, two client processes per QSFP. GB/s from `Bytes / Nanos`.

Results: [`../results/spark-zeno/flight/`](../results/spark-zeno/flight/).
