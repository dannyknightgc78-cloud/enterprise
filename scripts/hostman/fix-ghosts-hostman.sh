#!/usr/bin/env bash
# Fix ghosts.dannygc.cloud 530/1033 — route to Hostman empire tunnel, not dead Mac home-edge.
# Run on cloudit main (Hostman 195.133.93.104) as root.
set -euo pipefail

HOSTMAN_TUNNEL_ID="${HOSTMAN_TUNNEL_ID:-8cc6cd76-7f80-449e-b93f-2df400129dd1}"
TARGET="${HOSTMAN_TUNNEL_ID}.cfargotunnel.com"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

load_token() {
  for p in /root/lab-dannygc/secrets/lab-vault.env /root/lab-dannygc/.env; do
    [[ -f "$p" ]] || continue
    # shellcheck disable=SC1090
    set -a; source "$p"; set +a
    break
  done
  CF_API_TOKEN="${CF_API_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}"
  [[ -n "${CF_API_TOKEN:-}" ]] || { echo "Need CF_API_TOKEN or CLOUDFLARE_API_TOKEN in lab-vault.env"; exit 1; }
}

fix_dns() {
  local zid resp id
  zid=$(curl -sS -H "Authorization: Bearer ${CF_API_TOKEN}" \
    "https://api.cloudflare.com/client/v4/zones?name=dannygc.cloud" \
    | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"][0]["id"])')
  resp=$(curl -sS -H "Authorization: Bearer ${CF_API_TOKEN}" \
    "https://api.cloudflare.com/client/v4/zones/${zid}/dns_records?name=ghosts.dannygc.cloud")
  id=$(echo "$resp" | python3 -c 'import sys,json; r=json.load(sys.stdin).get("result") or []; print(r[0]["id"] if r else "")')
  body=$(python3 - <<PY
import json
print(json.dumps({
  "type": "CNAME",
  "name": "ghosts",
  "content": "${TARGET}",
  "proxied": True,
  "ttl": 1,
  "comment": "Hostman empire tunnel — Ghost Home fallback"
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

fix_nginx() {
  install -D -m 0644 "${SCRIPT_DIR}/ghosts.dannygc.cloud.conf" /etc/nginx/sites-available/ghosts.dannygc.cloud.conf
  ln -sfn /etc/nginx/sites-available/ghosts.dannygc.cloud.conf /etc/nginx/sites-enabled/ghosts.dannygc.cloud.conf
  # undo disable from old fix-ghosts-home
  disabled="/etc/nginx/sites-available/ghosts.dannygc.cloud.conf.disabled-ghosthome-20260820"
  [[ -f "$disabled" && ! -f /etc/nginx/sites-available/ghosts.dannygc.cloud.conf ]] && mv "$disabled" /etc/nginx/sites-available/ghosts.dannygc.cloud.conf
  [[ -d /var/www/ghost-home ]] || { echo "Missing /var/www/ghost-home — restore from backup"; exit 1; }
  nginx -t
  systemctl reload nginx
  echo "nginx ghosts vhost enabled"
}

fix_tunnel_ingress() {
  if grep -q "hostname: ghosts.dannygc.cloud" /etc/cloudflared/config.yml; then
    echo "cloudflared ingress already has ghosts"
  else
    echo "WARN: add ghosts.dannygc.cloud to /etc/cloudflared/config.yml ingress"
  fi
  systemctl is-active --quiet cloudflared || systemctl restart cloudflared
}

verify() {
  code=$(curl -sS -o /dev/null -w '%{http_code}' -H "Host: ghosts.dannygc.cloud" http://127.0.0.1/ || echo 000)
  echo "local nginx: HTTP ${code}"
  sleep 5
  pub=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 https://ghosts.dannygc.cloud/ || echo 000)
  echo "public: HTTP ${pub}"
}

main() {
  load_token
  fix_dns
  fix_nginx
  fix_tunnel_ingress
  verify
}

main "$@"
