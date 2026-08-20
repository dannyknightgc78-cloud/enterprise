#!/usr/bin/env python3
"""Patch nimbus_telegram.py for stronger Ghosts Home NL + auto-repair."""
from __future__ import annotations

from pathlib import Path

PATH = Path("/root/lab-dannygc/scripts/lib/nimbus_telegram.py")
text = PATH.read_text()
orig = text

OLD_REPORT = '''def build_fix_ghosts_home_report() -> str:
    """Ensure ghosts.dannygc.cloud is Mac Ghost Home (home-edge), not G7 Command Centre."""
    import json, urllib.request
    from pathlib import Path as _P
    lines = ["👻 <b>Ghosts Home</b>", ""]
    try:
        req = urllib.request.Request("https://ghosts.dannygc.cloud/", headers={"User-Agent": "NimbusNL/1.0"})
        with urllib.request.urlopen(req, timeout=15) as res:
            body = res.read(2500).decode("utf-8", "ignore")
        title = ""
        import re as _re
        m = _re.search(r"<title>([^<]+)", body, _re.I)
        title = (m.group(1) if m else "").strip()
        ok = "ghost home" in title.lower()
        lines.append(("✅" if ok else "⚠️") + f" title: <code>{_esc(title)}</code>")
        hreq = urllib.request.Request("https://ghosts.dannygc.cloud/api/health", headers={"User-Agent": "NimbusNL/1.0"})
        health = json.loads(urllib.request.urlopen(hreq, timeout=15).read().decode())
        lines.append(f"platform: <code>{_esc(str(health.get('platform')))}</code> · aether={health.get('aether_ready')}")
        if ok:
            lines.append("")
            lines.append("Ghosts is on <b>Mac Ghost Home</b> (home-edge tunnel).")
            lines.append("G7 Command Centre is separate: <code>g7.dannygc.cloud</code>")
        else:
            lines.append("")
            lines.append("Not Ghost Home — run DNS/tunnel repair on Hostman.")
    except Exception as exc:
        lines.append(f"✗ probe failed: {_esc(str(exc)[:200])}")
    return "\\n".join(lines)'''

NEW_REPORT = '''def build_fix_ghosts_home_report() -> str:
    """Ensure ghosts.dannygc.cloud is Mac Ghost Home (home-edge), not G7 Command Centre.

    If misrouted, re-assert Cloudflare DNS CNAME → home-edge tunnel and disable Hostman
    ghosts vhost so G7 stays on g7.dannygc.cloud only.
    """
    import json
    import urllib.request
    from pathlib import Path as _P

    HOME_EDGE = "518d4da0-ca44-4df1-a759-6a2941c61d4f.cfargotunnel.com"
    lines = ["👻 <b>Ghosts Home</b>", ""]

    def _probe_title() -> str:
        req = urllib.request.Request(
            "https://ghosts.dannygc.cloud/",
            headers={"User-Agent": "NimbusNL/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            body = res.read(4000).decode("utf-8", "ignore")
        import re as _re

        m = _re.search(r"<title>([^<]+)", body, _re.I)
        return (m.group(1) if m else "").strip()

    def _load_cf_token() -> str:
        env: dict[str, str] = {}
        for p in (
            _P("/root/lab-dannygc/secrets/lab-vault.env"),
            _P("/root/lab-dannygc/.env"),
        ):
            if not p.is_file():
                continue
            for line in p.read_text().splitlines():
                if not line.strip() or line.strip().startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\\"")
        return (
            env.get("CF_API_TOKEN")
            or env.get("CLOUDFLARE_API_TOKEN")
            or env.get("CLOUDFLARE_API_TOKEN_TUNNELS")
            or ""
        )

    def _repair_dns() -> str:
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
        return f"updated CNAME→home-edge ({ok})"

    def _disable_hostman_vhost() -> str:
        avail = _P("/etc/nginx/sites-available/ghosts.dannygc.cloud.conf")
        enabled = _P("/etc/nginx/sites-enabled/ghosts.dannygc.cloud.conf")
        disabled = _P("/etc/nginx/sites-available/ghosts.dannygc.cloud.conf.disabled-ghosthome-20260820")
        notes = []
        if enabled.is_symlink() or enabled.is_file():
            enabled.unlink()
            notes.append("removed sites-enabled")
        if avail.is_file() and not disabled.is_file():
            avail.rename(disabled)
            notes.append("disabled sites-available")
        if notes:
            subprocess.run(["nginx", "-t"], check=False, capture_output=True)
            subprocess.run(["systemctl", "reload", "nginx"], check=False, capture_output=True)
            return ", ".join(notes)
        return "Hostman ghosts vhost already disabled"

    try:
        title = _probe_title()
        ok = "ghost home" in title.lower() and "command centre" not in title.lower()
        lines.append(("✅" if ok else "⚠️") + f" title: <code>{_esc(title)}</code>")
        if not ok:
            lines.append("")
            lines.append("🔧 repairing…")
            try:
                lines.append(f"DNS: {_esc(_repair_dns())}")
            except Exception as exc:
                lines.append(f"DNS repair failed: {_esc(str(exc)[:180])}")
            try:
                lines.append(f"nginx: {_esc(_disable_hostman_vhost())}")
            except Exception as exc:
                lines.append(f"nginx repair failed: {_esc(str(exc)[:180])}")
            import time as _time

            _time.sleep(2)
            title = _probe_title()
            ok = "ghost home" in title.lower() and "command centre" not in title.lower()
            lines.append(("✅" if ok else "⚠️") + f" after repair: <code>{_esc(title)}</code>")
        try:
            hreq = urllib.request.Request(
                "https://ghosts.dannygc.cloud/api/health",
                headers={"User-Agent": "NimbusNL/1.0"},
            )
            health = json.loads(urllib.request.urlopen(hreq, timeout=15).read().decode())
            lines.append(
                f"platform: <code>{_esc(str(health.get('platform')))}</code> · aether={health.get('aether_ready')}"
            )
        except Exception as hexc:
            lines.append(f"health: {_esc(str(hexc)[:120])}")
        lines.append("")
        if ok:
            lines.append("Ghosts is on <b>Mac Ghost Home</b> (home-edge tunnel).")
            lines.append("G7 Command Centre is separate: <code>g7.dannygc.cloud</code>")
            lines.append("If your phone still shows G7: hard-refresh / clear CF cache.")
        else:
            lines.append("Still not Ghost Home after repair — check Mac home-edge :8850.")
    except Exception as exc:
        lines.append(f"✗ probe failed: {_esc(str(exc)[:200])}")
    return "\\n".join(lines)'''

OLD_NL = '''_NL_GHOSTS_HOME = re.compile(
    r"(?:^|\\b)(?:"
    r"fix\\s+ghosts?(?:\\s+home)?|"
    r"ghosts?(?:\\s+home)?\\s+(?:is\\s+)?(?:wrong|broken|down|misrouted)|"
    r"(?:why\\s+is\\s+)?ghosts?(?:\\s+home)?\\s+(?:wrong|broken)|"
    r"restore\\s+ghosts?(?:\\s+home)?|"
    r"point\\s+ghosts?\\s+(?:at|to)\\s+(?:mac|home[- ]?edge|ghost\\s*home)"
    r")(?:\\b|$)",
    re.I,
)
_NL_STATUS_PLAIN = re.compile(
    r"(?:^|\\b)(?:"
    r"how(?:'\\s*)?s\\s+(?:the\\s+)?(?:lab|empire|stack|fleet)|"
    r"is\\s+everything\\s+(?:ok|okay|fine|up|green)|"
    r"what(?:'\\s*)?s\\s+(?:down|broken|failing)|"
    r"any\\s+(?:outages?|problems?|issues?)|"
    r"give\\s+me\\s+(?:a\\s+)?(?:status|update|report)|"
    r"check\\s+(?:the\\s+)?(?:sites?|servers?|fleet)"
    r")(?:\\b|$)",
    re.I,
)'''

NEW_NL = '''_NL_GHOSTS_HOME = re.compile(
    r"(?:^|\\b)(?:"
    r"fix\\s+ghosts?(?:\\s+home)?|"
    r"ghosts?(?:\\s+home)?\\s+(?:is\\s+)?(?:still\\s+)?(?:wrong|broken|down|misrouted|busted)|"
    r"(?:why(?:'?s|\\s+is)?)\\s+ghosts?(?:\\s+home)?\\s+(?:not\\s+)?(?:fixed|wrong|broken)|"
    r"why(?:'?s)?\\s+ghosts?(?:\\s+home)?\\s+not\\s+fixed|"
    r"ghosts?(?:\\s+home)?\\s+(?:still\\s+)?(?:not\\s+)?(?:fixed|working)|"
    r"restore\\s+ghosts?(?:\\s+home)?|"
    r"point\\s+ghosts?\\s+(?:at|to)\\s+(?:mac|home[- ]?edge|ghost\\s*home)|"
    r"(?:make\\s+)?ghosts?(?:\\s+home)?\\s+(?:right|correct|again)"
    r")(?:\\b|$)",
    re.I,
)
_NL_STATUS_PLAIN = re.compile(
    r"(?:^|\\b)(?:"
    r"how(?:'\\s*)?s\\s+(?:the\\s+)?(?:lab|empire|stack|fleet)|"
    r"is\\s+everything\\s+(?:ok|okay|fine|up|green)|"
    r"what(?:'\\s*)?s\\s+(?:down|broken|failing)|"
    r"what\\s+is\\s+(?:down|broken|failing)|"
    r"any\\s+(?:outages?|problems?|issues?)|"
    r"give\\s+me\\s+(?:a\\s+)?(?:status|update|report)|"
    r"check\\s+(?:the\\s+)?(?:sites?|servers?|fleet)|"
    r"make\\s+nimbus\\s+(?:bigger|better)|"
    r"nimbus\\s+(?:status|board|monitor)"
    r")(?:\\b|$)",
    re.I,
)'''

OLD_HELP_PLAIN = '''        "<b>Plain English</b>\\n"
        "• “full scan all web apps”\\n"
        "• “check all sites and tunnels”\\n"
        "• “fix tunnel” · “heal lab” · “repair everything”\\n"
        "• “emergency fix” · “system recovery”\\n"
        "• “is daily backup done?”\\n"
        "• “full server snapshot” · “snapshot trooper” · “snapshot vultr”\\n"
        "• “Nimbus omega red OLD_IP” — sets pending; reply OMEGA RED NOW (never automatic)\\n"
        f"• After scrub: reply {OMEGA_DELETE_PHRASE} to remove Vultr VM (optional)\\n"
        "• “Captain force backup” — LAST RESORT; sets pending; reply CAPTAIN BACKUP NOW\\n"
        "• “Captain kill switch HOST” — LAST RESORT; password then phrase (or phrase then password)\\n"
        "• “snapshot all” · “heal hostman” · “tunnel check trooper” (voice or text)\\n"
        "• “update os all servers” · “patch vultr” — OS apt upgrade (reply UPDATE OS NOW for all)\\n"
        "• “update trooper” · “update trooper server” — rsync scripts (not OS packages)\\n"
        "• Voice notes — 🎤 transcribed via Whisper; destructive ops need enrolled voice\\n"
        "• /voice-enroll then 5–10s sample — speaker verify before captain-kill · omega-red\\n"
        "• “system status”\\n\\n"'''

NEW_HELP_PLAIN = '''        "<b>Plain English (no slash needed)</b>\\n"
        "• “is everything ok” · “whats down” · “what is down”\\n"
        "• “fix ghosts home” · “why is ghosts home not fixed” · “ghosts still wrong”\\n"
        "• “open the services monitor” · “nimbus board”\\n"
        "• “stop route guard alerts”\\n"
        "• “full scan all web apps” · “check all sites and tunnels”\\n"
        "• “fix tunnel” · “heal lab” · “repair everything”\\n"
        "• “emergency fix” · “system recovery”\\n"
        "• “is daily backup done?”\\n"
        "• “full server snapshot” · “snapshot trooper” · “snapshot vultr”\\n"
        "• “Nimbus omega red OLD_IP” — sets pending; reply OMEGA RED NOW (never automatic)\\n"
        f"• After scrub: reply {OMEGA_DELETE_PHRASE} to remove Vultr VM (optional)\\n"
        "• “Captain force backup” — LAST RESORT; sets pending; reply CAPTAIN BACKUP NOW\\n"
        "• “Captain kill switch HOST” — LAST RESORT; password then phrase (or phrase then password)\\n"
        "• “snapshot all” · “heal hostman” · “tunnel check trooper” (voice or text)\\n"
        "• “update os all servers” · “patch vultr” — OS apt upgrade (reply UPDATE OS NOW for all)\\n"
        "• “update trooper” · “update trooper server” — rsync scripts (not OS packages)\\n"
        "• Voice notes — 🎤 transcribed via Whisper; destructive ops need enrolled voice\\n"
        "• /voice-enroll then 5–10s sample — speaker verify before captain-kill · omega-red\\n"
        "• “system status”\\n\\n"'''

if OLD_REPORT not in text:
    raise SystemExit("OLD_REPORT not found")
if OLD_NL not in text:
    raise SystemExit("OLD_NL not found")
if OLD_HELP_PLAIN not in text:
    raise SystemExit("OLD_HELP_PLAIN not found")

text = text.replace(OLD_REPORT, NEW_REPORT, 1)
text = text.replace(OLD_NL, NEW_NL, 1)
text = text.replace(OLD_HELP_PLAIN, NEW_HELP_PLAIN, 1)

# also map make nimbus bigger -> services-monitor when that phrase alone
needle = '''    if _NL_STATUS_PLAIN.search(low):
        return "status"'''
repl = '''    if re.search(r"make\\s+nimbus\\s+(?:bigger|better)|nimbus\\s+board", low):
        return "services-monitor"
    if _NL_STATUS_PLAIN.search(low):
        return "status"'''
if needle not in text:
    raise SystemExit("status plain hook not found")
text = text.replace(needle, repl, 1)

if text == orig:
    raise SystemExit("no changes applied")

bak = PATH.with_suffix(PATH.suffix + ".bak.nl-20260820b")
bak.write_text(orig)
PATH.write_text(text)
print("patched", PATH)
print("backup", bak)
