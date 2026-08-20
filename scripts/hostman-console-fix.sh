#!/usr/bin/env bash
# Paste this entire script into the Hostman web/VNC console on the RTX Pro box
# (root shell) when SSH from Cursor is blocked. It restores cloudflared and prints
# the Tunnel UUID needed for DNS reset.
set -euo pipefail

echo "=== Hostman RTX console fix ==="
date -u
hostname

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "Installing cloudflared..."
  curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
  dpkg -i /tmp/cloudflared.deb || apt-get install -f -y
fi

cloudflared --version
systemctl enable cloudflared 2>/dev/null || true
systemctl restart cloudflared
sleep 4
systemctl --no-pager -l status cloudflared || true
journalctl -u cloudflared -n 40 --no-pager || true

echo
echo "=== Tunnel UUID (copy into TUNNEL_ID for dns-reset.sh) ==="
python3 - <<'PY'
import json, re, pathlib
for base in (pathlib.Path("/etc/cloudflared"), pathlib.Path("/root/.cloudflared")):
    if not base.exists():
        continue
    for p in base.iterdir():
        try:
            text = p.read_text()
        except Exception:
            continue
        if p.suffix == ".json":
            try:
                data = json.loads(text)
                if "TunnelID" in data:
                    print(f"TUNNEL_ID={data['TunnelID']}")
            except Exception:
                pass
        for m in re.finditer(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text):
            print(f"FOUND_UUID={m.group(0)}  ({p})")
PY

cloudflared tunnel list 2>/dev/null || true

# Authorize Cursor cloud agent SSH keys (safe to re-run)
for PUB in \
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGh5uzhhDMuW+reaCiInxGD2EetWAK+QyxnW0TFnvxeu cursor-cloud-agent' \
  'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFFWu6tW6vP2CYNp0CQn5lUSXB5Zitu/SrP5EQewx5Yc cursor-cloud-agent-recovery'
do
  mkdir -p /root/.ssh
  chmod 700 /root/.ssh
  touch /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
  grep -qF "$PUB" /root/.ssh/authorized_keys || echo "$PUB" >> /root/.ssh/authorized_keys
done
echo "Authorized Cursor agent SSH keys."

echo
echo "=== GPU relay bootstrap ==="
curl -fsSL https://raw.githubusercontent.com/dannyknightgc78-cloud/enterprise/cursor/rtx-pro-hybrid-relay-4fb3/infra/rtx-pro/scripts/bootstrap.sh | bash || true

echo
echo "Next: edit /opt/cursor-workers/enterprise/infra/rtx-pro/.env (NGC + CURSOR service account keys)"
echo "Then: cd /opt/cursor-workers/enterprise/infra/rtx-pro && bash worker/start-worker.sh"
