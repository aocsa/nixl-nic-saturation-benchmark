#!/usr/bin/env bash
# Install iperf3, Python deps, Amazon EFA (AWS), and NIXL.
# Usage: ./scripts/install-deps.sh [aws|spark|common]
set -euo pipefail
MODE="${1:-auto}"
if [[ "$MODE" == auto ]]; then
  if [[ -d /opt/amazon/efa ]] || curl -fsS --max-time 1 http://169.254.169.254/latest/meta-data/instance-id >/dev/null 2>&1; then
    MODE=aws
  else
    MODE=spark
  fi
fi
echo "install-deps mode=$MODE"

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 python3-pip python3-venv iperf3 curl wget git build-essential \
    linux-tools-common pciutils iproute2 ethtool
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y python3 python3-pip iperf3 curl wget git gcc make ethtool iproute
elif command -v yum >/dev/null 2>&1; then
  sudo yum install -y python3 python3-pip iperf3 curl wget git gcc make ethtool iproute
fi

python3 -m pip install --user -U pip
python3 -m pip install --user -r "$(cd "$(dirname "$0")/.." && pwd)/requirements.txt" || \
  python3 -m pip install --user 'numpy>=1.26' 'nixl>=0.4.1'

if [[ "$MODE" == aws ]]; then
  if [[ ! -d /opt/amazon/efa ]]; then
    VER="${EFA_INSTALLER_VERSION:-1.50.0}"
    tmp="$(mktemp -d)"
    curl -fsSL -o "$tmp/aws-efa-installer.tar.gz" \
      "https://efa-installer.amazonaws.com/aws-efa-installer-${VER}.tar.gz"
    tar -C "$tmp" -xzf "$tmp/aws-efa-installer.tar.gz"
    # -y non-interactive. Skip kmod if the AMI already ships the efa module.
    if lsmod | grep -q '^efa'; then
      sudo bash "$tmp/aws-efa-installer/efa_installer.sh" -y --skip-kmod --skip-limit-conf
    else
      sudo bash "$tmp/aws-efa-installer/efa_installer.sh" -y
    fi
    echo "EFA installer finished. Reboot if the kernel module was newly installed."
  fi
  # ptrace protection blocks some RDMA register paths on Ubuntu.
  if [[ -f /proc/sys/kernel/yama/ptrace_scope ]]; then
    echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope >/dev/null || true
  fi
  echo "fi_info:"
  /opt/amazon/efa/bin/fi_info -p efa -t FI_EP_RDM | head -n 40 || true
fi

echo "python3=$(command -v python3) iperf3=$(command -v iperf3)"
python3 -c "import numpy, nixl; print('numpy', numpy.__version__, 'nixl ok')"
