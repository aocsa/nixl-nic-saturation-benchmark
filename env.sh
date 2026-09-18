# Source this, or: set -a && source profiles/<name>.env && set +a
# Then: ./scripts/start-control-plane.sh   (hub)
#        ./start-worker.sh <name>          (others)
#        ./run.sh

export NIXL_BENCH_ROOT="${NIXL_BENCH_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
export PATH="${NIXL_BENCH_ROOT}/bin:${HOME}/.local/bin:${PATH}"
export PYTHONPATH="${NIXL_BENCH_ROOT}:${HOME}/.local/lib/python3.12/site-packages:${PYTHONPATH:-}"
if [[ -d /opt/amazon/efa ]]; then
  export PATH="/opt/amazon/efa/bin:${PATH}"
  export LD_LIBRARY_PATH="/opt/amazon/efa/lib:/opt/amazon/efa/lib64:${LD_LIBRARY_PATH:-}"
fi

# Defaults; profiles override.
export NIXL_RV="${NIXL_RV:-http://127.0.0.1:8766}"
export NIXL_FILES="${NIXL_FILES:-http://127.0.0.1:8765}"
export NIXL_RV_BIND="${NIXL_RV_BIND:-0.0.0.0}"
export NIXL_RV_PORT="${NIXL_RV_PORT:-8766}"
export NIXL_LISTEN_PORT="${NIXL_LISTEN_PORT:-5555}"
export NIXL_BACKEND="${NIXL_BACKEND:-UCX}"
export UCX_TLS="${UCX_TLS:-rc,ud,sm,self}"
export UCX_IB_ROCE_REACHABILITY_MODE="${UCX_IB_ROCE_REACHABILITY_MODE:-all}"
export UCX_WARN_UNUSED_ENV_VARS=n

rail_env() {
  case "$1" in
    f0)
      export UCX_NET_DEVICES="${RAIL_F0:?set RAIL_F0 in spark profile}"
      export UCX_MAX_RMA_RAILS=2
      ;;
    f1)
      export UCX_NET_DEVICES="${RAIL_F1:?set RAIL_F1 in spark profile}"
      export UCX_MAX_RMA_RAILS=2
      ;;
    dual)
      export UCX_NET_DEVICES="${RAIL_DUAL:?set RAIL_DUAL in spark profile}"
      export UCX_MAX_RMA_RAILS=4
      ;;
    efa|default)
      export NIXL_BACKEND=LIBFABRIC
      export FI_PROVIDER="${FI_PROVIDER:-efa}"
      # g7e.8xlarge has no GPUDirect RDMA; DRAM WRITE still uses host-memory EFA RDMA.
      export FI_EFA_USE_DEVICE_RDMA="${FI_EFA_USE_DEVICE_RDMA:-0}"
      export FI_EFA_ENABLE_SHM="${FI_EFA_ENABLE_SHM:-0}"
      export FI_EFA_ENABLE_SHM_TRANSFER="${FI_EFA_ENABLE_SHM_TRANSFER:-0}"
      export RDMAV_FORK_SAFE=1
      ;;
    *)
      echo "unknown rail $1" >&2
      return 1
      ;;
  esac
}
