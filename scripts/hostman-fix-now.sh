#!/usr/bin/env bash
# Run ON Hostman as root after SSH works
set -euo pipefail
PUB='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFFWu6tW6vP2CYNp0CQn5lUSXB5Zitu/SrP5EQewx5Yc cursor-cloud-agent-recovery'
mkdir -p /root/.ssh && chmod 700 /root/.ssh
grep -qF "$PUB" /root/.ssh/authorized_keys 2>/dev/null || echo "$PUB" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
echo "Authorized Cursor agent key"

echo "=== cloudflared ==="
systemctl status cloudflared --no-pager -l || true
journalctl -u cloudflared -n 40 --no-pager || true

echo "=== what is on :8811 (GhostGrid) ==="
ss -lntp | grep -E ':8811|:4173|:18001|:80|:8788' || true
curl -sS -m 3 http://127.0.0.1:8811/ | head -c 200; echo
curl -sS -m 3 http://127.0.0.1:8811/ | tr '\n' ' ' | sed -n 's/.*<title>\([^<]*\)<\/title>.*/TITLE: \1/ip'; echo

echo "=== docker ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true

echo "=== nginx sites ==="
ls /etc/nginx/sites-enabled 2>/dev/null || true
grep -R "server_name" /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -80

# Ensure mysteryproject is the only tunnel on THIS host if multiple tokens exist
ls -la /etc/cloudflared /root/.cloudflared 2>/dev/null || true
