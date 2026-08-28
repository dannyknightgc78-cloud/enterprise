#!/usr/bin/env bash
# Permanent ghosts route guard — Hostman only.
# Detects: local nginx serves Ghost Home (200) but public DNS → dead Mac home-edge (530).
# Action: run fix-ghosts-hostman.sh (DNS → empire tunnel, nginx + cloudflared ingress).
set -euo pipefail

ROOT="${LAB_ROOT:-/root/lab-dannygc}"
LOG="${HOME}/lab-heal-cron.log"
COOLDOWN_FILE="${HOME}/.ghosts-guard-last"
COOLDOWN_SEC="${GHOSTS_GUARD_COOLDOWN_SEC:-900}"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(ts) ghosts-guard: $*" | tee -a "$LOG"; }

local_code="$(curl -sf -o /dev/null -w '%{http_code}' -H "Host: ghosts.dannygc.cloud" --max-time 6 http://127.0.0.1/ 2>/dev/null || echo 000)"
pub_code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 12 https://ghosts.dannygc.cloud/ 2>/dev/null || echo 000)"

if [[ "$local_code" != "200" ]]; then
  log "local HTTP ${local_code} — origin issue (not DNS-only 530); skip guard"
  exit 0
fi

if [[ "$pub_code" != "530" && "$pub_code" != "103" ]]; then
  exit 0
fi

now=$(date +%s)
if [[ -f "$COOLDOWN_FILE" ]]; then
  last=$(cat "$COOLDOWN_FILE" 2>/dev/null || echo 0)
  if (( now - last < COOLDOWN_SEC )); then
    log "public ${pub_code} but cooldown active — skip"
    exit 0
  fi
fi

log "MISMATCH local=${local_code} public=${pub_code} — fixing DNS → Hostman empire tunnel"
echo "$now" > "$COOLDOWN_FILE"

if [[ -x "$ROOT/scripts/hostman/fix-ghosts-hostman.sh" ]]; then
  bash "$ROOT/scripts/hostman/fix-ghosts-hostman.sh" >>"$LOG" 2>&1 || log "WARN fix-ghosts-hostman.sh failed"
else
  log "ERROR missing $ROOT/scripts/hostman/fix-ghosts-hostman.sh"
  exit 1
fi

sleep 8
after="$(curl -sf -o /dev/null -w '%{http_code}' --max-time 15 https://ghosts.dannygc.cloud/ 2>/dev/null || echo 000)"
log "after fix public HTTP ${after}"
[[ "$after" == "200" ]]
