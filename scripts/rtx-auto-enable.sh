#!/usr/bin/env bash
# Ensures RTX auto-routing is on — called from hooks/session; no user input.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODE_FILE="${ROOT}/infra/rtx-pro/.hybrid-mode"
RTX_AI_BASE="${RTX_AI_BASE:-https://ai.dannygc.cloud/v1}"

mkdir -p "$(dirname "${MODE_FILE}")"
echo "local" > "${MODE_FILE}"
echo "local" > /tmp/cursor-hybrid-mode 2>/dev/null || true

TUNNEL=down
curl -sf "${RTX_AI_BASE}/models" >/dev/null 2>&1 && TUNNEL=live

echo "mode=local tunnel=${TUNNEL} endpoint=${RTX_AI_BASE}"
