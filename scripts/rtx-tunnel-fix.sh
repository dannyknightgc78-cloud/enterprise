#!/usr/bin/env bash
# Fix cloudflared on RTX Pro 6000 (AI tunnels).
# Usage:
#   ./scripts/rtx-tunnel-fix.sh
#   RTX_HOST=172.236.195.90 RTX_USER=root ./scripts/rtx-tunnel-fix.sh
set -euo pipefail

RTX_HOST="${RTX_HOST:-172.236.195.90}"
RTX_USER="${RTX_USER:-root}"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o BatchMode=yes)

echo "==> Connecting to ${RTX_USER}@${RTX_HOST}"
if ! ssh "${SSH_OPTS[@]}" "${RTX_USER}@${RTX_HOST}" 'echo connected'; then
  echo "SSH failed (publickey). Authorize this agent key on the Hostman server:"
  echo
  cat ~/.ssh/id_ed25519.pub 2>/dev/null || echo "(no local key found — generate one first)"
  echo
  echo "Hostman: Cloud servers → your RTX box → Settings → SSH keys → add the key above."
  echo "Or paste into Hostman web console:"
  echo "  mkdir -p /root/.ssh && chmod 700 /root/.ssh"
  echo "  echo 'PUBLIC_KEY' >> /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys"
  exit 1
fi

ssh "${SSH_OPTS[@]}" "${RTX_USER}@${RTX_HOST}" 'bash -s' <<'REMOTE'
set -euo pipefail
echo "=== host ==="
hostname; uptime; date -u

echo
echo "=== cloudflared binary ==="
command -v cloudflared || { echo "cloudflared missing"; exit 1; }
cloudflared --version

echo
echo "=== service status (before) ==="
systemctl status cloudflared --no-pager -l || true
systemctl is-active cloudflared || true

echo
echo "=== config discovery ==="
for p in /etc/cloudflared/config.yml /root/.cloudflared/config.yml /etc/cloudflared/*.json; do
  [ -e "$p" ] && echo "FOUND $p" && ls -la "$p"
done
ls -la /etc/cloudflared 2>/dev/null || true
ls -la /root/.cloudflared 2>/dev/null || true

echo
echo "=== recent logs ==="
journalctl -u cloudflared -n 80 --no-pager || true

echo
echo "=== restart cloudflared ==="
systemctl enable cloudflared 2>/dev/null || true
systemctl restart cloudflared
sleep 3
systemctl --no-pager -l status cloudflared || true

echo
echo "=== tunnel list / info ==="
cloudflared tunnel list 2>/dev/null || true
cloudflared tunnel info 2>/dev/null || true

# Print tunnel UUIDs from config for DNS reset
python3 - <<'PY' 2>/dev/null || true
import re, pathlib, json
paths = list(pathlib.Path("/etc/cloudflared").glob("*")) + list(pathlib.Path("/root/.cloudflared").glob("*"))
for p in paths:
    try:
        text = p.read_text()
    except Exception:
        continue
    if p.suffix in {".yml", ".yaml"}:
        for m in re.finditer(r"(?im)^(?:tunnel|credentials-file):\s*(.+)$", text):
            print(f"CONFIG {p}: {m.group(0).strip()}")
        for m in re.finditer(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text):
            print(f"UUID_IN {p}: {m.group(0)}")
    if p.suffix == ".json":
        try:
            data = json.loads(text)
            if "TunnelID" in data:
                print(f"CRED {p.name} TunnelID={data['TunnelID']}")
            if "AccountTag" in data:
                print(f"CRED {p.name} AccountTag={data['AccountTag']}")
        except Exception:
            pass
PY

echo
echo "=== local origin listeners (common AI ports) ==="
ss -lntp 2>/dev/null | head -60 || netstat -lntp 2>/dev/null | head -60 || true

echo
echo "=== docker (if used) ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true

echo
echo "DONE on origin. If tunnel is Healthy, run DNS reset next."
REMOTE
