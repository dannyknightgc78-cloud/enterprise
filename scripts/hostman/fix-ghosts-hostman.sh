#!/usr/bin/env bash
# Fix ghosts.dannygc.cloud 530/1033 — PERMANENT route via Hostman empire tunnel.
# Mac home-edge (518d4da0…) must NOT own ghosts DNS when Mac is offline.
# Run on cloudit main (Hostman 195.133.93.104) as root, or use fix-ghosts-dns-remote.sh for DNS-only.
set -euo pipefail

HOSTMAN_TUNNEL_ID="${HOSTMAN_TUNNEL_ID:-8cc6cd76-7f80-449e-b93f-2df400129dd1}"
HOME_EDGE_TUNNEL_ID="${HOME_EDGE_TUNNEL_ID:-518d4da0-ca44-4df1-a759-6a2941c61d4f}"
TARGET="${HOSTMAN_TUNNEL_ID}.cfargotunnel.com"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${LAB_ROOT:-/root/lab-dannygc}"
CF_CONFIG="${CF_CONFIG:-/etc/cloudflared/config.yml}"

load_token() {
  CF_API_TOKEN="${CF_API_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}"
  if [[ -n "${CF_API_TOKEN:-}" ]]; then
    return 0
  fi
  for p in /root/lab-dannygc/secrets/lab-vault.env /root/lab-dannygc/.env; do
    [[ -f "$p" ]] || continue
    # shellcheck disable=SC1090
    set -a; source "$p"; set +a
    CF_API_TOKEN="${CF_API_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}"
    break
  done
  [[ -n "${CF_API_TOKEN:-}" ]] || { echo "Need CF_API_TOKEN in env or lab-vault.env"; exit 1; }
}

fix_dns() {
  local zid resp id
  zid=$(curl -sS -H "Authorization: Bearer ${CF_API_TOKEN}" \
    "https://api.cloudflare.com/client/v4/zones?name=dannygc.cloud" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"][0]["id"])')
  resp=$(curl -sS -H "Authorization: Bearer ${CF_API_TOKEN}" \
    "https://api.cloudflare.com/client/v4/zones/${zid}/dns_records?name=ghosts.dannygc.cloud")
  id=$(echo "$resp" | python3 -c 'import sys,json; r=json.load(sys.stdin).get("result") or []; print(r[0]["id"] if r else "")')
  current=$(echo "$resp" | python3 -c 'import sys,json; r=json.load(sys.stdin).get("result") or []; print(r[0].get("content","") if r else "")')
  if [[ "$current" == *"${HOME_EDGE_TUNNEL_ID}"* ]]; then
    echo "WARN: ghosts DNS was on dead Mac home-edge — repointing to Hostman"
  fi
  body=$(python3 - <<PY
import json
print(json.dumps({
  "type": "CNAME",
  "name": "ghosts",
  "content": "${TARGET}",
  "proxied": True,
  "ttl": 1,
  "comment": "PERMANENT Hostman empire tunnel — Ghost Home fallback"
}))
PY
)
  if [[ -n "$id" ]]; then
    curl -sS -X PUT -H "Authorization: Bearer ${CF_API_TOKEN}" -H "Content-Type: application/json" \
      "https://api.cloudflare.com/client/v4/zones/${zid}/dns_records/${id}" --data "$body" \
      | python3 -c 'import sys,json; d=json.load(sys.stdin); print("DNS updated", d.get("success")); sys.exit(0 if d.get("success") else 1)'
  else
    curl -sS -X POST -H "Authorization: Bearer ${CF_API_TOKEN}" -H "Content-Type: application/json" \
      "https://api.cloudflare.com/client/v4/zones/${zid}/dns_records" --data "$body" \
      | python3 -c 'import sys,json; d=json.load(sys.stdin); print("DNS created", d.get("success")); sys.exit(0 if d.get("success") else 1)'
  fi
  echo "ghosts → ${TARGET}"
}

install_ghost_home() {
  local src="${SCRIPT_DIR}/ghost-home"
  [[ -d "$src" ]] || src="${ROOT}/scripts/hostman/ghost-home"
  if [[ -d "$src" ]]; then
    mkdir -p /var/www/ghost-home
    install -m 0644 "${src}/index.html" /var/www/ghost-home/index.html
    install -m 0644 "${src}/health.json" /var/www/ghost-home/health.json
    echo "ghost-home static files installed"
  elif [[ ! -d /var/www/ghost-home ]]; then
    echo "Missing /var/www/ghost-home and no repo bundle — restore backup"
    exit 1
  fi
}

fix_nginx() {
  install -D -m 0644 "${SCRIPT_DIR}/ghosts.dannygc.cloud.conf" /etc/nginx/sites-available/ghosts.dannygc.cloud.conf
  ln -sfn /etc/nginx/sites-available/ghosts.dannygc.cloud.conf /etc/nginx/sites-enabled/ghosts.dannygc.cloud.conf
  disabled="/etc/nginx/sites-available/ghosts.dannygc.cloud.conf.disabled-ghosthome-20260820"
  [[ -f "$disabled" && ! -f /etc/nginx/sites-available/ghosts.dannygc.cloud.conf ]] && mv "$disabled" /etc/nginx/sites-available/ghosts.dannygc.cloud.conf
  install_ghost_home
  nginx -t
  systemctl reload nginx
  echo "nginx ghosts vhost enabled"
}

fix_tunnel_ingress() {
  [[ -f "$CF_CONFIG" ]] || { echo "WARN: no $CF_CONFIG — skip ingress patch"; return 0; }
  if grep -q "hostname: ghosts.dannygc.cloud" "$CF_CONFIG"; then
    echo "cloudflared ingress already has ghosts"
  else
    cp -a "$CF_CONFIG" "${CF_CONFIG}.bak.ghosts-$(date +%Y%m%d%H%M%S)"
    python3 - <<PY
from pathlib import Path
path = Path("${CF_CONFIG}")
text = path.read_text()
rule = "  - hostname: ghosts.dannygc.cloud\n    service: http://127.0.0.1:80\n"
if "ingress:" not in text:
    raise SystemExit("no ingress: block in config")
lines = text.splitlines(keepends=True)
out = []
inserted = False
for i, line in enumerate(lines):
    out.append(line)
    if not inserted and line.strip() == "ingress:":
        # insert after ingress: header
        out.append(rule)
        inserted = True
if not inserted:
    raise SystemExit("failed to patch ingress")
path.write_text("".join(out))
print("added ghosts.dannygc.cloud ingress rule")
PY
    echo "cloudflared config patched — reloading"
  fi
  systemctl is-active --quiet cloudflared || systemctl restart cloudflared
  systemctl reload cloudflared 2>/dev/null || systemctl restart cloudflared
}

verify() {
  local code pub
  code=$(curl -sS -o /dev/null -w '%{http_code}' -H "Host: ghosts.dannygc.cloud" http://127.0.0.1/ || echo 000)
  echo "local nginx: HTTP ${code}"
  sleep 8
  pub=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 25 https://ghosts.dannygc.cloud/ || echo 000)
  echo "public: HTTP ${pub}"
  [[ "$pub" == "200" ]]
}

main() {
  load_token
  fix_dns
  fix_nginx
  fix_tunnel_ingress
  verify
}

main "$@"
