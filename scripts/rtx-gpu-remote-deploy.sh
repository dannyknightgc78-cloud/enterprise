#!/usr/bin/env bash
# SSH to RTX Pro (172.236.195.90) and install GPU relay + Cursor worker.
set -euo pipefail

RTX_HOST="${RTX_HOST:-172.236.195.90}"
RTX_USER="${RTX_USER:-root}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=20 -o BatchMode=yes)
BRANCH="${CURSOR_GPU_BRANCH:-cursor/rtx-pro-hybrid-relay-4fb3}"
REPO="${CURSOR_GPU_REPO:-https://github.com/dannyknightgc78-cloud/enterprise.git}"

echo "==> RTX GPU remote deploy → ${RTX_USER}@${RTX_HOST}"

if ! ssh "${SSH_OPTS[@]}" "${RTX_USER}@${RTX_HOST}" 'echo connected'; then
  echo "SSH blocked. Paste this ONE block in an SSH/root shell on the RTX server (172.236.195.90):"
  echo
  cat <<'CONSOLE'
PUB='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGh5uzhhDMuW+reaCiInxGD2EetWAK+QyxnW0TFnvxeu cursor-cloud-agent'
mkdir -p /root/.ssh && chmod 700 /root/.ssh
grep -qF "$PUB" /root/.ssh/authorized_keys 2>/dev/null || echo "$PUB" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
curl -fsSL https://raw.githubusercontent.com/dannyknightgc78-cloud/enterprise/cursor/rtx-pro-hybrid-relay-4fb3/infra/rtx-pro/scripts/bootstrap.sh | bash
CONSOLE
  echo
  echo "Then re-run: ./scripts/rtx-gpu-remote-deploy.sh"
  exit 1
fi

ssh "${SSH_OPTS[@]}" "${RTX_USER}@${RTX_HOST}" "bash -s" <<REMOTE
set -euo pipefail
export CURSOR_GPU_BRANCH='${BRANCH}'
export CURSOR_GPU_REPO='${REPO}'
curl -fsSL https://raw.githubusercontent.com/dannyknightgc78-cloud/enterprise/${BRANCH}/infra/rtx-pro/scripts/bootstrap.sh | bash
REMOTE

echo "==> Remote bootstrap finished. Checking worker..."
ssh "${SSH_OPTS[@]}" "${RTX_USER}@${RTX_HOST}" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/cursor-workers/enterprise/infra/rtx-pro 2>/dev/null || exit 0
docker compose ps 2>/dev/null || true
pgrep -af 'agent worker' || echo "worker not running yet — check .env keys"
REMOTE

echo "Done. Start Cloud Agent with pool=rtx-pro and type: use gpus"
