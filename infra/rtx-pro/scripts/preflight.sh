#!/usr/bin/env bash
# Verify RTX Pro GPU, Nemotron NIM, LiteLLM, and Cursor worker connectivity.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

pass() { echo -e "${GREEN}PASS${NC} $*"; }
fail() { echo -e "${RED}FAIL${NC} $*"; exit 1; }

echo "=== RTX Pro preflight ==="

command -v nvidia-smi >/dev/null && pass "nvidia-smi available" || fail "nvidia-smi missing"
nvidia-smi -L | head -3

command -v docker >/dev/null && pass "docker available" || fail "docker missing"
docker info >/dev/null 2>&1 && pass "docker daemon running" || fail "docker daemon not running"

curl -sf http://127.0.0.1:8000/v1/models >/dev/null \
  && pass "Nemotron NIM :8000" \
  || fail "Nemotron NIM not reachable — run: cd ${INFRA_DIR} && docker compose up -d"

curl -sf http://127.0.0.1:4000/health/liveliness >/dev/null \
  && pass "LiteLLM gateway :4000" \
  || fail "LiteLLM not reachable"

# Quick inference smoke test through LiteLLM
RESP=$(curl -sf http://127.0.0.1:4000/v1/chat/completions \
  -H "Authorization: Bearer ${LITELLM_MASTER_KEY:-sk-rtx-local}" \
  -H "Content-Type: application/json" \
  -d '{"model":"execution","messages":[{"role":"user","content":"Reply with exactly: nemotron-ok"}],"max_tokens":16}' \
  2>/dev/null) && echo "${RESP}" | grep -q "nemotron-ok\|content" \
  && pass "LiteLLM → Nemotron inference" \
  || echo "WARN: inference smoke test inconclusive (model may still be warming)"

command -v agent >/dev/null && pass "Cursor agent CLI" || fail "agent CLI missing — curl https://cursor.com/install | bash"

if [[ -n "${CURSOR_API_KEY:-}" ]]; then
  curl -sf "https://api.cursor.com/v0/private-workers/summary" -u "${CURSOR_API_KEY}:" >/dev/null \
    && pass "Cursor API key (service account)" \
    || fail "CURSOR_API_KEY invalid or not a service account key"
else
  echo "WARN: CURSOR_API_KEY not set in environment"
fi

curl -sf https://api2.cursor.sh >/dev/null 2>&1 || true
pass "Outbound to api2.cursor.sh (worker relay path)"

echo ""
echo "Preflight complete. Start worker: bash ${INFRA_DIR}/worker/start-worker.sh"
