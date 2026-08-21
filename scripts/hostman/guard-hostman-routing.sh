#!/usr/bin/env bash
# Detect + auto-fix misrouted cloud/dashboard portals.
# Works on host and inside watchdog container (no curl required).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIX="${1:-}"
LOG="${HOME}/lab-heal-cron.log"
ORIGIN="${ROUTE_GUARD_ORIGIN:-http://195.133.93.104}"
ORIGIN="${ORIGIN%/}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(ts) route-guard: $*" | tee -a "$LOG"; }

HUB_PORT="${HUB_DASHBOARD_HOST_PORT:-3012}"
CLOUDIT_PORT="${CLOUDIT_HOST_PORT:-8816}"
BAD_RE='mysteryproject|BUTLER[[:space:]]*//[[:space:]]*neural relay|cloud me ☁'
HUB_GOOD_RE='DANNYGC Hub|DannyGC Hub|hub-dashboard|Photobooth'
CLOUD_GOOD_RE='CloudIt|Sovereign Command Centre'
HUB_VHOST_FILES=(
  /etc/nginx/sites-available/hub.dannygc.cloud
  /etc/nginx/sites-available/hub.dannygc.cloud.conf
  "$ROOT/nginx/hub.dannygc.cloud.conf"
)

_http_get() {
  local url="$1"
  local host_header="${2:-}"
  if command -v curl >/dev/null 2>&1; then
    if [ -n "$host_header" ]; then
      curl -sS --max-time 10 -A "Mozilla/5.0 NimbusRouteGuard/1.2" -H "Host: ${host_header}" "$url" 2>/dev/null | head -c 1200 || true
    else
      curl -sS --max-time 12 -A "Mozilla/5.0 NimbusRouteGuard/1.2" "$url" 2>/dev/null | head -c 1200 || true
    fi
    return 0
  fi
  ORIGIN_URL="$url" ORIGIN_HOST="$host_header" python3 - <<'PY'
import os, urllib.request
url = os.environ["ORIGIN_URL"]
host = os.environ.get("ORIGIN_HOST") or ""
headers = {"User-Agent": "Mozilla/5.0 NimbusRouteGuard/1.2", "Accept": "text/html"}
if host:
    headers["Host"] = host
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as res:
        print(res.read(1200).decode("utf-8", "ignore"), end="")
except Exception:
    pass
PY
}

_fetch() {
  local host="$1"
  local body
  body="$(_http_get "${ORIGIN}/" "$host")"
  if [ -z "$body" ]; then
    body="$(_http_get "https://${host}/" "")"
  fi
  printf '%s' "$body"
}

_route_ok() {
  local host="$1"
  local expect="$2"
  local body
  body="$(_fetch "$host")"
  if [ -z "$body" ]; then
    return 1
  fi
  if echo "$body" | grep -qiE "$BAD_RE"; then
    return 1
  fi
  echo "$body" | grep -qiE "$expect"
}

_nginx_ok() {
  local cloud="/etc/nginx/sites-available/cloud.dannygc.cloud.conf"
  local dash="/etc/nginx/sites-available/dashboard.dannygc.cloud.conf"
  if [ ! -f "$cloud" ] || [ ! -f "$dash" ]; then
    return 0
  fi
  grep -q "127.0.0.1:${CLOUDIT_PORT}" "$cloud" || return 1
  grep -q "127.0.0.1:${HUB_PORT}" "$dash" || return 1
  grep -qE '10\.0\.1\.9:3000|:3010;' "$cloud" && return 1
  grep -qE '10\.0\.1\.9:3000|:3010;' "$dash" && return 1
  grep -q "127.0.0.1:${HUB_PORT}" "$cloud" && return 1
  return 0
}

_hub_vhost_ok() {
  local f
  for f in "${HUB_VHOST_FILES[@]}"; do
    [ -f "$f" ] || continue
    if grep -E 'location[[:space:]]+/[[:space:]]*\{' -A12 "$f" 2>/dev/null | grep -qE "127\.0\.0\.1:${HUB_PORT}|localhost:${HUB_PORT}"; then
      if grep -E 'location[[:space:]]+/[[:space:]]*\{' -A12 "$f" 2>/dev/null | grep -qE '14173|:4173'; then
        return 1
      fi
      return 0
    fi
    if grep -q "127.0.0.1:${HUB_PORT}" "$f" && ! grep -qE 'proxy_pass[[:space:]]+http://127\.0\.0\.1:14173' "$f"; then
      return 0
    fi
  done
  return 0
}

_hub_running() {
  docker ps --format '{{.Names}}' 2>/dev/null | grep -qx hub-dashboard
}

issues=()
if ! _hub_running; then
  issues+=("hub-dashboard container down")
fi
if ! _nginx_ok; then
  issues+=("nginx cloud not :${CLOUDIT_PORT} or dashboard not :${HUB_PORT}")
fi
if ! _hub_vhost_ok; then
  issues+=("hub.dannygc.cloud UI not on :${HUB_PORT} (must not be :14173)")
fi
if ! _route_ok cloud.dannygc.cloud "$CLOUD_GOOD_RE"; then
  issues+=("cloud.dannygc.cloud serving wrong app (want CloudIt)")
fi
if ! _route_ok dashboard.dannygc.cloud "$HUB_GOOD_RE"; then
  issues+=("dashboard.dannygc.cloud serving wrong app (want Hub)")
fi

if [ "${#issues[@]}" -eq 0 ]; then
  exit 0
fi

log "DEGRADED: ${issues[*]}"

if [ "$FIX" = "--fix" ]; then
  log "running fix-cloud-portal.sh --local"
  if [ -f /etc/nginx/sites-available/cloud.dannygc.cloud.conf ] && [ -x "$ROOT/scripts/fix-cloud-portal.sh" ]; then
    bash "$ROOT/scripts/fix-cloud-portal.sh" --local >>"$LOG" 2>&1 || true
    sleep 4
  else
    log "skip host nginx fix in this environment"
  fi
  if _hub_running \
      && _route_ok cloud.dannygc.cloud "$CLOUD_GOOD_RE" \
      && _route_ok dashboard.dannygc.cloud "$HUB_GOOD_RE"; then
    log "recovered cloud (CloudIt) + dashboard (Hub) routing"
    exit 0
  fi
  log "WARN routing still degraded after fix"
  exit 1
fi

exit 1
