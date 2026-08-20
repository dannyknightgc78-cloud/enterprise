#!/usr/bin/env python3
"""Nimbus Live — external-style fleet + site monitor (runs on Hostman origin).
Alerts Telegram on state changes. Serves JSON + HTML status on :3099.
Critical: does NOT depend on Cloudflare tunnels for local origin checks;
also probes public HTTPS so tunnel/DNS failures still alert.
"""
from __future__ import annotations
import json, os, re, subprocess, time, urllib.request, urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread, Lock

ROOT = Path("/opt/nimbus-live")
STATE = Path("/var/lib/nimbus-live/state.json")
LOG = Path("/var/log/nimbus-live/monitor.jsonl")
SITES = json.loads((ROOT / "sites.json").read_text())
SERVERS = json.loads((ROOT / "servers.json").read_text())
LOCK = Lock()
CURRENT = {"updated_at": None, "sites": [], "servers": [], "summary": {}}

def utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load_vault():
    env = {}
    for p in (Path("/root/lab-dannygc/secrets/lab-vault.env"), Path("/root/lab-dannygc/.env")):
        if not p.is_file():
            continue
        for line in p.read_text().splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env

ENV = load_vault()
TG_TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = ENV.get("TELEGRAM_CHAT_ID", "")

def tg(msg: str):
    if not TG_TOKEN or not TG_CHAT:
        return
    try:
        data = json.dumps({"chat_id": TG_CHAT, "text": msg[:3500], "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=data, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        append_log({"event": "tg_fail", "error": str(e)})

def append_log(obj):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(obj) + "\n")

def http_probe(url: str, timeout=12):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NimbusLive/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(20000)
            code = r.status
        title = ""
        try:
            m = re.search(br"<title>([^<]+)", body, re.I)
            title = m.group(1).decode("utf-8", "ignore").strip() if m else ""
        except Exception:
            pass
        return code, title, body
    except urllib.error.HTTPError as e:
        return e.code, "", b""
    except Exception:
        return 0, "", b""

def local_probe(host: str):
    try:
        p = subprocess.run(
            ["curl", "-sS", "-o", "/tmp/nimbus-body.html", "-w", "%{http_code}",
             "-H", f"Host: {host}", "--max-time", "6", "http://127.0.0.1/"],
            capture_output=True, text=True)
        code = int(p.stdout.strip() or "0")
        body = Path("/tmp/nimbus-body.html").read_bytes()[:20000]
        m = re.search(br"<title>([^<]+)", body, re.I)
        title = m.group(1).decode("utf-8", "ignore").strip() if m else ""
        return code, title
    except Exception:
        return 0, ""

def ssh_probe(srv: dict):
    if srv.get("ssh") is False:
        # local hostman checks
        try:
            up = Path("/proc/uptime").read_text().split()[0]
            return {"ok": True, "detail": f"local uptime_s={up}"}
        except Exception as e:
            return {"ok": False, "detail": str(e)}
    host = srv["host"]; user = srv.get("user", "root"); key = srv.get("key", "/root/.ssh/id_ed25519")
    cmd = [
        "ssh", "-i", key, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
        "-o", "StrictHostKeyChecking=accept-new", "-o", "IdentitiesOnly=yes",
        f"{user}@{host}", "echo OK; hostname; uptime -p 2>/dev/null || uptime"
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        ok = p.returncode == 0 and "OK" in p.stdout
        return {"ok": ok, "detail": (p.stdout or p.stderr).strip()[:300]}
    except Exception as e:
        return {"ok": False, "detail": str(e)}

def classify_site(site, local_code, local_title, pub_code, pub_title):
    expect = site.get("expect") or "."
    # DNS/public failure is critical
    if pub_code in (0, 103, 521, 522, 523, 530, 502, 503):
        return "DOWN", f"public HTTP {pub_code}"
    if local_code in (0, 502, 503):
        return "ORIGIN_DOWN", f"local HTTP {local_code}"
    # content mismatch on critical hosts
    if expect != "." and pub_code == 200:
        if not re.search(expect, pub_title or "", re.I) and not re.search(expect, local_title or "", re.I):
            return "WRONG_APP", f"title={pub_title or local_title}"
    if pub_code in (200, 301, 302, 401, 403):
        return "OK", f"public {pub_code}"
    return "CHECK", f"public {pub_code} local {local_code}"

def previous_state():
    if STATE.is_file():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"sites": {}, "servers": {}}


def infra_status():
    import subprocess as _sp
    def _active(unit):
        try:
            r = _sp.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=5)
            return (r.stdout or "").strip() or "unknown"
        except Exception:
            return "unknown"
    ha = "n/a"
    try:
        import urllib.request
        raw = urllib.request.urlopen("http://127.0.0.1:20241/metrics", timeout=3).read().decode("utf-8", "ignore")
        for line in raw.splitlines():
            if line.startswith("cloudflared_tunnel_ha_connections "):
                ha = line.split()[-1]
                break
    except Exception:
        pass
    wd = "up" if _sp.run(["docker", "inspect", "-f", "{{.State.Running}}", "watchdog-agent"], capture_output=True, text=True, timeout=5).stdout.strip() == "true" else "down"
    return {
        "cloudflared": _active("cloudflared"),
        "nginx": _active("nginx"),
        "watchdog": wd,
        "tunnel_ha": ha,
        "lead_scraper": _active("lead-scraper"),
        "auto_emailer": _active("auto-emailer"),
    }


def ops_pulse():
    """UI-facing ops flags (not secrets)."""
    rg = "off"
    lead_tg = "off"
    try:
        # compose env often sets ROUTE_GUARD_TELEGRAM=0
        compose = Path("/root/lab-dannygc/docker-compose.yml")
        if compose.is_file() and "ROUTE_GUARD_TELEGRAM=0" in compose.read_text():
            rg = "off"
        elif compose.is_file() and "ROUTE_GUARD_TELEGRAM=1" in compose.read_text():
            rg = "on"
    except Exception:
        pass
    try:
        for p in (
            Path("/root/lead-scraper/.env"),
            Path("/root/lead-scraper/config.env"),
            Path("/etc/default/lead-scraper"),
        ):
            if p.is_file() and "TELEGRAM_LEADS_ENABLED=0" in p.read_text():
                lead_tg = "off"
                break
            if p.is_file() and "TELEGRAM_LEADS_ENABLED=1" in p.read_text():
                lead_tg = "on"
    except Exception:
        pass
    return {
        "route_guard_telegram": rg,
        "lead_telegram": lead_tg,
        "interval_sec": os.environ.get("NIMBUS_INTERVAL_SEC", "60"),
        "ghosts_expect": "Ghost Home",
        "g7_host": "g7.dannygc.cloud",
    }

def run_cycle():
    prev = previous_state()
    site_rows = []
    server_rows = []
    alerts = []
    for site in SITES:
        host = site["host"]
        lc, lt = local_probe(host)
        pc, pt, _ = http_probe(site["url"])
        status, detail = classify_site(site, lc, lt, pc, pt)
        row = {"host": host, "status": status, "detail": detail, "local": lc, "public": pc,
               "local_title": lt, "public_title": pt, "checked_at": utc()}
        site_rows.append(row)
        old = (prev.get("sites") or {}).get(host, {}).get("status")
        if old and old != status and status in ("DOWN", "ORIGIN_DOWN", "WRONG_APP"):
            alerts.append(f"🔴 {host} {old}→{status} ({detail})")
        elif old in ("DOWN", "ORIGIN_DOWN", "WRONG_APP") and status == "OK":
            alerts.append(f"🟢 {host} recovered ({detail})")

    for srv in SERVERS:
        res = ssh_probe(srv)
        status = "OK" if res["ok"] else "SSH_FAIL"
        row = {"id": srv["id"], "label": srv.get("label"), "host": srv["host"], "status": status,
               "detail": res["detail"], "checked_at": utc()}
        server_rows.append(row)
        old = (prev.get("servers") or {}).get(srv["id"], {}).get("status")
        if old and old != status and status == "SSH_FAIL":
            alerts.append(f"🔴 server {srv['id']} SSH_FAIL: {res['detail'][:120]}")
        elif old == "SSH_FAIL" and status == "OK":
            alerts.append(f"🟢 server {srv['id']} SSH recovered")

    summary = {
        "sites_ok": sum(1 for r in site_rows if r["status"] == "OK"),
        "sites_bad": sum(1 for r in site_rows if r["status"] != "OK"),
        "servers_ok": sum(1 for r in server_rows if r["status"] == "OK"),
        "servers_bad": sum(1 for r in server_rows if r["status"] != "OK"),
    }
    state = {
        "updated_at": utc(),
        "sites": {r["host"]: r for r in site_rows},
        "servers": {r["id"]: r for r in server_rows},
        "summary": summary,
    }
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2))
    with LOCK:
        CURRENT.clear()
        CURRENT.update({
            "updated_at": state["updated_at"],
            "sites": site_rows,
            "servers": server_rows,
            "summary": summary,
            "infra": infra_status(),
            "pulse": ops_pulse(),
            "health_score": round(100 * summary["sites_ok"] / max(1, len(site_rows))),
        })
    append_log({"event": "cycle", "at": utc(), "summary": summary, "alerts": alerts})
    if alerts:
        tg("Nimbus Live\n" + "\n".join(alerts[:20]))
    return state

HTML = """<!doctype html><html><head><meta charset=utf-8><meta http-equiv=refresh content=60>
<title>Nimbus Live — Fleet & Site Monitor</title>
<style>
:root{--bg:#0b1220;--card:#121a2b;--ok:#3ddc97;--bad:#ff5d5d;--warn:#ffc857;--muted:#8b9bb4;--fg:#e8eefc}
*{box-sizing:border-box}body{margin:0;font-family:ui-sans-serif,system-ui,Segoe UI,sans-serif;background:radial-gradient(1200px 600px at 10% -10%,#1a2744,var(--bg));color:var(--fg)}
header{padding:28px 32px 8px}h1{margin:0;font-size:28px;letter-spacing:.02em}h1 span{color:#6ea8fe}
.sub{color:var(--muted);margin-top:6px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px 32px 40px}
@media(max-width:960px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid #243049;border-radius:14px;padding:16px;overflow:auto;max-height:70vh}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{padding:8px 10px;border-bottom:1px solid #1e2a40;text-align:left}
th{color:var(--muted);font-weight:600}.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700}
.OK{background:#143528;color:var(--ok)}.DOWN,.ORIGIN_DOWN,.SSH_FAIL{background:#3a1418;color:var(--bad)}
.WRONG_APP,.CHECK{background:#3a2e14;color:var(--warn)}.stats{display:flex;gap:12px;flex-wrap:wrap;margin:12px 32px}
.stat{background:var(--card);border:1px solid #243049;border-radius:12px;padding:12px 16px;min-width:140px}
.stat b{display:block;font-size:22px}
</style></head><body>
<header><h1>Nimbus <span>Live</span></h1>
<div class=sub>External-style site + passwordless server monitor · auto-refresh 60s · Telegram on change</div></header>
<div class=stats id=stats></div>
<div class=grid>
<div class=card><h3>Sites</h3><table><thead><tr><th>Status</th><th>Host</th><th>Public</th><th>Local</th><th>Title</th></tr></thead><tbody id=sites></tbody></table></div>
<div class=card><h3>Servers (passwordless SSH)</h3><table><thead><tr><th>Status</th><th>ID</th><th>Host</th><th>Detail</th></tr></thead><tbody id=servers></tbody></table></div>
</div>
<script>
async function load(){
  const d=await fetch('/api/status').then(r=>r.json());
  document.getElementById('stats').innerHTML=`
    <div class=stat><b>${d.summary.sites_ok}/${d.sites.length}</b>sites OK</div>
    <div class=stat><b>${d.summary.sites_bad}</b>sites bad</div>
    <div class=stat><b>${d.summary.servers_ok}/${d.servers.length}</b>servers OK</div>
    <div class=stat><b>${d.summary.servers_bad}</b>SSH fail</div>
    <div class=stat><b style=font-size:14px>${d.updated_at||'—'}</b>updated UTC</div>`;
  const order={DOWN:0,ORIGIN_DOWN:1,SSH_FAIL:1,WRONG_APP:2,CHECK:3,OK:4};
  d.sites.sort((a,b)=>(order[a.status]??9)-(order[b.status]??9)||a.host.localeCompare(b.host));
  document.getElementById('sites').innerHTML=d.sites.map(s=>`<tr>
    <td><span class="pill ${s.status}">${s.status}</span></td>
    <td>${s.host}</td><td>${s.public}</td><td>${s.local}</td>
    <td>${(s.public_title||s.local_title||s.detail||'').replace(/[<>]/g=>'')} </td></tr>`).join('');
  document.getElementById('servers').innerHTML=d.servers.map(s=>`<tr>
    <td><span class="pill ${s.status}">${s.status}</span></td>
    <td>${s.id}</td><td>${s.host}</td><td><code>${(s.detail||'').replace(/[<>]/g=>'')}</code></td></tr>`).join('');
}
load(); setInterval(load, 30000);
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return
    def do_GET(self):
        if self.path.startswith("/api/status"):
            with LOCK:
                payload = json.dumps(CURRENT).encode()
            self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
            return
        if self.path.startswith("/api/health"):
            body=b'{"ok":true,"service":"nimbus-live"}'
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(body); return
        html_path = ROOT / "static" / "index.html"
        body = html_path.read_bytes() if html_path.is_file() else HTML.encode()
        self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.end_headers(); self.wfile.write(body)

def loop():
    while True:
        try:
            run_cycle()
        except Exception as e:
            append_log({"event":"cycle_error","error":str(e),"at":utc()})
        time.sleep(int(os.environ.get("NIMBUS_INTERVAL_SEC", "60")))

if __name__ == "__main__":
    def boot():
        time.sleep(0.2)
        try: run_cycle()
        except Exception as e: print("initial cycle error", e)
        loop()
    Thread(target=boot, daemon=True).start()
    print("nimbus-live listening 127.0.0.1:3099", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 3099), Handler).serve_forever()
