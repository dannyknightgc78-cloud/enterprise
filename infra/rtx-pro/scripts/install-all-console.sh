#!/usr/bin/env bash
# ONE paste on RTX server (SSH or provider console) — authorizes Cursor SSH + installs worker.
set -euo pipefail

echo "=== Cursor RTX full install ==="
date -u

# 1) SSH keys for Cursor cloud agent
mkdir -p /root/.ssh && chmod 700 /root/.ssh
for PUB in \
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGh5uzhhDMuW+reaCiInxGD2EetWAK+QyxnW0TFnvxeu cursor-cloud-agent' \
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFFWu6tW6vP2CYNp0CQn5lUSXB5Zitu/SrP5EQewx5Yc cursor-cloud-agent-recovery'
do
  grep -qF "$PUB" /root/.ssh/authorized_keys 2>/dev/null || echo "$PUB" >> /root/.ssh/authorized_keys
done
chmod 600 /root/.ssh/authorized_keys
echo "SSH keys: OK"

# 2) Clone/update enterprise repo
INSTALL_ROOT=/opt/cursor-workers/enterprise
BRANCH=main
if [[ -d "$INSTALL_ROOT/.git" ]]; then
  cd "$INSTALL_ROOT" && git fetch origin && git checkout "$BRANCH" && git pull origin "$BRANCH"
else
  git clone -b "$BRANCH" https://github.com/dannyknightgc78-cloud/enterprise.git "$INSTALL_ROOT"
  cd "$INSTALL_ROOT"
fi

# 3) Cursor CLI
command -v agent >/dev/null || curl https://cursor.com/install -fsS | bash

# 4) Use existing Ollama/Nemotron if already running (skip heavy NIM pull)
if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama local: OK — using existing Nemotron on GPU"
elif curl -sf https://ai.dannygc.cloud/v1/models >/dev/null 2>&1; then
  echo "RTX tunnel AI: OK — ai.dannygc.cloud"
else
  echo "Starting NIM stack (needs NGC_API_KEY in .env)..."
  cd "$INSTALL_ROOT/infra/rtx-pro"
  [[ -f .env ]] || cp .env.example .env
  docker compose up -d 2>/dev/null || true
fi

# 5) Python MCP deps
pip3 install -q -r "$INSTALL_ROOT/infra/rtx-pro/mcp/requirements.txt" 2>/dev/null || true

# 6) Worker (needs CURSOR_API_KEY service account in .env)
cd "$INSTALL_ROOT/infra/rtx-pro"
if [[ -f .env ]] && grep -qE '^CURSOR_API_KEY=.+$' .env; then
  nohup bash worker/start-worker.sh >> /tmp/cursor-rtx-worker.log 2>&1 &
  echo "Cursor worker starting — log: /tmp/cursor-rtx-worker.log"
else
  echo "WARN: Set CURSOR_API_KEY in $INSTALL_ROOT/infra/rtx-pro/.env then: bash worker/start-worker.sh"
fi

echo "=== DONE ==="
nvidia-smi -L 2>/dev/null | head -2 || true
curl -sf https://ai.dannygc.cloud/v1/models | head -c 200; echo
