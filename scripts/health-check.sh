#!/usr/bin/env bash
# External health probe for DannyGC / Cloudit services.
# Runs OUTSIDE your network so it still works when cloudflared is down.
set -uo pipefail

TIMEOUT="${TIMEOUT:-10}"
FAIL=0
WARN=0

check() {
  local name="$1" url="$2"
  local host code dns

  host="${url#https://}"
  host="${host#http://}"
  host="${host%%/*}"

  dns=$(dig +short A "$host" 2>/dev/null | head -1)
  if [[ -z "$dns" ]]; then
    echo "FAIL  $name  ($host)  DNS: NXDOMAIN — no A record"
    FAIL=$((FAIL + 1))
    return
  fi

  code=$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout "$TIMEOUT" --max-time "$((TIMEOUT + 5))" "$url" 2>/dev/null || echo "000")

  case "$code" in
    000) echo "FAIL  $name  ($host → $dns)  UNREACHABLE"; FAIL=$((FAIL + 1)) ;;
    103|530|502|503)
      echo "FAIL  $name  ($host → $dns)  HTTP $code — tunnel/origin down (Cloudflare 1033/530)"
      FAIL=$((FAIL + 1))
      ;;
    404)
      echo "WARN  $name  ($host → $dns)  HTTP 404 — DNS ok but no route/origin"
      WARN=$((WARN + 1))
      ;;
    2*|3*)
      echo "OK    $name  ($host → $dns)  HTTP $code"
      ;;
    *)
      echo "WARN  $name  ($host → $dns)  HTTP $code"
      WARN=$((WARN + 1))
      ;;
  esac
}

echo "=== DannyGC / Cloudit external health check ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# Portal & hub
check "Cloud Portal"      "https://cloud.dannygc.cloud"
check "Hub"               "https://hub.dannygc.cloud"
check "Main site"         "https://dannygc.cloud"

# AI stack + GhostGrid (urgent)
check "GhostGrid"         "https://ghostgrid.dannygc.cloud"
check "GhostGrid warroom" "https://ghostgrid.dannygc.cloud/warroom"
check "Ollama / AI"       "https://ai.dannygc.cloud"
check "Ollama API"        "https://ollama.dannygc.cloud"
check "API gateway"       "https://api.dannygc.cloud"
check "Genie PWA"         "https://genie.dannygc.cloud"

# Dev tools
check "VS Code"           "https://code.dannygc.cloud"
check "Files"             "https://files.dannygc.cloud"
check "Monitor (Netdata)" "https://monitor.dannygc.cloud"
check "Portainer"         "https://portainer.dannygc.cloud"
check "Grafana"           "https://grafana.dannygc.cloud"
check "n8n"               "https://n8n.dannygc.cloud"
check "Photos"            "https://photos.dannygc.cloud"

# Cloudit GPU
check "Cloudit Video"     "https://video.cloudsit.app"
check "Cloudit Comfy"     "https://comfy.cloudsit.app"

# Other
check "Kasm browser"      "https://kasm.dannyk.online/"

echo
echo "Summary: $FAIL failed, $WARN warnings"
if [[ "$FAIL" -gt 0 ]]; then
  echo
  echo "Likely cause: cloudflared tunnel down on origin server (Cloudflare error 1033/530)."
  echo "Recovery (run ON THE ORIGIN SERVER, not here):"
  echo "  sudo systemctl status cloudflared"
  echo "  sudo journalctl -u cloudflared -n 50 --no-pager"
  echo "  sudo systemctl restart cloudflared"
  echo "  cloudflared tunnel list"
  echo "Also check Cloudflare Zero Trust → Networks → Connectors for tunnel status."
  exit 1
fi
exit 0
