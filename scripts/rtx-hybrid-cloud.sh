#!/usr/bin/env bash
# Cloud-side RTX hybrid — use your live Nemotron on RTX via ai.dannygc.cloud
# Works from Cursor cloud agents when SSH to 172.236.195.90 is blocked.
set -euo pipefail

RTX_AI_BASE="${RTX_AI_BASE:-https://ai.dannygc.cloud/v1}"
MODEL="${RTX_AI_MODEL:-nemotron-3.5-lightning:latest}"
MODE_FILE="${MODE_FILE:-/tmp/cursor-hybrid-mode}"

cmd="${1:-status}"
shift || true

read_mode() {
  [[ -f "$MODE_FILE" ]] && cat "$MODE_FILE" || echo hybrid
}

write_mode() {
  echo "$1" > "$MODE_FILE"
}

case "$cmd" in
  status)
    echo "=== RTX hybrid (cloud path) ==="
    echo "mode: $(read_mode)"
    echo "endpoint: ${RTX_AI_BASE}"
    if curl -sf "${RTX_AI_BASE}/models" >/dev/null 2>&1; then
      echo "nemotron: LIVE"
      curl -sf "${RTX_AI_BASE}/models" | python3 -c "import sys,json; d=json.load(sys.stdin); print('models:', ', '.join(m['id'] for m in d.get('data',[])))" 2>/dev/null || true
    else
      echo "nemotron: DOWN"
    fi
    ssh -o BatchMode=yes -o ConnectTimeout=5 root@172.236.195.90 'echo worker:connected' 2>/dev/null || echo "ssh: blocked (pool worker not reachable from cloud)"
    ssh -o BatchMode=yes -o ConnectTimeout=5 root@172.236.195.90 'pgrep -af "agent worker"' 2>/dev/null || echo "cursor-worker: not running on box"
    ;;
  local|use-gpus|gpu)
    write_mode local
    echo "Switched to local Nemotron (RTX via ${RTX_AI_BASE})"
    ;;
  cursor)
    write_mode cursor
    echo "Switched to Cursor cloud models"
    ;;
  hybrid)
    write_mode hybrid
    echo "Switched to hybrid mode"
    ;;
  chat|ask)
    PROMPT="$*"
    [[ -z "$PROMPT" ]] && { echo "Usage: $0 chat \"prompt\""; exit 1; }
    MODE=$(read_mode)
    [[ "$MODE" == "cursor" ]] && { echo "Mode is cursor — switch: $0 local"; exit 1; }
    curl -sf "${RTX_AI_BASE}/chat/completions" \
      -H "Content-Type: application/json" \
      -d "$(python3 -c "import json,sys; print(json.dumps({'model':'${MODEL}','messages':[{'role':'user','content':sys.argv[1]}],'max_tokens':1024,'stream':False}))" "$PROMPT")" \
      | python3 -c "import sys,json; d=json.load(sys.stdin); c=d['choices'][0]['message']; print(c.get('content') or c.get('reasoning','')[:500])"
    ;;
  *)
    echo "Usage: $0 {status|local|cursor|hybrid|chat \"prompt\"}"
    exit 1
    ;;
esac
