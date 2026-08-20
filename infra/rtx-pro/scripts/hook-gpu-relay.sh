#!/usr/bin/env bash
# Worker-side hook: annotate sessions running on RTX Pro relay pool.
# When Nemotron is up, optionally compress long command output locally (saves cloud context tokens).
set -euo pipefail

INPUT=$(cat)
EVENT=$(echo "${INPUT}" | jq -r '.event // empty')
CMD=$(echo "${INPUT}" | jq -r '.command // empty')
EXIT_CODE=$(echo "${INPUT}" | jq -r '.exit_code // empty')

NIM_OK=false
curl -sf http://127.0.0.1:8000/v1/models >/dev/null 2>&1 && NIM_OK=true

if [[ "${EVENT}" == "beforeShellExecution" ]]; then
  jq -n \
    --arg permission "allow" \
    --arg msg "RTX Pro relay (${NIM_OK:+Nemotron ready})" \
    '{permission: $permission, agent_message: $msg}'
  exit 0
fi

if [[ "${EVENT}" == "afterShellExecution" && "${NIM_OK}" == "true" && -n "${CMD}" ]]; then
  # Only summarize noisy commands to shrink what goes back to cloud context
  case "${CMD}" in
    *"npm test"*|*"pytest"*|*"cargo test"*|*"make "*|*"docker "*)
      SUMMARY=$(bash "$(dirname "$0")/route-local.sh" fast-chat \
        "In one sentence, what happened? exit=${EXIT_CODE} cmd=${CMD}" 2>/dev/null || true)
      if [[ -n "${SUMMARY}" ]]; then
        jq -n --arg s "${SUMMARY}" '{agent_message: ("GPU summary: " + $s)}'
        exit 0
      fi
      ;;
  esac
fi

echo '{}'
