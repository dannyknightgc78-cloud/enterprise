#!/usr/bin/env bash
# Full DNS reset for DannyGC / Cloudit / GhostGrid tunnel hostnames.
# Requires Cloudflare API token with Zone.DNS Edit on dannygc.cloud, cloudsit.app, dannyk.online.
#
# Required env:
#   CF_API_TOKEN   — Cloudflare API token
#   TUNNEL_ID      — primary Cloudflare Tunnel UUID (RTX / Hostman AI tunnel)
#
# Optional:
#   TUNNEL_ID_KASM — separate tunnel UUID for kasm.dannyk.online (defaults to TUNNEL_ID)
#   DRY_RUN=1      — print actions only
set -euo pipefail

: "${CF_API_TOKEN:?Set CF_API_TOKEN}"
: "${TUNNEL_ID:?Set TUNNEL_ID (from cloudflared credentials or Zero Trust → Connectors)}"

TUNNEL_ID_KASM="${TUNNEL_ID_KASM:-$TUNNEL_ID}"
API="https://api.cloudflare.com/client/v4"
AUTH=(-H "Authorization: Bearer ${CF_API_TOKEN}" -H "Content-Type: application/json")
DRY_RUN="${DRY_RUN:-0}"

cf() {
  curl -sS "${AUTH[@]}" "$@"
}

zone_id() {
  local name="$1"
  cf "${API}/zones?name=${name}" | python3 -c 'import sys,json; d=json.load(sys.stdin); r=d.get("result") or []; print(r[0]["id"] if r else "")'
}

upsert_cname() {
  local zone="$1" name="$2" target="$3" proxied="${4:-true}"
  local zid
  zid=$(zone_id "$zone")
  if [[ -z "$zid" ]]; then
    echo "FAIL  zone not found: $zone"
    return 1
  fi

  local existing id typ
  existing=$(cf "${API}/zones/${zid}/dns_records?name=${name}" )
  id=$(echo "$existing" | python3 -c 'import sys,json; r=(json.load(sys.stdin).get("result") or [None])[0]; print(r["id"] if r else "")')
  typ=$(echo "$existing" | python3 -c 'import sys,json; r=(json.load(sys.stdin).get("result") or [None])[0]; print(r["type"] if r else "")')

  local body
  body=$(python3 - <<PY
import json
print(json.dumps({
  "type": "CNAME",
  "name": "$name",
  "content": "$target",
  "ttl": 1,
  "proxied": $([[ "$proxied" == "true" ]] && echo true || echo false),
  "comment": "enterprise dns-reset $(date -u +%Y-%m-%dT%H:%MZ)"
}))
PY
)

  if [[ "$DRY_RUN" == "1" ]]; then
    if [[ -n "$id" ]]; then
      echo "DRY   UPDATE $name → $target (was $typ id=$id)"
    else
      echo "DRY   CREATE $name → $target"
    fi
    return 0
  fi

  # Replace incompatible record types (A/AAAA) with CNAME
  if [[ -n "$id" && "$typ" != "CNAME" ]]; then
    cf -X DELETE "${API}/zones/${zid}/dns_records/${id}" >/dev/null
    id=""
  fi

  local resp ok
  if [[ -n "$id" ]]; then
    resp=$(cf -X PUT "${API}/zones/${zid}/dns_records/${id}" --data "$body")
  else
    resp=$(cf -X POST "${API}/zones/${zid}/dns_records" --data "$body")
  fi
  ok=$(echo "$resp" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("success"))')
  if [[ "$ok" == "True" ]]; then
    echo "OK    $name → $target"
  else
    echo "FAIL  $name"
    echo "$resp" | python3 -m json.tool || echo "$resp"
    return 1
  fi
}

TARGET="${TUNNEL_ID}.cfargotunnel.com"
TARGET_KASM="${TUNNEL_ID_KASM}.cfargotunnel.com"

echo "=== DNS full reset → tunnel ${TUNNEL_ID} ==="
echo "Target: ${TARGET}"
echo

# Apex + portal
upsert_cname dannygc.cloud dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud cloud.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud hub.dannygc.cloud "$TARGET"

# AI / GhostGrid (urgent)
upsert_cname dannygc.cloud ghostgrid.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud ai.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud ollama.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud api.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud genie.dannygc.cloud "$TARGET"

# Dev / ops
upsert_cname dannygc.cloud code.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud files.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud monitor.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud portainer.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud grafana.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud n8n.dannygc.cloud "$TARGET"
upsert_cname dannygc.cloud photos.dannygc.cloud "$TARGET"

# Cloudit GPU frontends
upsert_cname cloudsit.app video.cloudsit.app "$TARGET"
upsert_cname cloudsit.app comfy.cloudsit.app "$TARGET"
upsert_cname cloudsit.app cloudsit.app "$TARGET"

# Kasm (may share tunnel or use TUNNEL_ID_KASM)
upsert_cname dannyk.online kasm.dannyk.online "$TARGET_KASM" || echo "WARN  dannyk.online zone skipped (token may lack access)"

echo
echo "Done. Wait 30–60s then run: ./scripts/health-check.sh"
echo "If DNS is OK but HTTP still 530/1033, cloudflared is still down on the RTX host."
