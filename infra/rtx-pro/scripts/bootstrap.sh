#!/usr/bin/env bash
# One-line bootstrap for RTX Pro — paste on your GPU workstation terminal.
# curl -fsSL https://raw.githubusercontent.com/dannyknightgc78-cloud/enterprise/cursor/rtx-pro-hybrid-relay-4fb3/infra/rtx-pro/scripts/bootstrap.sh | bash
set -euo pipefail

REPO="${CURSOR_GPU_REPO:-https://github.com/dannyknightgc78-cloud/enterprise.git}"
BRANCH="${CURSOR_GPU_BRANCH:-cursor/rtx-pro-hybrid-relay-4fb3}"
INSTALL_ROOT="${CURSOR_GPU_ROOT:-/opt/cursor-workers/enterprise}"

echo "==> Cursor GPU relay bootstrap"
echo "    repo: ${REPO}@${BRANCH}"
echo "    root: ${INSTALL_ROOT}"

if [[ -d "${INSTALL_ROOT}/.git" ]]; then
  cd "${INSTALL_ROOT}"
  git fetch origin
  git checkout "${BRANCH}" 2>/dev/null || git checkout -b "${BRANCH}" "origin/${BRANCH}"
  git pull origin "${BRANCH}" || true
else
  sudo mkdir -p "$(dirname "${INSTALL_ROOT}")"
  sudo git clone --branch "${BRANCH}" "${REPO}" "${INSTALL_ROOT}" 2>/dev/null \
    || git clone --branch "${BRANCH}" "${REPO}" "${INSTALL_ROOT}"
  cd "${INSTALL_ROOT}"
fi

bash infra/rtx-pro/scripts/install-rtx-pro.sh

echo ""
echo "==> Starting Nemotron stack + worker (requires .env keys)"
if [[ -f infra/rtx-pro/.env ]] && grep -q 'CURSOR_API_KEY=.\+' infra/rtx-pro/.env; then
  cd infra/rtx-pro
  docker compose up -d
  pip3 install -q -r mcp/requirements.txt 2>/dev/null || python3 -m pip install -q -r mcp/requirements.txt
  nohup bash worker/start-worker.sh >> /tmp/cursor-rtx-worker.log 2>&1 &
  echo "Worker starting — log: /tmp/cursor-rtx-worker.log"
  sleep 3
  bash scripts/preflight.sh || true
else
  echo "Edit ${INSTALL_ROOT}/infra/rtx-pro/.env then run:"
  echo "  cd ${INSTALL_ROOT}/infra/rtx-pro && docker compose up -d && bash worker/start-worker.sh"
fi

echo ""
echo "Done. In Cursor chat type:  use gpus"
echo "Pick pool rtx-pro when starting Cloud Agents."
