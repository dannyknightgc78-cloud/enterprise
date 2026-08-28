#!/usr/bin/env python3
"""Patch nimbus_telegram.py: prefer Hostman fallback when Mac home-edge is down.

Replaces the 2026-08-20 NL patch that always CNAMEs ghosts → home-edge and
disables the Hostman nginx vhost (causes 530/1033 when Mac is off).
"""
from __future__ import annotations

from pathlib import Path

PATH = Path("/root/lab-dannygc/scripts/lib/nimbus_telegram.py")
text = PATH.read_text()
orig = text

HOME_EDGE = "518d4da0-ca44-4df1-a759-6a2941c61d4f.cfargotunnel.com"
HOSTMAN_TUNNEL = "8cc6cd76-7f80-449e-b93f-2df400129dd1.cfargotunnel.com"

OLD_MARKER = '''    HOME_EDGE = "518d4da0-ca44-4df1-a759-6a2941c61d4f.cfargotunnel.com"
    lines = ["👻 <b>Ghosts Home</b>", ""]'''

NEW_MARKER = f'''    HOME_EDGE = "{HOME_EDGE}"
    HOSTMAN_TUNNEL = "{HOSTMAN_TUNNEL}"
    lines = ["👻 <b>Ghosts Home</b>", ""]'''

OLD_REPAIR = '''    def _repair_dns() -> str:
        tok = _load_cf_token()
        if not tok:
            return "no CF token"
        headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
        zreq = urllib.request.Request(
            "https://api.cloudflare.com/client/v4/zones?name=dannygc.cloud",
            headers=headers,
        )
        zid = json.loads(urllib.request.urlopen(zreq, timeout=20).read())["result"][0]["id"]
        rreq = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{zid}/dns_records?name=ghosts.dannygc.cloud",
            headers=headers,
        )
        recs = json.loads(urllib.request.urlopen(rreq, timeout=20).read())["result"]
        if not recs:
            payload = json.dumps(
                {
                    "type": "CNAME",
                    "name": "ghosts",
                    "content": HOME_EDGE,
                    "proxied": True,
                    "ttl": 1,
                }
            ).encode()
            creq = urllib.request.Request(
                f"https://api.cloudflare.com/client/v4/zones/{zid}/dns_records",
                data=payload,
                headers=headers,
                method="POST",
            )
            ok = json.loads(urllib.request.urlopen(creq, timeout=20).read()).get("success")
            return f"created CNAME→home-edge ({ok})"
        rec = recs[0]
        need = rec.get("type") != "CNAME" or rec.get("content") != HOME_EDGE or not rec.get("proxied")
        if not need:
            return "DNS already home-edge"
        payload = json.dumps(
            {
                "type": "CNAME",
                "name": "ghosts",
                "content": HOME_EDGE,
                "proxied": True,
                "ttl": 1,
            }
        ).encode()
        ureq = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{zid}/dns_records/{rec['id']}",
            data=payload,
            headers=headers,
            method="PUT",
        )
        ok = json.loads(urllib.request.urlopen(ureq, timeout=20).read()).get("success")
        return f"updated CNAME→home-edge ({ok})"'''

NEW_REPAIR = f'''    def _home_edge_alive() -> bool:
        try:
            req = urllib.request.Request(
                "https://api.cloudflare.com/client/v4/accounts",
                headers={{"Authorization": f"Bearer {{_load_cf_token()}}"}},
            )
            # cheap probe: if public ghosts is 530, home-edge route is dead
            greq = urllib.request.Request(
                "https://ghosts.dannygc.cloud/",
                headers={{"User-Agent": "NimbusNL/1.0"}},
            )
            with urllib.request.urlopen(greq, timeout=12) as res:
                body = res.read(800).decode("utf-8", "ignore")
            if "1033" in body or "error code: 1033" in body.lower():
                return False
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 530:
                return False
            return True
        except Exception:
            return False

    def _repair_dns(target: str, label: str) -> str:
        tok = _load_cf_token()
        if not tok:
            return "no CF token"
        headers = {{"Authorization": f"Bearer {{tok}}", "Content-Type": "application/json"}}
        zreq = urllib.request.Request(
            "https://api.cloudflare.com/client/v4/zones?name=dannygc.cloud",
            headers=headers,
        )
        zid = json.loads(urllib.request.urlopen(zreq, timeout=20).read())["result"][0]["id"]
        rreq = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{{zid}}/dns_records?name=ghosts.dannygc.cloud",
            headers=headers,
        )
        recs = json.loads(urllib.request.urlopen(rreq, timeout=20).read())["result"]
        payload = json.dumps(
            {{
                "type": "CNAME",
                "name": "ghosts",
                "content": target,
                "proxied": True,
                "ttl": 1,
            }}
        ).encode()
        if not recs:
            creq = urllib.request.Request(
                f"https://api.cloudflare.com/client/v4/zones/{{zid}}/dns_records",
                data=payload,
                headers=headers,
                method="POST",
            )
            ok = json.loads(urllib.request.urlopen(creq, timeout=20).read()).get("success")
            return f"created CNAME→{{label}} ({{ok}})"
        rec = recs[0]
        if (
            rec.get("type") == "CNAME"
            and rec.get("content") == target
            and rec.get("proxied")
        ):
            return f"DNS already {{label}}"
        ureq = urllib.request.Request(
            f"https://api.cloudflare.com/client/v4/zones/{{zid}}/dns_records/{{rec['id']}}",
            data=payload,
            headers=headers,
            method="PUT",
        )
        ok = json.loads(urllib.request.urlopen(ureq, timeout=20).read()).get("success")
        return f"updated CNAME→{{label}} ({{ok}})"

    def _enable_hostman_vhost() -> str:
        import subprocess

        script = _P("/root/lab-dannygc/scripts/hostman/fix-ghosts-hostman.sh")
        if script.is_file():
            subprocess.run(["bash", str(script)], check=False, capture_output=True)
            return "ran fix-ghosts-hostman.sh"
        avail = _P("/etc/nginx/sites-available/ghosts.dannygc.cloud.conf")
        enabled = _P("/etc/nginx/sites-enabled/ghosts.dannygc.cloud.conf")
        disabled = _P(
            "/etc/nginx/sites-available/ghosts.dannygc.cloud.conf.disabled-ghosthome-20260820"
        )
        if disabled.is_file() and not avail.is_file():
            disabled.rename(avail)
        if not enabled.is_symlink() and not enabled.is_file() and avail.is_file():
            enabled.symlink_to(avail)
            subprocess.run(["nginx", "-t"], check=False, capture_output=True)
            subprocess.run(["systemctl", "reload", "nginx"], check=False, capture_output=True)
            return "re-enabled Hostman ghosts vhost"
        return "Hostman ghosts vhost already enabled"'''

OLD_TRY = '''        if not ok:
            lines.append("")
            lines.append("🔧 repairing…")
            try:
                lines.append(f"DNS: {_esc(_repair_dns())}")
            except Exception as exc:
                lines.append(f"DNS repair failed: {_esc(str(exc)[:180])}")
            try:
                lines.append(f"nginx: {_esc(_disable_hostman_vhost())}")
            except Exception as exc:
                lines.append(f"nginx repair failed: {_esc(str(exc)[:180])}")'''

NEW_TRY = '''        if not ok:
            lines.append("")
            lines.append("🔧 repairing…")
            try:
                if _home_edge_alive():
                    lines.append(f"DNS: {_esc(_repair_dns(HOME_EDGE, 'home-edge'))}")
                    try:
                        lines.append(f"nginx: {_esc(_disable_hostman_vhost())}")
                    except Exception as exc:
                        lines.append(f"nginx repair failed: {_esc(str(exc)[:180])}")
                else:
                    lines.append("Mac home-edge down — using Hostman fallback")
                    lines.append(f"DNS: {_esc(_repair_dns(HOSTMAN_TUNNEL, 'hostman'))}")
                    try:
                        lines.append(f"nginx: {_esc(_enable_hostman_vhost())}")
                    except Exception as exc:
                        lines.append(f"nginx repair failed: {_esc(str(exc)[:180])}")
            except Exception as exc:
                lines.append(f"DNS repair failed: {_esc(str(exc)[:180])}")'''

OLD_OK_MSG = '''        if ok:
            lines.append("Ghosts is on <b>Mac Ghost Home</b> (home-edge tunnel).")
            lines.append("G7 Command Centre is separate: <code>g7.dannygc.cloud</code>")
            lines.append("If your phone still shows G7: hard-refresh / clear CF cache.")
        else:
            lines.append("Still not Ghost Home after repair — check Mac home-edge :8850.")'''

NEW_OK_MSG = '''        if ok:
            lines.append("Ghosts is serving <b>Ghost Home</b>.")
            lines.append("Mac live → home-edge tunnel; Mac off → Hostman fallback.")
            lines.append("G7 Command Centre is separate: <code>g7.dannygc.cloud</code>")
        else:
            lines.append("Still not Ghost Home — run on Hostman:")
            lines.append("<code>bash scripts/hostman/fix-ghosts-hostman.sh</code>")'''

for label, old, new in (
    ("marker", OLD_MARKER, NEW_MARKER),
    ("repair", OLD_REPAIR, NEW_REPAIR),
    ("try", OLD_TRY, NEW_TRY),
    ("ok_msg", OLD_OK_MSG, NEW_OK_MSG),
):
    if old not in text:
        raise SystemExit(f"OLD {label} not found — already patched or nimbus_telegram changed")
    text = text.replace(old, new, 1)

if text == orig:
    raise SystemExit("no changes applied")

bak = PATH.with_suffix(PATH.suffix + ".bak.ghosts-hostman-fallback")
bak.write_text(orig)
PATH.write_text(text)
print("patched", PATH)
print("backup", bak)
