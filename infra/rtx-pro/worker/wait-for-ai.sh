#!/usr/bin/env bash
# Wait until RTX AI is reachable (Ollama local, NIM, or tunnel on same box).
set -euo pipefail

wait_for_rtx_ai() {
  local i
  for i in $(seq 1 30); do
    curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && return 0
    curl -sf http://127.0.0.1:8000/v1/models >/dev/null 2>&1 && return 0
    curl -sf http://127.0.0.1:18001/v1/models >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "WARN: local AI not on :11434/:8000/:18001 — continuing (tunnel may still serve ai.dannygc.cloud)" >&2
  return 0
}

wait_for_rtx_ai
