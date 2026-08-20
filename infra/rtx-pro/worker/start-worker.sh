#!/usr/bin/env bash
# Start a Cursor Self-Hosted Pool worker on RTX Pro.
# Tool calls from Cloud Agents relay here; inference stack runs on localhost GPUs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=/dev/null
[[ -f "${INFRA_DIR}/.env" ]] && source "${INFRA_DIR}/.env"

: "${CURSOR_API_KEY:?Set CURSOR_API_KEY in infra/rtx-pro/.env (service account key)}"
: "${WORKER_ROOT:?Set WORKER_ROOT in infra/rtx-pro/.env}"

POOL_NAME="${CURSOR_WORKER_POOL_NAME:-rtx-pro}"
LABELS_FILE="${SCRIPT_DIR}/labels.json"
WORKER_NAME="${CURSOR_WORKER_NAME:-rtx-pro-$(hostname -s)}"
IDLE_TIMEOUT="${CURSOR_IDLE_RELEASE_TIMEOUT:-3600}"

if ! command -v agent >/dev/null 2>&1; then
  echo "Cursor CLI not found. Run: curl https://cursor.com/install -fsS | bash" >&2
  exit 1
fi

mkdir -p "${WORKER_ROOT}"
if [[ ! -d "${WORKER_ROOT}/.git" ]]; then
  git clone "${WORKER_REPO_URL:-https://github.com/dannyknightgc78-cloud/enterprise.git}" "${WORKER_ROOT}"
fi

# Wait for local Nemotron relay before accepting agent sessions
NIM_URL="${NIM_HEALTH_URL:-http://127.0.0.1:8000/v1/models}"
echo "Waiting for Nemotron NIM at ${NIM_URL}..."
for i in $(seq 1 60); do
  if curl -sf "${NIM_URL}" >/dev/null 2>&1; then
    echo "Nemotron NIM ready."
    break
  fi
  if [[ "${i}" -eq 60 ]]; then
    echo "Nemotron NIM not ready after 5 minutes. Start: cd ${INFRA_DIR} && docker compose up -d" >&2
    exit 1
  fi
  sleep 5
done

export CURSOR_API_KEY

echo "Starting pool worker: pool=${POOL_NAME} name=${WORKER_NAME} root=${WORKER_ROOT}"
exec agent worker \
  --pool "${POOL_NAME}" \
  --name "${WORKER_NAME}" \
  --worker-dir "${WORKER_ROOT}" \
  --labels-file "${LABELS_FILE}" \
  --idle-release-timeout "${IDLE_TIMEOUT}" \
  --management-addr "127.0.0.1:8080" \
  start --verbose
