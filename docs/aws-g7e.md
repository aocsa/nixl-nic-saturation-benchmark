# AWS g7e.8xlarge (and similar)

## Why this size

| | |
|---|---|
| GPU | 1× NVIDIA RTX PRO 6000 Blackwell, 96 GB |
| CPU / DRAM | 32 vCPU, 256 GiB |
| Network | **100 Gbps** ENA |
| EFA | yes, **1** interface (`EFA with ENA`) |
| GPUDirect RDMA | **no** (starts at `g7e.12xlarge`) |
| Cap used here | **12.5 GB/s** (100e9 / 8 / 1e9) |

This harness writes **host DRAM**, so missing GDR is fine. GPU-memory NIXL is out of scope on 8xlarge.

Larger G7e: 12xlarge 400 Gbps + GDR, 24xlarge 800, 48xlarge 1600. Change `instance_type` and `CAP_GBS` (`400/8/1e9 = 50`, etc.).

## Mandatory AWS knobs

1. **Cluster placement group** in **one AZ**. EFA + HPC/ML bandwidth assumes this.
2. **EFA-enabled ENI**. Terraform sets `interface_type = "efa"` (EFA **with** ENA). `efa-only` would break SSH/iperf TCP.
3. **Security group self-allow, all protocols**. Without it, EFA RDMA is silently blackholed. SSH from your CIDR is separate.
4. **Same subnet** for all N nodes.
5. **`NIXL_BACKEND=LIBFABRIC`** and **`FI_PROVIDER=efa`**. UCX on EFA often lands on TCP (~1–3 GB/s). Treat anything near iperf *and* far below 12.5 GB/s on NIXL as “wrong backend”, not “slow RDMA”.
6. Put `/opt/amazon/efa/lib` first on `LD_LIBRARY_PATH`. `env.sh` does this when the directory exists.
7. Ubuntu **22.04 or 24.04** for the AWS NIXL+EFA path. Install EFA software from [efa-installer](https://efa-installer.amazonaws.com/) (this repo pins **1.50.0**).
8. `fi_info -p efa -t FI_EP_RDM` must list provider `efa` before you run `coord.py`.
9. `g7e.8xlarge` is expensive. Tear down the placement group / instances when idle (`terraform destroy`).

## Data plane vs control plane

| Channel | Port | Path |
|---|---|---|
| NIXL WRITE | agent listen 5550+ | EFA / libfabric |
| iperf3 | 5201 | TCP on the **ENA** IP (inventory `HOSTS` IP) |
| rendezvous | 8766 | HTTP KV, metadata only |
| fileserver | 8765 | curl `sat.py` onto workers |

Do not confuse ENA TCP with EFA RDMA. iperf will never increment IB `port_xmit_data` on Spark and may not show EFA counters on AWS; `nics.py` also records Ethernet `tx_bytes`.

## Terraform

```bash
cd aws/terraform
cp terraform.tfvars.example terraform.tfvars
# set vpc_id, subnet_id (one AZ), key_name, node_count, region
terraform init
terraform apply
python3 ../../scripts/gen-inventory.py   # writes ../../inventory.env (gitignored)
```

Optional: set `ami_id` to a Deep Learning AMI that already has NVIDIA drivers + EFA so you skip the first-boot installer reboot.

Hub gets an EIP when `associate_hub_eip = true`. SSH to the hub, then hop to workers on private IPs.

## Per-node software

```bash
./scripts/install-deps.sh aws
./scripts/probe-net.sh
NIXL_BACKEND=LIBFABRIC FI_PROVIDER=efa python3 scripts/check-backend.py
```

If `check-backend.py` fails, build NIXL from source with `-Dlibfabric_path=/opt/amazon/efa` ([plugin README](https://github.com/ai-dynamo/nixl/blob/main/src/plugins/libfabric/README.md)). PyPI `nixl` is enough when it was built with libfabric and the EFA `so` is on `LD_LIBRARY_PATH`.

`FI_EFA_USE_DEVICE_RDMA=0` in the g7e profile: that flag is for GPUDirect. DRAM registration does not need it; turning it on on a no-GDR size can confuse the provider.

Disable ptrace restriction (`install-deps.sh` writes `yama/ptrace_scope=0`) so `fi_mr_reg` on DRAM is not blocked.

## Run matrix (PROFILE=aws-g7e)

For N=3 (`node0` hub):

1. `iperf-n0-n1`, `iperf-n0-n2` — TCP calibration
2. `p-n0-n1`, `p-n0-n2` — NIXL WRITE pairwise
3. `m2o-n0` — both workers WRITE into hub
4. `o2m-n0` — hub WRITE to both workers

N=2 skips m2o/o2m. Increase `node_count` for a wider fan-in.

## Pass / fail (100G)

| Observation | Meaning |
|---|---|
| iperf ~10–12.5 GB/s | ENA TCP is healthy |
| NIXL ~1–3 GB/s | UCX/TCP fallback — fix backend / `FI_PROVIDER` |
| NIXL ≥ ~10.5 GB/s | EFA DRAM WRITE saturating 100G |
| NIXL ≫ 12.5 or ~50/100 | units bug (bits vs bytes, MiB vs MB) |

## References

- [EC2 G7e](https://aws.amazon.com/ec2/instance-types/g7e/)
- [Get started with EFA](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa-start.html)
- [EFA + NIXL on EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa-start-nixl.html)
- Dynamo note: LIBFABRIC is the EFA backend that reaches line rate; UCX does not.
