#!/usr/bin/env python3
"""Create+send batch-emailer campaigns for contacts not yet delivered."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import sys as _sys

_sys.path.insert(0, "/root/lead-scraper")
import email_daily_quota as daily_quota  # noqa: E402

LOG = Path("/var/log/bulk-campaign-auto.log")
sys.stdout = open(LOG, "a", buffering=1)
sys.stderr = sys.stdout

ENV: dict[str, str] = {}
for p in (Path("/opt/batch-emailer/.env"), Path("/root/lead-scraper/.env")):
    if not p.exists():
        continue
    for line in p.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            ENV.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE = "http://127.0.0.1:8890"
TOKEN = ENV.get("BATCH_EMAILER_ADMIN_TOKEN", "")
LOOP = int(os.getenv("BULK_CAMPAIGN_LOOP_SEC", "180"))
DB = Path("/opt/batch-emailer/data/emailer.db")
HTML = Path("/opt/batch-emailer/static/templates/portal-premium.html")
FALLBACK_HTML = Path("/opt/batch-emailer/static/templates/portal-light.html")


def api(method: str, path: str, body: dict | None = None, query: str = ""):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}{query}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.load(resp)


def wait_health(timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{BASE}/api/health", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def pending_count() -> int:
    con = sqlite3.connect(DB)
    n = con.execute(
        """
        SELECT COUNT(*) FROM contacts c
        WHERE c.unsubscribed=0
          AND lower(c.email) NOT LIKE '%example%'
          AND lower(c.email) NOT LIKE '%iana.org%'
          AND NOT EXISTS (
            SELECT 1 FROM deliveries d
            WHERE lower(d.email)=lower(c.email) AND d.status='sent'
          )
        """
    ).fetchone()[0]
    con.close()
    return int(n)


def run_once():
    if not wait_health():
        raise RuntimeError("batch-emailer_not_ready")
    # Always sync leads into the mailer contact pool (even when send-capped).
    os.system("bash /root/lead-scraper/sync-to-portal.sh >> /var/log/lead-sync.log 2>&1")
    snap = daily_quota.sent_today()
    daily_quota.write_state({"source": "bulk-campaign-auto"})
    print(
        f"[BULK] daily={snap['sent']}/{snap['max']} remaining={snap['remaining']} "
        f"(auto={snap['auto_contacted']} bulk={snap['bulk_sent']})"
    )
    if snap["capped"]:
        wait = daily_quota.seconds_until_utc_midnight()
        print(f"[BULK] daily cap hit — leads keep syncing; sleep {wait}s until UTC midnight")
        time.sleep(wait)
        return 0
    pending = pending_count()
    print(f"[BULK] pending_contacts={pending}")
    if pending <= 0:
        return 0
    room = daily_quota.remaining()
    if room <= 0:
        return 0
    html_path = HTML if HTML.exists() else FALLBACK_HTML
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    for a, b in (("{company}", "your team"), ("{name}", "there"), ("{{company}}", "your team"), ("{{name}}", "there")):
        html = html.replace(a, b)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    created = api(
        "POST",
        "/api/campaigns",
        {
            "name": f"Auto drain {stamp}",
            "subject": "Portal Biz — cleaner ops for your team",
            "html": html,
            "text": (
                "Portal Biz: CRM, campaigns, vault, AI templates.\n"
                "https://portalbiz.cloudsit.app/public/landing.html\n"
                "Unsubscribe: reply UNSUBSCRIBE\n"
            ),
            "tags": "leads",
        },
    )
    cid = created.get("campaign_id")
    print(f"[BULK] campaign_id={cid}")
    result = api(
        "POST",
        f"/api/campaigns/{cid}/send",
        None,
        f"?dry_run=false&skip_sent=true&limit={room}",
    )
    sent = sum(1 for r in (result.get("results") or []) if r.get("status") == "sent")
    failed = sum(1 for r in (result.get("results") or []) if r.get("status") == "failed")
    print(f"[BULK] targets={result.get('count')} sent={sent} failed={failed} daily={result.get('daily')}")
    if failed:
        print(f"[BULK] fail_sample={str(result.get('results'))[:500]}")
    return sent


def main():
    print(f"[BULK] auto drain start loop={LOOP}s daily_max={daily_quota.daily_max()}")
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"[BULK] error: {e}")
        time.sleep(LOOP)


if __name__ == "__main__":
    main()
