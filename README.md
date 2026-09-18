# nixl-nic-saturation-benchmark

TCP **iperf3** vs NIXL DRAM **WRITE** on N hosts. Same harness ran on three NVIDIA DGX Spark boxes (CX-7 RoCE / UCX) and is meant to be re-run on **N × [g7e.8xlarge](https://aws.amazon.com/ec2/instance-types/g7e/)** (100 Gbps ENA + 1 EFA, LIBFABRIC).

| Path | Backend | What it measures |
|---|---|---|
| TCP | iperf3, 8 streams | ENA / CX-7 Ethernet ceiling |
| NIXL WRITE | DRAM, registered buffers, 16 MiB × batch 8 | RDMA (UCX RoCE on Spark, **LIBFABRIC + `FI_PROVIDER=efa` on AWS**) |

Do **not** use NIXL’s default UCX backend on EFA. UCX typically falls onto a slow transport (~1–3 GB/s, TCP-like). GPUDirect RDMA is **not** available on `g7e.8xlarge`; this bench is **host DRAM**, which EFA RDMA write still supports.

## Caps (SI GB/s, 1e9)

| Cluster | One path | Notes |
|---|---:|---|
| **g7e.8xlarge** | **12.5** | 100 Gbps instance network. Pass ≈ ≥ 10.5 (85%). |
| Spark one twin | 12.5 | 100G of a dual-PF 200G QSFP |
| Spark one QSFP (rail f0 or f1) | 25.0 | pass ≥ 23 |
| Spark host PCIe (dual rail) | 31.5 | pass ≥ 28; **not reached** on pairwise WRITE |

Spark archive: [`results/spark-zeno/`](results/spark-zeno/). NIXL pairwise rail-f0 was **24.44 GB/s**; iperf both twins **21.80 GB/s**.

## Layout

```
sat.py                 NIXL DRAM WRITE (pairwise / m2o / o2m)
coord.py               hub: iperf then NIXL jobs from inventory
worker.py              other nodes pull jobs from rendezvous
rendezvous.py          HTTP KV :8766 (metadata; not the data plane)
fileserver.py          HTTP :8765 so workers can curl this tree
nics.py                IB/EFA/ENA byte counters
inventory.py           HOSTS=name:ip:port
profiles/aws-g7e.env   100 Gbps EFA defaults
profiles/spark-zeno.env  original zeno-01/02/03 map
aws/terraform/         cluster placement group + EFA+ENA ENI
flight/                Arrow Flight DoPut harness (Spark TCP; no binaries)
docs/                  AWS, Spark, scoring, hardness
```

## AWS: N × g7e.8xlarge

1. One AZ, **cluster placement group**, EFA-enabled ENI (`interface_type = efa` = EFA **with** ENA).
2. Security group **must** allow all traffic **to itself** (EFA requirement). Terraform does this.
3. Ubuntu 24.04 or a DLAMI that already has NVIDIA + EFA. NIXL+EFA: Ubuntu 22.04/24.04.

```bash
cd aws/terraform
cp terraform.tfvars.example terraform.tfvars   # vpc_id, subnet_id, key_name
terraform init && terraform apply
python3 ../../scripts/gen-inventory.py
```

On every node:

```bash
git clone https://github.com/aocsa/nixl-nic-saturation-benchmark.git
cd nixl-nic-saturation-benchmark
./scripts/install-deps.sh aws
./scripts/probe-net.sh
# fi_info -p efa must show provider efa. Then reboot if the EFA kmod was new.
```

Hub (`node0`):

```bash
# inventory.env already has NIXL_RV / HOSTS from gen-inventory.py
./scripts/start-control-plane.sh
./run.sh inventory.env
```

Workers (`node1` …):

```bash
# copy inventory.env or:
export NIXL_RV=http://HUB_PRIVATE_IP:8766
export NIXL_FILES=http://HUB_PRIVATE_IP:8765
curl -fsSL "$NIXL_FILES/start-worker.sh" | bash -s node1
```

`coord.py` waits until `/k/worker/<name>` is posted, then:

1. iperf3 hub → each peer (TCP on the inventory IP / ENA)
2. NIXL WRITE hub → each peer
3. if N≥3: many-to-one into hub, one-to-many from hub

JSON + `results/summary.csv` + `results/SCORE.md` land on the hub.

Full AWS notes: [`docs/aws-g7e.md`](docs/aws-g7e.md).

## Spark replay (zeno-01/02/03)

```bash
cp profiles/spark-zeno.env inventory.env
# hub zeno-02
./scripts/start-control-plane.sh
# zeno-01 / zeno-03
./start-worker.sh zeno-01
./run.sh
```

`PROFILE=spark-zeno` runs the original 9 pairwise rails (f0/f1/dual) plus m2o/o2m. See [`docs/spark-zeno.md`](docs/spark-zeno.md).

## Scoring and units

- Throughput is **SI GB/s** (`bytes / 1e9 / s`). iperf bits/s ÷ 8e9.
- IB `port_xmit_data` is **4-byte words**; TCP usually leaves it at 0 — use `tx_bytes`.
- ~50 or ~100 GB/s on a 100/200G link is a units bug, not saturation.

[`docs/scoring.md`](docs/scoring.md) · [`docs/lessons.md`](docs/lessons.md)

## Similar AWS shapes

Anything with **EFA + ~100 Gbps** can use `profiles/aws-g7e.env` with `CAP_GBS` adjusted. `g7e.8xlarge` is 1× RTX PRO 6000 96 GB, 32 vCPU, 256 GiB, **100 Gbps**, **1 EFA**, **no GPUDirect RDMA**. Larger G7e (`12xlarge`+) add GDR and more EFA bandwidth; raise `CAP_GBS` and `instance_type` in terraform.
