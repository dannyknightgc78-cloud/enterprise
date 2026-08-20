#!/usr/bin/env bash
# === PASTE ON YOUR RTX SERVER (root@172.236.195.90) — SSH or provider console ===
# Sets up Cursor GPU pool worker rtx-pro. Pass key inline:
#   CURSOR_API_KEY='key_...' bash -s  <(curl -fsSL https://raw.githubusercontent.com/dannyknightgc78-cloud/enterprise/main/infra/rtx-pro/scripts/setup-gpu-worker-console.sh)
# Or paste block below after editing CURSOR_API_KEY line.
set -euo pipefail

CURSOR_API_KEY="${CURSOR_API_KEY:-PASTE_SERVICE_ACCOUNT_KEY_HERE}"
INSTALL_ROOT=/opt/cursor-workers/enterprise

echo "=== GPU worker setup $(date -u) ==="

# Authorize Cursor cloud agent SSH
mkdir -p /root/.ssh && chmod 700 /root/.ssh
PUB='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGh5uzhhDMuW+reaCiInxGD2EetWAK+QyxnW0TFnvxeu cursor-cloud-agent'
grep -qF "$PUB" /root/.ssh/authorized_keys 2>/dev/null || echo "$PUB" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# Repo on main
if [[ -d "$INSTALL_ROOT/.git" ]]; then
  cd "$INSTALL_ROOT" && git fetch origin && git checkout main && git pull origin main
else
  git clone -b main https://github.com/dannyknightgc78-cloud/enterprise.git "$INSTALL_ROOT"
fi

# Cursor CLI
command -v agent >/dev/null || { curl https://cursor.com/install -fsS | bash; export PATH="$HOME/.local/bin:$PATH"; }

# .env
cd "$INSTALL_ROOT/infra/rtx-pro"
[[ -f .env ]] || cp .env.example .env
if [[ "$CURSOR_API_KEY" != PASTE_SERVICE_ACCOUNT_KEY_HERE ]]; then
  grep -q '^CURSOR_API_KEY=' .env && sed -i "s|^CURSOR_API_KEY=.*|CURSOR_API_KEY=${CURSOR_API_KEY}|" .env || echo "CURSOR_API_KEY=${CURSOR_API_KEY}" >> .env
else
  echo "ERROR: Set CURSOR_API_KEY=your_service_account_key before running"
  exit 1
fi
grep -q '^WORKER_ROOT=' .env || echo "WORKER_ROOT=${INSTALL_ROOT}" >> .env

pip3 install -q -r mcp/requirements.txt 2>/dev/null || true

# systemd — worker survives reboot
cat > /etc/systemd/system/cursor-rtx-worker.service <<UNIT
[Unit]
Description=Cursor pool worker rtx-pro
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Restart=always
RestartSec=10
WorkingDirectory=${INSTALL_ROOT}
Environment=HOME=/root
Environment=PATH=/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
EnvironmentFile=${INSTALL_ROOT}/infra/rtx-pro/.env
ExecStart=${INSTALL_ROOT}/infra/rtx-pro/worker/start-worker.sh

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable cursor-rtx-worker.service
systemctl restart cursor-rtx-worker.service
sleep 3
systemctl --no-pager status cursor-rtx-worker.service || true
tail -20 /tmp/cursor-rtx-worker.log 2>/dev/null || journalctl -u cursor-rtx-worker -n 20 --no-pager || true

echo "=== Worker pool=rtx-pro ==="
pgrep -af 'agent worker' || echo "check logs if not running"
nvidia-smi -L 2>/dev/null | head -2 || true
