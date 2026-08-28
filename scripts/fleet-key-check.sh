#!/usr/bin/env bash
# Quick external probe of empire-critical hostnames.
set -uo pipefail

TIMEOUT="${TIMEOUT:-12}"
FAIL=0
WARN=0

check() {
  local name="$1" url="$2" expect="${3:-}"
  local code title body

  code=$(curl -sS -o /tmp/fleet-body.html -w '%{http_code}' --max-time "$TIMEOUT" "$url" 2>/dev/null || echo "000")
  title=$(grep -oiP '(?<=<title>)[^<]+' /tmp/fleet-body.html 2>/dev/null | head -1 || true)

  case "$code" in
    000) echo "FAIL  $name  UNREACHABLE"; FAIL=$((FAIL + 1)) ;;
    103|530|502|503)
      echo "FAIL  $name  HTTP $code (tunnel/DNS)"
      FAIL=$((FAIL + 1))
      ;;
    404)
      echo "WARN  $name  HTTP 404"
      WARN=$((WARN + 1))
      ;;
    2*|3*)
      if [[ -n "$expect" && ! "$title" =~ $expect ]]; then
        echo "WARN  $name  HTTP $code title='$title' (expect $expect)"
        WARN=$((WARN + 1))
      else
        echo "OK    $name  HTTP $code${title:+ title=$title}"
      fi
      ;;
    *)
      echo "WARN  $name  HTTP $code"
      WARN=$((WARN + 1))
      ;;
  esac
}

echo "=== Fleet key check $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo

check "Ghosts Home"    "https://ghosts.dannygc.cloud/"     "Ghost Home"
check "Landing"        "https://landing.dannygc.cloud/"    "Portal Biz|Business Suite"
check "Haven"          "https://haven.dannygc.cloud/"      "Haven"
check "Nimbus"         "https://nimbus.dannygc.cloud/"     "Nimbus|Empire Monitor"
check "Services"       "https://services.dannygc.cloud/" "Nimbus|Empire Monitor"
check "Cloud Portal"   "https://cloud.dannygc.cloud/"     "CloudIt"
check "Hub"            "https://hub.dannygc.cloud/"       "Hub|Command"
check "Dashboard"      "https://dashboard.dannygc.cloud/" "Hub|Photobooth|Command"
check "AI"             "https://ai.dannygc.cloud/"        "."
check "GhostGrid"      "https://ghostgrid.dannygc.cloud/" "GhostGrid|ABX"
check "Genie"          "https://genie.dannygc.cloud/"     "Genie"
check "Glucose"        "https://glucose.dannygc.cloud/"   "."
check "Sentinel"       "https://sentinel.dannygc.cloud/" "."
check "Fillit"         "https://fillit.dannygc.cloud/"    "."
check "Portal Biz"     "https://portalbiz.dannygc.cloud/" "."
check "Lab"            "https://lab.dannygc.cloud/"       "."
check "Systems"        "https://systems.dannygc.cloud/"   "."
check "G7"             "https://g7.dannygc.cloud/"        "."
check "Main apex"      "https://dannygc.cloud/"           "."

echo
echo "Summary: $FAIL failed, $WARN warnings"
exit $([[ "$FAIL" -eq 0 ]] && echo 0 || echo 1)
