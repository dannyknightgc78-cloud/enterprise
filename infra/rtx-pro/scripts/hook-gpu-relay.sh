#!/usr/bin/env bash
# GPU relay hooks — stream progress back to Cursor as if running directly on RTX Pro server.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROGRESS_LOG="/tmp/cursor-gpu-relay-progress.log"
MODE_FILE="$(cd "${SCRIPT_DIR}/.." && pwd)/.hybrid-mode"

log_progress() {
  local msg="$1"
  mkdir -p "$(dirname "${PROGRESS_LOG}")"
  printf '%s\n' "{\"ts\":\"$(date -Iseconds)\",\"msg\":$(jq -Rn --arg m "$msg" '$m')}" >> "${PROGRESS_LOG}" 2>/dev/null || true
}

read_mode() {
  if [[ -f "${MODE_FILE}" ]]; then
    cat "${MODE_FILE}" | tr -d '[:space:]'
  else
    echo "hybrid"
  fi
}

tunnel_ok() {
  curl -sf "${RTX_AI_BASE:-https://ai.dannygc.cloud/v1}/models" >/dev/null 2>&1
}

RTX_AI_BASE="${RTX_AI_BASE:-https://ai.dannygc.cloud/v1}"

nim_ok() {
  curl -sf http://127.0.0.1:8000/v1/models >/dev/null 2>&1
}

INPUT=$(cat)
EVENT=$(echo "${INPUT}" | jq -r '.event // empty')
CMD=$(echo "${INPUT}" | jq -r '.command // empty')
EXIT_CODE=$(echo "${INPUT}" | jq -r '.exit_code // empty')
TOOL=$(echo "${INPUT}" | jq -r '.tool_name // .tool // empty')
MCP_TOOL=$(echo "${INPUT}" | jq -r '.toolName // empty')

MODE=$(read_mode)
GPU_LABEL="RTX Pro"
if tunnel_ok; then
  GPU_LABEL="RTX Pro + Nemotron (auto)"
elif nim_ok; then
  GPU_LABEL="RTX Pro + Nemotron"
else
  GPU_LABEL="RTX Pro"
fi

case "${EVENT}" in
  sessionStart)
    bash "${SCRIPT_DIR}/../../../scripts/rtx-auto-enable.sh" >/dev/null 2>&1 || echo "local" > "${MODE_FILE}"
    MODE=$(read_mode)
    log_progress "session started mode=${MODE} auto=on"
    jq -n \
      --arg msg "🖥️ ${GPU_LABEL} — auto routing on (no commands needed)" \
      '{agent_message: $msg}'
    ;;

  beforeShellExecution)
    log_progress "shell: ${CMD}"
    jq -n \
      --arg msg "🖥️ ${GPU_LABEL}: running \`${CMD}\`..." \
      '{permission: "allow", agent_message: $msg}'
    ;;

  afterShellExecution)
    log_progress "shell done exit=${EXIT_CODE}: ${CMD}"
    SUMMARY=""
    if nim_ok && [[ "$(read_mode)" != "cursor" ]]; then
      case "${CMD}" in
        *"npm "*|*"pnpm "*|*"pytest"*|*"cargo "*|*"docker "*|*"make "*|*"git "*)
          SUMMARY=$(bash "${SCRIPT_DIR}/route-local.sh" fast-chat \
            "One line: command finished on GPU. exit=${EXIT_CODE}. cmd=${CMD}" 2>/dev/null || true)
          ;;
      esac
    fi
    if [[ -n "${SUMMARY}" ]]; then
      jq -n \
        --arg msg "✅ ${GPU_LABEL}: exit ${EXIT_CODE} | ${SUMMARY}" \
        '{agent_message: $msg}'
    else
      jq -n \
        --arg msg "✅ ${GPU_LABEL}: finished (exit ${EXIT_CODE})" \
        '{agent_message: $msg}'
    fi
    ;;

  beforeMCPExecution)
    log_progress "mcp: ${MCP_TOOL}"
    jq -n \
      --arg msg "🔌 ${GPU_LABEL} MCP: ${MCP_TOOL}..." \
      '{permission: "allow", agent_message: $msg}'
    ;;

  afterMCPExecution)
    log_progress "mcp done: ${MCP_TOOL}"
    jq -n \
      --arg msg "🔌 ${GPU_LABEL} MCP: ${MCP_TOOL} done" \
      '{agent_message: $msg}'
    ;;

  preToolUse)
    log_progress "tool: ${TOOL}"
    jq -n \
      --arg msg "⚙️ ${GPU_LABEL}: ${TOOL}..." \
      '{agent_message: $msg}'
    ;;

  postToolUse)
    log_progress "tool done: ${TOOL}"
    jq -n \
      --arg msg "⚙️ ${GPU_LABEL}: ${TOOL} complete" \
      '{agent_message: $msg}'
    ;;

  beforeSubmitPrompt)
    # Auto-enable local RTX routing every session — no user phrase required
    bash "${SCRIPT_DIR}/../../../scripts/rtx-auto-enable.sh" >/dev/null 2>&1 || true
    PROMPT=$(echo "${INPUT}" | jq -r '.prompt // empty' | head -c 120)
    if echo "${PROMPT}" | grep -qiE 'use cursor|cursor only|\[cursor\]'; then
      echo "cursor" > "${MODE_FILE}"
      log_progress "user override: cursor mode"
      jq -n --arg msg "🔵 Cursor cloud models (override)" '{agent_message: $msg}'
    else
      echo '{}'
    fi
    ;;

  *)
    echo '{}'
    ;;
esac
