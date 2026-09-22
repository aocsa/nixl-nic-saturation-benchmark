# Shared UCX / NIXL env for Spark CX-7 multi-host twins.
# Source this, then export UCX_NET_DEVICES from a rail preset.

export NIXL_BENCH_ROOT="${NIXL_BENCH_ROOT:-/home/aocsa/git/nixl-bench}"
export PATH="${NIXL_BENCH_ROOT}/bin:${HOME}/.local/bin:${PATH}"
export PYTHONPATH="${HOME}/.local/lib/python3.12/site-packages:${PYTHONPATH:-}"

# Force RoCE; never TCP for the data path.
export UCX_TLS="${UCX_TLS:-rc,ud,sm,self}"
export UCX_IB_ROCE_REACHABILITY_MODE="${UCX_IB_ROCE_REACHABILITY_MODE:-all}"
# Do not pin GID index: zeno-03 f0 RoCEv2 IPv4 is index 4, others are 3.
export RAIL_F0="rocep1s0f0:1,roceP2p1s0f0:1"
export RAIL_F1="rocep1s0f1:1,roceP2p1s0f1:1"
export RAIL_DUAL="rocep1s0f0:1,roceP2p1s0f0:1,rocep1s0f1:1,roceP2p1s0f1:1"
export UCX_WARN_UNUSED_ENV_VARS=n
unset UCX_NET_DEVICES_F0 UCX_NET_DEVICES_F1 UCX_NET_DEVICES_DUAL

export ETCD_ENDPOINTS="${ETCD_ENDPOINTS:-http://10.87.131.182:2379}"
export NIXL_RV="${NIXL_RV:-http://10.87.131.182:8766}"
export NIXL_LISTEN_PORT="${NIXL_LISTEN_PORT:-5555}"

# Host map (mgmt / CX7)
export ZENO01_MGMT=10.87.131.181
export ZENO02_MGMT=10.87.131.182
export ZENO03_MGMT=10.87.131.183
export ZENO01_F0_A=10.87.131.64
export ZENO01_F0_B=10.87.131.66
export ZENO01_F1_A=10.87.131.65
export ZENO01_F1_B=10.87.131.67
export ZENO02_F0_A=10.87.131.68
export ZENO02_F0_B=10.87.131.70
export ZENO02_F1_A=10.87.131.69
export ZENO02_F1_B=10.87.131.71
export ZENO03_F0_A=10.87.131.72
export ZENO03_F0_B=10.87.131.74
export ZENO03_F1_A=10.87.131.73
export ZENO03_F1_B=10.87.131.75

rail_env() {
  case "$1" in
    f0)
      export UCX_NET_DEVICES="${RAIL_F0}"
      export UCX_MAX_RMA_RAILS=2
      ;;
    f1)
      export UCX_NET_DEVICES="${RAIL_F1}"
      export UCX_MAX_RMA_RAILS=2
      ;;
    dual)
      export UCX_NET_DEVICES="${RAIL_DUAL}"
      export UCX_MAX_RMA_RAILS=4
      ;;
    *)
      echo "unknown rail $1 (f0|f1|dual)" >&2
      return 1
      ;;
  esac
}
