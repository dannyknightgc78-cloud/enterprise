#!/usr/bin/env bash
# Fix ghosts.dannygc.cloud DNS from anywhere (Cloud Agent, laptop, CI).
# Does NOT need SSH to Hostman — only Cloudflare API token with Zone.DNS Edit.
#
#   export CF_API_TOKEN=...
#   bash scripts/fix-ghosts-dns-remote.sh
set -euo pipefail

HOSTMAN_TUNNEL_ID="${HOSTMAN_TUNNEL_ID:-8cc6cd76-7f80-449e-b93f-2df400129dd1}"
TARGET="${HOSTMAN_TUNNEL_ID}.cfargotunnel.com"
CF_API_TOKEN="${CF_API_TOKEN:-${CLOUDFLARE_API_TOKEN:-}}"
: "${CF_API_TOKEN:?Set CF_API_TOKEN or CLOUDFLARE_API_TOKEN}"

API="https://api.cloudflare.com/client/v4"
AUTH=(-H "Authorization: Bearer ${CF_API_TOKEN}" -H "Content-Type: application/json")

zid=$(curl -sS "${AUTH[@]}" "${API}/zones?name=dannygc.cloud" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["result"][0]["id"])')

resp=$(curl -sS "${AUTH[@]}" "${API}/zones/${zid}/dns_records?name=ghosts.dannygc.cloud")
echo "Current DNS:"
echo "$resp" | python3 -c 'import sys,json; [print(r) for r in json.load(sys.stdin).get("result") or []]' || true

id=$(echo "$resp" | python3 -c 'import sys,json; r=json.load(sys.stdin).get("result") or []; print(r[0]["id"] if r else "")')
body=$(python3 - <<PY
import json
print(json.dumps({
  "type": "CNAME",
  "name": "ghosts",
  "content": "${TARGET}",
  "proxied": True,
  "ttl": 1,
  "comment": "PERMANENT Hostman empire tunnel — Ghost Home fallback (not Mac home-edge)"
}))
PY
)

if [[ -n "$id" ]]; then
  curl -sS -X PUT "${AUTH[@]}" "${API}/zones/${zid}/dns_records/${id}" --data "$body" \
    | python3 -m json.tool
else
  curl -sS -X POST "${AUTH[@]}" "${API}/zones/${zid}/dns_records" --data "$body" \
    | python3 -m json.tool
fi

echo "ghosts.dannygc.cloud → ${TARGET}"
echo "Waiting 15s for propagation..."
sleep 15
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 https://ghosts.dannygc.cloud/ || echo 000)
echo "Public check: HTTP ${code}"
[[ "$code" == "200" ]]
