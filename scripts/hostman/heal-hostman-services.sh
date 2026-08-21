#!/usr/bin/env bash
# Heal Hostman cloudit1 (public origin after Vultr cutover 2026-07-30).
# Empire tunnel = systemd cloudflared (token). Ops-agent = native :8788.
# GPU peer = systemd trooper-ai-tunnel → :18000 vLLM / :11434 Ollama.
set -u
ROOT="${LAB_ROOT:-/root/lab-dannygc}"
cd "$ROOT" || exit 0

LOG="${HOME}/lab-heal-cron.log"
LOCK="${HOME}/.heal-hostman-services.lock"
exec 9>"$LOCK"
flock -n 9 || exit 0

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
log() { echo "$(ts) heal-hostman: $*" | tee -a "$LOG"; }

check() { curl -sf --max-time "${1:-5}" "$2" >/dev/null 2>&1; }

_empire_public_ok() {
  local url="$1"
  local code
  code="$(curl -sf -o /dev/null -w '%{http_code}' --max-time "${2:-8}" "$url" 2>/dev/null || echo 000)"
  [[ "$code" =~ ^(200|301|302|401|403)$ ]]
}

_heal_container() {
  local name="$1"
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name"; then
    return 0
  fi
  if ! docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$name"; then
    return 1
  fi
  log "restart container $name"
  docker start "$name" 2>/dev/null || docker restart "$name" 2>/dev/null || true
  sleep 2
  docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$name"
}

_ensure_unit() {
  local unit="$1"
  systemctl list-unit-files "${unit}.service" 2>/dev/null | grep -q "${unit}.service" || return 0
  if ! systemctl is-active --quiet "$unit"; then
    log "$unit inactive — systemctl start"
    systemctl start "$unit" >>"$LOG" 2>&1 || true
  fi
}

log "start hub=$(hostname) ip=195.133.93.104"

# Empire Cloudflare tunnel (systemd — NOT docker cloudflared-cloudme)
if ! systemctl is-active --quiet cloudflared; then
  log "cloudflared inactive — systemctl start"
  systemctl start cloudflared >>"$LOG" 2>&1 || true
fi
systemctl is-active --quiet cloudflared-mysteryproject 2>/dev/null || \
  # disabled-dupe: systemctl start cloudflared-mysteryproject >>"$LOG" 2>&1 || true

# Trooper / GPU peer SSH tunnel (vLLM :18000 vision + :18001 coder)
_ensure_unit trooper-ai-tunnel
if ! check 5 http://127.0.0.1:18000/v1/models; then
  log "vLLM :18000 down — restart trooper-ai-tunnel"
  systemctl restart trooper-ai-tunnel >>"$LOG" 2>&1 || true
  sleep 3
  check 8 http://127.0.0.1:18000/v1/models || log "WARN vLLM :18000 still down (GPU peer / SSH)"
fi
if ! check 5 http://127.0.0.1:18001/v1/models; then
  log "vLLM coder :18001 down — restart trooper-ai-tunnel"
  systemctl restart trooper-ai-tunnel >>"$LOG" 2>&1 || true
  sleep 3
  check 8 http://127.0.0.1:18001/v1/models || log "WARN vLLM :18001 still down (GPU peer / SSH)"
fi
_empire_public_ok "https://gpu.cloudsit.app/v1/models" || log "WARN gpu.cloudsit.app degraded"
_empire_public_ok "https://gpu-coder.cloudsit.app/v1/models" || log "WARN gpu-coder.cloudsit.app degraded"

# Ops-agent must be local :8788 on Hostman (do NOT flip hub/systems to :18788)
if ! check 3 http://127.0.0.1:8788/api/health; then
  log "ops-agent :8788 down — restart"
  systemctl restart ops-agent 2>/dev/null || true
  if ! check 3 http://127.0.0.1:8788/api/health; then
    pkill -f 'uvicorn server:app --host 0.0.0.0 --port 8788' 2>/dev/null || true
    sleep 1
    if [ -x "$ROOT/ops-agent/.venv/bin/uvicorn" ]; then
      cd "$ROOT/ops-agent"
      nohup .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8788 --timeout-keep-alive 5 \
        >>/var/log/ops-agent.log 2>&1 &
      sleep 2
    fi
  fi
fi

# Nimbus Telegram poll (bare process — keep alive)
if ! pgrep -f 'nimbus_telegram.py --poll' >/dev/null 2>&1; then
  log "nimbus telegram poll down — restart"
  bash "$ROOT/scripts/restart-nimbus-telegram-poll.sh" >>"$LOG" 2>&1 || true
fi

# Lead scraper (Portal Biz)
_ensure_unit lead-scraper
check 3 http://127.0.0.1:8840/health || log "WARN lead-scraper :8840 unhealthy"

# Genie middleware — circuit cooldown (do not thrash on flaps)
GENIE_CIRCUIT="${GENIE_CIRCUIT_FILE:-$ROOT/dashboard-data/ops/genie-circuit.json}"
_genie_circuit_open() {
  python3 - "$GENIE_CIRCUIT" <<'PY' 2>/dev/null
import json, sys, time
from pathlib import Path
p = Path(sys.argv[1])
try:
    doc = json.loads(p.read_text(encoding="utf-8"))
    cooldown = int(doc.get("cooldown_sec") or 900)
    last = float(doc.get("last_restart_ts") or 0)
except Exception:
    sys.exit(1)
sys.exit(0 if last and (time.time() - last) < cooldown else 1)
PY
}
_mark_genie_restart() {
  python3 - "$GENIE_CIRCUIT" <<'PY' 2>/dev/null || true
import json, sys, time
from pathlib import Path
p = Path(sys.argv[1])
doc = {"cooldown_sec": 900, "last_restart_ts": time.time(),
       "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
if p.is_file():
    try:
        old = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(old, dict):
            doc["cooldown_sec"] = int(old.get("cooldown_sec") or 900)
            doc["restart_count"] = int(old.get("restart_count") or 0) + 1
            if old.get("last_fail_ts"):
                doc["last_fail_ts"] = old["last_fail_ts"]
    except Exception:
        doc["restart_count"] = 1
else:
    doc["restart_count"] = 1
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
PY
}
if ! check 3 http://127.0.0.1:8794/api/health; then
  if _genie_circuit_open; then
    log "genie :8794 down — circuit open (cooldown) skip restart"
  else
    log "genie :8794 down — restart genie-middleware"
    systemctl restart genie-middleware >>"$LOG" 2>&1 || true
    _mark_genie_restart
  fi
fi

# Core docker product stack (Hostman origin)
for c in \
  hub-dashboard butler cyberpunk-cloud cloudit cloudme-cloudme-1 \
  queendar-portal ghostgrid-abx ghostgrid-postgres watchdog-agent \
  stratus-stratus-daemon-1 carl-whisper jellyblze-portal
do
  _heal_container "$c" || true
done

# Soft-heal genie-discord-bot if stuck in Created/Exited (optional; needs .env)
if docker ps -a --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -q '^genie-discord-bot Created'; then
  log "genie-discord-bot stuck Created — docker start"
  docker start genie-discord-bot >>"$LOG" 2>&1 || log "WARN genie-discord-bot still Created (check compose .env)"
elif docker ps -a --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -q '^genie-discord-bot Exited'; then
  log "genie-discord-bot exited — docker start"
  docker start genie-discord-bot >>"$LOG" 2>&1 || true
fi

# GhostGrid
_heal_container ghostgrid-abx || log "WARN ghostgrid-abx still down"
if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx ghostgrid-abx; then
  docker update --restart=unless-stopped ghostgrid-abx >/dev/null 2>&1 || true
fi
if ! check 4 http://127.0.0.1:8810/api/health; then
  log "ghostgrid honeypot :8810 degraded — start-ghostgrid.sh"
  bash "$ROOT/scripts/start-ghostgrid.sh" >>"$LOG" 2>&1 || true
  systemctl restart ghostgrid-honeypot >>"$LOG" 2>&1 || true
fi
if ! check 4 http://127.0.0.1:8811/api/abx/health; then
  log "ghostgrid-abx :8811 unhealthy — docker restart"
  docker restart ghostgrid-abx >>"$LOG" 2>&1 || docker start ghostgrid-abx >>"$LOG" 2>&1 || true
fi

# Hub dashboard / cloud portal
if ! check 4 "http://127.0.0.1:${HUB_DASHBOARD_HOST_PORT:-3012}/"; then
  log "hub-dashboard :3012 down — fix-cloud-portal"
  bash "$ROOT/scripts/fix-cloud-portal.sh" --local >>"$LOG" 2>&1 || true
fi

# Clinical agents (native on Hostman)
if ! check 4 http://127.0.0.1:8787/api/health || ! check 4 http://127.0.0.1:8789/api/health; then
  log "clinical agents down — heal-lab-services"
  bash "$ROOT/scripts/heal-lab-services.sh" >>"$LOG" 2>&1 || true
fi

# Protect / Aegis (:8798 native python on Hostman)
if ! check 4 http://127.0.0.1:8798/api/health; then
  log "protect/aegis :8798 down — start if present"
  systemctl restart aegis-ego-agent 2>/dev/null || \
    docker start aegis-ego-agent 2>/dev/null || true
fi

# Butler Google OAuth
if [[ -f "$ROOT/scripts/heal-butler-google.sh" ]]; then
  bash "$ROOT/scripts/heal-butler-google.sh" --notify >>"$LOG" 2>&1 || log "WARN butler-google needs reauth"
fi

# serve-lab SPA
if ! check 3 http://127.0.0.1:4173/; then
  log "serve-lab :4173 down — restart"
  systemctl restart serve-lab >>"$LOG" 2>&1 || true
fi

# ── Full empire URL sweep (public + local) from empire-public-urls.json ──
URL_CATALOG="${EMPIRE_URL_CATALOG:-$ROOT/dashboard-data/ops/empire-public-urls.json}"
_probe_catalog() {
  local tier_filter="${1:-}"
  python3 - "$URL_CATALOG" "$tier_filter" <<'PY' 2>/dev/null || true
import json, sys, urllib.request, ssl
from pathlib import Path
path, want = sys.argv[1], sys.argv[2]
doc = json.loads(Path(path).read_text(encoding="utf-8"))
ctx = ssl.create_default_context()
fail_required = []
for site in doc.get("sites") or []:
    tier = str(site.get("tier") or "optional")
    if want and tier != want:
        continue
    sid = site.get("id") or "?"
    for kind in ("local", "public"):
        url = site.get(kind)
        if not url:
            continue
        ok = False
        try:
            req = urllib.request.Request(url, method="GET", headers={"User-Agent": "heal-hostman/catalog"})
            with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
                ok = 200 <= int(r.status) < 500
        except Exception as e:
            code = getattr(e, "code", None)
            ok = code in (401, 403, 404) and kind == "public" and sid in {"lab-services"}
            if code in (200, 301, 302, 401, 403):
                ok = True
        mark = "OK" if ok else "FAIL"
        print(f"{mark}\t{tier}\t{kind}\t{sid}\t{url}")
        if not ok and tier == "required" and kind == "public":
            fail_required.append(sid)
if fail_required:
    print("REQUIRED_PUBLIC_FAIL\t" + ",".join(sorted(set(fail_required))))
    sys.exit(1)
sys.exit(0)
PY
}

log "empire URL catalog probe"
CATALOG_OUT="$(_probe_catalog || true)"
echo "$CATALOG_OUT" | while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  case "$line" in
    FAIL*) log "WARN $line" ;;
    REQUIRED_PUBLIC_FAIL*) log "empire required public fail: ${line#*$'\t'}" ;;
  esac
done

# Queen / Queendar portal + IDE (Hostman :3011)
if ! check 4 http://127.0.0.1:3011/; then
  log "queendar :3011 down — restart container"
  docker start queendar-portal >>"$LOG" 2>&1 || docker restart queendar-portal >>"$LOG" 2>&1 || true
fi
_empire_public_ok "https://queendar.dannygc.cloud/" || log "WARN queendar.dannygc.cloud degraded"
_empire_public_ok "https://queendar.cloudsit.app/" || log "WARN queendar.cloudsit.app degraded"

# Mysteryproject (separate tunnel + cyberpunk :3000)
if ! check 4 http://127.0.0.1:3000/; then
  log "cyberpunk/mystery :3000 down — restart"
  docker start cyberpunk-cloud >>"$LOG" 2>&1 || docker restart cyberpunk-cloud >>"$LOG" 2>&1 || true
  # disabled-dupe: systemctl restart cloudflared-mysteryproject >>"$LOG" 2>&1 || true
fi
_empire_public_ok "https://mysteryproject.org/" || log "WARN mysteryproject.org degraded"

# Jellyblaze
if ! check 4 http://127.0.0.1:8815/api/health; then
  log "jellyblaze :8815 down — restart"
  docker start jellyblze-portal >>"$LOG" 2>&1 || docker restart jellyblze-portal >>"$LOG" 2>&1 || true
fi
_empire_public_ok "https://jellyblaze.cloudsit.app/api/health" || log "WARN jellyblaze degraded"

# GPU public (via Hostman tunnel → cloudit-gpu)
if ! check 5 http://127.0.0.1:18001/v1/models; then
  log "gpu-coder tunnel :18001 down — restart trooper-ai-tunnel"
  systemctl restart trooper-ai-tunnel >>"$LOG" 2>&1 || true
fi
if ! check 5 http://127.0.0.1:18000/v1/models; then
  log "gpu-vl tunnel :18000 down — restart trooper-ai-tunnel"
  systemctl restart trooper-ai-tunnel >>"$LOG" 2>&1 || true
fi
_empire_public_ok "https://gpu-coder.cloudsit.app/v1/models" || log "WARN gpu-coder public degraded"
_empire_public_ok "https://gpu-vl.cloudsit.app/v1/models" || log "WARN gpu-vl public degraded"

# Public empire core — restart tunnel if hub/systems/glucose fail
if ! _empire_public_ok "https://glucose.dannygc.cloud/api/health" \
  || ! _empire_public_ok "https://hub.dannygc.cloud/" \
  || ! _empire_public_ok "https://systems.dannygc.cloud/" \
  || ! _empire_public_ok "https://lab.dannygc.cloud/services"; then
  log "public empire degraded — ensure cloudflared active + nginx reload"
  if ! systemctl is-active --quiet cloudflared; then
    systemctl start cloudflared >>"$LOG" 2>&1 || true
  else
    log "cloudflared already active — skip restart (avoid max-restart spam)"
  fi
  sleep 3
  nginx -t >>"$LOG" 2>&1 && systemctl reload nginx >>"$LOG" 2>&1 || true
  bash "$ROOT/scripts/lib/log-nimbus-outcome.sh" \
    --fix-action "heal-hostman:empire-degraded" \
    --success 1 \
    --category tunnel \
    --signature "530|1033|glucose.dannygc.cloud|hostman-cloudflared" \
    --source heal \
    --notes "Hostman systemd cloudflared restart + nginx reload" 2>/dev/null || true
fi

_empire_public_ok "https://lab.dannygc.cloud/" || log "WARN lab.dannygc.cloud degraded"
_empire_public_ok "https://glucose.dannyk.online/api/health" || log "WARN glucose.dannyk.online degraded"
_empire_public_ok "https://ghosts.dannygc.cloud/api/health" || log "WARN ghosts.dannygc.cloud degraded (Mac home-edge)"
_empire_public_ok "https://fillit.dannygc.cloud/" || log "WARN fillit degraded"
_empire_public_ok "https://cloudme.cloudsit.app/" || log "WARN cloudme degraded"
# nimbus-excluded: leads.cloudsit.app (not in Nimbus)
_empire_public_ok "https://portalbiz.dannygc.cloud/" || log "WARN portalbiz degraded"
_empire_public_ok "https://cloudit.cloudsit.app/" || log "WARN cloudit degraded"
_empire_public_ok "https://stratus.dannygc.cloud/" || log "WARN stratus degraded"
_empire_public_ok "https://speakit.dannygc.cloud/" || log "WARN speakit degraded"
_empire_public_ok "https://carl.dannygc.cloud/" || log "WARN carl degraded"
_empire_public_ok "https://haven.dannygc.cloud/" || log "WARN haven degraded"
_empire_public_ok "https://search.dannygc.cloud/" || log "WARN search degraded"
_empire_public_ok "https://sentinel.dannygc.cloud/" || log "WARN sentinel degraded"
_empire_public_ok "https://timesaver.dannygc.cloud/" || log "WARN timesaver degraded"
_empire_public_ok "https://requests.dannygc.cloud/" || log "WARN requests/jellyseerr degraded"
_empire_public_ok "https://watch.dannygc.cloud/" || log "WARN watch degraded"
_empire_public_ok "https://protect.dannygc.cloud/" || log "WARN protect degraded"
_empire_public_ok "https://home.dannygc.cloud/" || log "WARN home degraded"
_empire_public_ok "https://dannyk.online/" || log "WARN dannyk.online degraded"

bash "$ROOT/scripts/guard-stack-integrity.sh" --fix >>"$LOG" 2>&1 || true

log "done"
exit 0
