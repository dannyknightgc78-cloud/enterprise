#!/usr/bin/env bash
# Nimbus — external uptime watcher (runs OUTSIDE the tunnels).
# Why internal monitors stay silent: Netdata/Grafana/n8n sit behind the same
# cloudflared path. When tunnels die, they cannot alert. Nimbus must run on
# GitHub Actions, a VPS outside Hostman, or any always-on box with public egress.
#
# Usage:
#   ./scripts/nimbus-monitor.sh
#   SLACK_WEBHOOK_URL=... ./scripts/nimbus-monitor.sh   # optional alert
#   NIMBUS_FAIL_EXIT=1 ./scripts/nimbus-monitor.sh      # exit 1 on any fail
set -uo pipefail

TIMEOUT="${TIMEOUT:-12}"
FAIL=0
OK=0
REPORT=""

check() {
  local name="$1" url="$2" expect_re="${3:-.}"
  local code body title
  body=$(mktemp)
  code=$(curl -sS -o "$body" -w '%{http_code}' --connect-timeout "$TIMEOUT" --max-time "$((TIMEOUT + 5))" "$url" 2>/dev/null || echo "000")
  title=$(tr '\n' ' ' <"$body" | sed -n 's/.*<title>\([^<]*\)<\/title>.*/\1/ip' | head -c 70)
  if [[ "$code" =~ ^(000|103|530|502|503)$ ]]; then
    REPORT+="FAIL  $name  HTTP $code  $url"$'\n'
    FAIL=$((FAIL + 1))
  elif ! grep -Iq . "$body" 2>/dev/null && [[ "$code" == "200" ]]; then
    REPORT+="FAIL  $name  empty body (txt/blank)  $url"$'\n'
    FAIL=$((FAIL + 1))
  elif [[ -n "$expect_re" && "$expect_re" != "." ]] && ! grep -Eiq "$expect_re" "$body"; then
    REPORT+="WARN  $name  HTTP $code but content mismatch (got: ${title:-none})  $url"$'\n'
    FAIL=$((FAIL + 1))
  else
    REPORT+="OK    $name  HTTP $code  ${title:-}"$'\n'
    OK=$((OK + 1))
  fi
  rm -f "$body"
}

echo "=== Nimbus external monitor ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# Dashboard / portals (Hostman direct)
check "CloudIt dashboard" "https://cloud.dannygc.cloud" "CloudIt|Sovereign|Command"
check "DannyK portal"     "https://dannyk.online" "dannyk|Cloud|Why Work"
check "Biz portal"        "https://bizportal.dannygc.cloud" "CloudIt|Business|Portal"

# GhostGrid (mysteryproject tunnel — do not strip)
check "GhostGrid"         "https://ghostgrid.dannygc.cloud" "GhostGrid|ABX|Agentic"

# Cloudsit
check "Cloudsit Video"    "https://video.cloudsit.app" "Cloudsit|Video|CloudIt"
check "Comfy"             "https://comfy.cloudsit.app" "Comfy|parked|Cloud"

# Genie / hub (tunnel)
check "Genie"             "https://genie.dannygc.cloud" "."
check "Hub"               "https://hub.dannygc.cloud" "."

# Mystery project
check "Mysteryproject"    "https://mysteryproject.dannygc.cloud" "."

echo "$REPORT"
echo "Summary: $OK ok, $FAIL failed"

if [[ "$FAIL" -gt 0 && -n "${SLACK_WEBHOOK_URL:-}" ]]; then
  payload=$(python3 - <<PY
import json, os
print(json.dumps({"text": "Nimbus alert: $FAIL site(s) down/misrouted\n$REPORT"}))
PY
)
  curl -sS -X POST -H 'Content-type: application/json' --data "$payload" "$SLACK_WEBHOOK_URL" >/dev/null || true
fi

if [[ "$FAIL" -gt 0 && "${NIMBUS_FAIL_EXIT:-0}" == "1" ]]; then
  exit 1
fi
exit 0
