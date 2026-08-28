#!/usr/bin/env bash
# One-shot permanent fix on cloudit main (Hostman 195.133.93.104) as root.
# Run via SSH or paste into Hostman web console when Cursor agent cannot reach :22.
set -euo pipefail

ROOT="${LAB_ROOT:-/root/lab-dannygc}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== permanent-fleet-fix $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
hostname
echo "IP: $(curl -sf --max-time 3 ifconfig.me 2>/dev/null || echo unknown)"

# 1) Ghosts — DNS + nginx + cloudflared ingress (Mac home-edge must NOT own ghosts DNS)
echo
echo "--- ghosts permanent route (Hostman empire tunnel) ---"
bash "${SCRIPT_DIR}/fix-ghosts-hostman.sh"

# 2) Nimbus telegram — stop reverting ghosts to dead home-edge
if [[ -f "$ROOT/scripts/lib/patch_nimbus_telegram_ghosts_hostman_fallback.py" ]]; then
  echo
  echo "--- patch nimbus telegram ghosts fallback ---"
  python3 "$ROOT/scripts/lib/patch_nimbus_telegram_ghosts_hostman_fallback.py" || echo "WARN telegram patch skipped (already applied or path missing)"
fi

# 3) Install ghosts route guard cron (every 10 min)
echo
echo "--- install ghosts guard cron ---"
CRON_LINE="*/10 * * * * LAB_ROOT=$ROOT $ROOT/scripts/hostman/guard-ghosts-routing.sh >> $HOME/lab-heal-cron.log 2>&1"
(chmod +x "$ROOT/scripts/hostman/guard-ghosts-routing.sh" 2>/dev/null || true)
tmp=$(mktemp)
crontab -l 2>/dev/null | grep -v 'guard-ghosts-routing.sh' >"$tmp" || true
echo "$CRON_LINE" >>"$tmp"
crontab "$tmp"
rm -f "$tmp"
echo "cron installed: guard-ghosts-routing every 10m"

# 4) Sync nimbus-live monitor (auto-heal ghosts on 530)
if [[ -f "$ROOT/scripts/nimbus-live/monitor.py" ]]; then
  echo
  echo "--- sync nimbus-live monitor ---"
  install -D -m 0644 "$ROOT/scripts/nimbus-live/monitor.py" /opt/nimbus-live/monitor.py
  install -D -m 0644 "$ROOT/scripts/nimbus-live/sites.json" /opt/nimbus-live/sites.json
  systemctl restart nimbus-live 2>/dev/null || systemctl restart nimbus-live.service 2>/dev/null || true
fi

# 5) Empire tunnel + nginx sanity
echo
echo "--- cloudflared + nginx ---"
systemctl is-active --quiet cloudflared || systemctl start cloudflared
nginx -t && systemctl reload nginx

# 6) Heal pass
if [[ -x "$ROOT/scripts/hostman/heal-hostman-services.sh" ]]; then
  echo
  echo "--- heal-hostman-services ---"
  bash "$ROOT/scripts/hostman/heal-hostman-services.sh" || true
fi

# 7) Key-host verification
echo
echo "--- key host check ---"
KEYS=(ghosts landing haven nimbus services hub cloud ai ghostgrid genie glucose dashboard g7 sentinel fillit portalbiz lab systems)
for h in "${KEYS[@]}"; do
  code=$(curl -sf -o /dev/null -w '%{http_code}' --max-time 12 "https://${h}.dannygc.cloud/" 2>/dev/null || echo 000)
  echo "  ${h}.dannygc.cloud → HTTP ${code}"
done

echo
echo "=== done — ghosts should be HTTP 200 on empire tunnel ==="
