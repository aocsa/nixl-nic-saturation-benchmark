# Hardness / lessons (keep these or the next run lies)

## Backends

- **AWS EFA: `NIXL_BACKEND=LIBFABRIC` + `FI_PROVIDER=efa`.** UCX is NIXL’s default and on EFA it often uses a slow path (empirically TCP-speed, ~1–3 GB/s). A “NIXL ≈ iperf and both are tiny” result is almost always the wrong plugin, not a bad NIC.
- **Spark CX-7: `UCX_TLS=rc,ud,sm,self`.** Never allow `tcp` on the data path. Do not pin `UCX_IB_GID_INDEX`; zeno-03 f0 RoCEv2 IPv4 GID is 4, the others are 3. `UCX_IB_ROCE_REACHABILITY_MODE=all`.
- **g7e.8xlarge has no GPUDirect RDMA.** Leave `FI_EFA_USE_DEVICE_RDMA=0`. This bench is DRAM. GDR exists from `g7e.12xlarge` up.
- Build/install NIXL against **Amazon libfabric** (`-Dlibfabric_path=/opt/amazon/efa`). Put `/opt/amazon/efa/lib{,64}` first on `LD_LIBRARY_PATH`.

## AWS cluster

- EFA security group **must** allow **all traffic to itself** (ingress and egress). SSH-only SGs black-hole RDMA.
- **Cluster placement group**, single AZ, same subnet.
- ENI type **EFA with ENA** (`interface_type = efa`). `efa-only` drops TCP iperf and often SSH on that NIC.
- `g7e.8xlarge` has **one** EFA. Do not write Spark-style dual-rail `UCX_NET_DEVICES` lists here.

## Control plane

- HTTP rendezvous is **metadata only** (agent MD, xfer descs, worker cmds). Bind `0.0.0.0` so workers can use the ENA/mgmt IP.
- Killing processes with a cmdline grep for `rendezvous.py` also kills shells whose command line *contains* that string. `scripts/kill-stale.sh` uses `[r]endezvous.py` character-class tricks; still, do not `pkill -f rendezvous` from a script that has the word in `$0`.
- Two coordinators → iperf **server busy**. One hub, `kill-stale` first.
- Workers fetch `sat.py` from `:8765` every job so you can edit the hub copy without a second scp.

## Counters and binds

- TCP does not increment IB `port_xmit_data`. Use `tx_bytes`. `nics.py` records both, plus ENA-only netdevs.
- Spark Flight: gRPC may `connect()` as **IPv4-mapped IPv6**. The first `bind_connect.c` only bound `AF_INET`, so both clients landed on one PF (~6.6 GB/s). Bind `::ffff:BIND_ADDR` and `SO_BINDTODEVICE`.
- One CX-7 PF with the sibling idle can pull **>100 Gbps** of a shared 200G QSFP (ethtool advertises 200G per netdev). Single-twin iperf at 13.88 GB/s is not a units error.

## NIXL WRITE vs TCP

- Pairwise Spark NIXL **24.44 GB/s** vs iperf both-twins **21.80 GB/s**: RDMA into registered DRAM vs CPU copies.
- Dual-rail UCX used all four PFs but did **not** stack the second 200G cage on one pairwise WRITE (~24 GB/s, not 31.5).
- Flight o2m ≈ iperf because two `perf_server` processes exist; o2o/m2o sit near 13 GB/s (one server, gRPC).

## Process hygiene

- Unique NIXL `--listen-port` per host (inventory third field).
- `sat.py` leftovers hold GPU/NIC registrations; workers SIGTERM previous `sat.py` before each job.
- Cursor remote agents: resume the **parent that started workers**; a new Task on the hub host can `HOSTNAME_MISMATCH`. Prefer this SSH/rendezvous harness on AWS.

## Units

GB/s is SI. Flight’s printed MB/s is MiB/s. Convert from bytes+nanoseconds. Anything near 50 or 100 GB/s on these NICs is wrong.
