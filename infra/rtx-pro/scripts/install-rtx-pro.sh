#!/usr/bin/env bash
# One-shot RTX Pro setup: NVIDIA toolkit, Docker, Cursor CLI, Nemotron stack, worker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "==> RTX Pro hybrid relay installer"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "ERROR: nvidia-smi not found. Install NVIDIA drivers first." >&2
  exit 1
fi

nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

# Docker + NVIDIA Container Toolkit (Ubuntu/Debian)
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "${USER}" || true
fi

if ! docker info 2>/dev/null | grep -q nvidia; then
  echo "==> Installing NVIDIA Container Toolkit..."
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  sudo apt-get update
  sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
fi

# Cursor CLI
if ! command -v agent >/dev/null 2>&1; then
  echo "==> Installing Cursor CLI..."
  curl https://cursor.com/install -fsS | bash
fi

# Env file
if [[ ! -f "${INFRA_DIR}/.env" ]]; then
  cp "${INFRA_DIR}/.env.example" "${INFRA_DIR}/.env"
  echo "Created ${INFRA_DIR}/.env — edit NGC_API_KEY and CURSOR_API_KEY before continuing."
  exit 0
fi

# shellcheck source=/dev/null
source "${INFRA_DIR}/.env"
if [[ -z "${NGC_API_KEY:-}" || -z "${CURSOR_API_KEY:-}" ]]; then
  echo "Fill NGC_API_KEY and CURSOR_API_KEY in ${INFRA_DIR}/.env" >&2
  exit 1
fi

echo "==> Logging in to NGC..."
echo "${NGC_API_KEY}" | docker login nvcr.io -u '$oauthtoken' --password-stdin

echo "==> Starting Nemotron + LiteLLM stack..."
cd "${INFRA_DIR}"
docker compose pull
docker compose up -d

echo "==> Installing systemd units (optional, requires sudo)..."
if [[ "${INSTALL_SYSTEMD:-1}" == "1" ]]; then
  sudo cp "${INFRA_DIR}/systemd/nemotron-stack.service" /etc/systemd/system/
  sudo cp "${INFRA_DIR}/systemd/cursor-rtx-worker.service" /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable nemotron-stack.service cursor-rtx-worker.service
  sudo systemctl restart nemotron-stack.service
  echo "Worker unit installed but not started until CURSOR_API_KEY is in EnvironmentFile."
  echo "Edit /etc/systemd/system/cursor-rtx-worker.service.d/override.conf or use start-worker.sh manually first."
fi

chmod +x "${INFRA_DIR}/worker/start-worker.sh" "${INFRA_DIR}/scripts/"*.sh "${INFRA_DIR}/mcp/"*.py 2>/dev/null || true

if command -v pip3 >/dev/null 2>&1; then
  pip3 install -q -r "${INFRA_DIR}/mcp/requirements.txt" || python3 -m pip install -q -r "${INFRA_DIR}/mcp/requirements.txt"
fi

echo ""
echo "Done. Next steps:"
echo "  1. bash ${INFRA_DIR}/scripts/preflight.sh"
echo "  2. bash ${INFRA_DIR}/worker/start-worker.sh"
echo "  3. In Cursor dashboard: Cloud Agents → Self-Hosted → Allow Self-Hosted Agents"
echo "  4. Start agents with: pool=rtx-pro  (or pick pool in dashboard)"
