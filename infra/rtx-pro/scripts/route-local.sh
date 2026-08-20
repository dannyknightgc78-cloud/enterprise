#!/usr/bin/env bash
# Local routing helper: send a prompt to Nemotron on GPU (execution tier).
# Used by hooks and worker-side scripts — not Cursor's cloud inference loop.
set -euo pipefail

LITELLM_URL="${LITELLM_URL:-http://127.0.0.1:4000/v1/chat/completions}"
LITELLM_KEY="${LITELLM_MASTER_KEY:-sk-rtx-local}"
MODEL="${1:-execution}"
PROMPT="${2:?Usage: route-local.sh [execution|fast-chat] \"prompt\"}"

curl -sf "${LITELLM_URL}" \
  -H "Authorization: Bearer ${LITELLM_KEY}" \
  -H "Content-Type: application/json" \
  -d "$(jq -n \
    --arg model "${MODEL}" \
    --arg content "${PROMPT}" \
    '{model: $model, messages: [{role: "user", content: $content}], temperature: 1.0, top_p: 0.95}')" \
  | jq -r '.choices[0].message.content // empty'
