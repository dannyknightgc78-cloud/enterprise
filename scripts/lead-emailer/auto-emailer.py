#!/usr/bin/env python3
"""Auto-emailer 24/7: send good Portal Biz mails up to EMAIL_DAILY_MAX (default 300)."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, "/root/lead-scraper")
import email_daily_quota as daily_quota  # noqa: E402

LOG = Path("/var/log/auto-emailer.log")
sys.stdout = open(LOG, "a", buffering=1)
sys.stderr = sys.stdout

DB_PATH = "/root/lead-scraper/data/leads.db"
API_KEY = os.getenv("BREVO_API_KEY", "").strip()
FROM_EMAIL = os.getenv("FROM_EMAIL", "sales@dannygc.cloud")
FROM_NAME = os.getenv("FROM_NAME", "Portal Biz")
MAX_PER_RUN = int(os.getenv("AUTO_EMAIL_MAX_PER_RUN", "80"))
LOOP_SEC = int(os.getenv("AUTO_EMAIL_LOOP_SEC", "90"))
MIN_SCORE = float(os.getenv("AUTO_EMAIL_MIN_SCORE", "0.62"))
PORTAL = "https://portalbiz.cloudsit.app"
GALLERY = "https://portalbiz.cloudsit.app/public/landing.html"
LANDING = "https://landing.dannygc.cloud/"

SAFE_PREFIXES = (
    "info@", "hello@", "sales@", "contact@", "enquiries@", "enquiry@",
    "office@", "admin@", "team@", "hi@", "mail@", "business@", "partnerships@",
    "support@", "marketing@", "jobs@", "careers@", "press@",
)

BLOCK_SUBSTR = (
    "example.com", "example-biz", "example.org", "test@", "localhost",
    "iana.org", "wixpress", "sentry.", "noreply@", "no-reply@", "donotreply@",
    "mailer-daemon", "postmaster@", "u003e",
)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width"/>
<title>Portal Biz</title></head>
<body style="margin:0;padding:0;background:#0b1220;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b1220;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="600" style="max-width:600px;width:100%;background:#111a2e;border-radius:16px;border:1px solid #243152;overflow:hidden;">
<tr><td style="padding:26px 30px;background:linear-gradient(135deg,#0ea5e9,#6366f1);">
  <div style="font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:rgba(255,255,255,.85);">PORTAL BIZ</div>
  <div style="font-size:24px;font-weight:700;color:#fff;margin-top:8px;line-height:1.25;">A cleaner ops stack for {company}</div>
</td></tr>
<tr><td style="padding:26px 30px;color:#e8eefc;font-size:16px;line-height:1.6;">
  <p style="margin:0 0 14px;">Hi {name},</p>
  <p style="margin:0 0 14px;color:#c5d0e6;">I found <strong style="color:#fff;">{company}</strong> while mapping UK operators who could use a single workspace for leads, docs, automation, and follow-ups.</p>
  <p style="margin:0 0 8px;color:#c5d0e6;"><strong style="color:#fff;">Inside Portal Biz:</strong></p>
  <ul style="margin:0 0 18px;color:#c5d0e6;padding-left:18px;">
    <li>CRM + lead pipeline</li>
    <li>Campaigns with clear unsubscribe</li>
    <li>Document vault + contract tools</li>
    <li>AI drafts and starter templates</li>
  </ul>
  <p style="margin:0 0 10px;">
    <a href="{gallery}" style="display:inline-block;background:#38bdf8;color:#041018;text-decoration:none;font-weight:700;padding:13px 20px;border-radius:10px;">Browse product gallery</a>
  </p>
  <p style="margin:0 0 6px;font-size:14px;">
    <a href="{portal}" style="color:#7dd3fc;">Open Portal Biz</a>
    &nbsp;·&nbsp;
    <a href="{landing}" style="color:#7dd3fc;">Landing page</a>
    &nbsp;·&nbsp;
    <a href="{portal}/pricing.html" style="color:#7dd3fc;">Pricing</a>
  </p>
</td></tr>
<tr><td style="padding:18px 30px 26px;border-top:1px solid #243152;background:#0d1526;">
  <p style="margin:0 0 10px;font-size:12px;line-height:1.5;color:#8fa3c2;">
    You are receiving this as a business contact research outreach.
    <strong style="color:#dbe7ff;">Unsubscribe anytime</strong> — reply with <strong>UNSUBSCRIBE</strong> or use:
  </p>
  <p style="margin:0 0 12px;">
    <a href="mailto:{from_email}?subject=Unsubscribe%20{company}" style="display:inline-block;background:#1a2744;color:#f8fafc;text-decoration:none;font-weight:700;padding:11px 16px;border-radius:8px;border:1px solid #334766;">Unsubscribe from these emails</a>
  </p>
  <p style="margin:0;font-size:11px;color:#6b7c99;">Portal Biz · <a href="{portal}" style="color:#7dd3fc;">{portal}</a></p>
</td></tr>
</table>
</td></tr></table>
</body></html>
"""


def is_sendable(email: str) -> bool:
    e = (email or "").lower().strip()
    if "@" not in e or e.count("@") != 1:
        return False
    if any(b in e for b in BLOCK_SUBSTR):
        return False
    return any(e.startswith(p) for p in SAFE_PREFIXES)


def get_new_leads():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT id, email, domain, meta_json, score FROM leads
        WHERE status IN ('new', 'synced')
          AND score >= ?
          AND IFNULL(is_personal,0)=0
        ORDER BY score DESC
        LIMIT ?
        """,
        (MIN_SCORE, MAX_PER_RUN * 8),
    ).fetchall()
    con.close()
    safe = []
    for r in rows:
        if is_sendable(r["email"] or ""):
            safe.append(dict(r))
    return safe[:MAX_PER_RUN]


def mark(lead_id: int, status: str):
    con = sqlite3.connect(DB_PATH)
    con.execute("UPDATE leads SET status=?, updated_at=? WHERE id=?", (status, time.time(), lead_id))
    con.commit()
    con.close()


def send_email(to: str, company: str, name: str):
    if not API_KEY:
        print("[EMAIL] BREVO_API_KEY missing - skip send")
        return False, True
    html = HTML_TEMPLATE.format(
        name=name,
        company=company,
        portal=PORTAL,
        gallery=GALLERY,
        landing=LANDING,
        from_email=FROM_EMAIL,
    )
    payload = json.dumps(
        {
            "sender": {"name": FROM_NAME, "email": FROM_EMAIL},
            "to": [{"email": to}],
            "subject": f"A simpler way to run {company}",
            "htmlContent": html,
            "textContent": (
                f"Hi {name},\n\nPortal Biz for {company}: CRM, campaigns, vault, AI templates.\n"
                f"Gallery: {GALLERY}\nPortal: {PORTAL}\nLanding: {LANDING}\n\n"
                f"Unsubscribe: reply UNSUBSCRIBE or email {FROM_EMAIL} with subject Unsubscribe.\n"
            ),
            "headers": {"List-Unsubscribe": f"<mailto:{FROM_EMAIL}?subject=Unsubscribe>"},
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={"api-key": API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[EMAIL] sent {to} status={resp.status}")
            return True, False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:400]
        print(f"[EMAIL] fail {to}: HTTP {e.code} {body}")
        if e.code in (401, 402, 403, 429) or e.code >= 500:
            return False, True
        return False, False
    except Exception as e:
        print(f"[EMAIL] fail {to}: {e}")
        return False, False


def company_name(domain: str) -> str:
    d = (domain or "").removeprefix("www.")
    base = d.split(".")[0] if d else "there"
    return base.replace("-", " ").title() or "there"


def purge_junk():
    con = sqlite3.connect(DB_PATH)
    now = time.time()
    n = 0
    rows = con.execute("SELECT id, email FROM leads WHERE status IN ('new','synced')").fetchall()
    for lid, email in rows:
        e = (email or "").lower()
        if any(b in e for b in BLOCK_SUBSTR):
            con.execute("UPDATE leads SET status=?, updated_at=? WHERE id=?", ("skipped", now, lid))
            n += 1
    con.commit()
    con.close()
    if n:
        print(f"[EMAIL] purged junk={n}")


def run_once():
    purge_junk()
    snap = daily_quota.sent_today()
    daily_quota.write_state({"source": "auto-emailer"})
    print(
        f"[EMAIL] daily={snap['sent']}/{snap['max']} remaining={snap['remaining']} "
        f"(auto={snap['auto_contacted']} bulk={snap['bulk_sent']})"
    )
    if snap["capped"]:
        wait = daily_quota.seconds_until_utc_midnight()
        print(f"[EMAIL] daily cap hit — leads keep collecting; sleep {wait}s until UTC midnight")
        time.sleep(wait)
        return 0
    room = min(MAX_PER_RUN, int(snap["remaining"]))
    if room <= 0:
        return 0
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT id, email, domain, meta_json, score FROM leads
        WHERE status IN ('new', 'synced')
          AND score >= ?
          AND IFNULL(is_personal,0)=0
        ORDER BY score DESC
        LIMIT ?
        """,
        (MIN_SCORE, room * 8),
    ).fetchall()
    con.close()
    leads = []
    for r in rows:
        if is_sendable(r["email"] or ""):
            leads.append(dict(r))
        if len(leads) >= room:
            break
    print(
        f"[EMAIL] candidates={len(leads)} min_score={MIN_SCORE} max={room} "
        f"daily_left={snap['remaining']}"
    )
    sent = 0
    for lead in leads:
        email = (lead["email"] or "").lower().strip()
        company = company_name(lead.get("domain") or "")
        ok, hard = send_email(email, company, "there")
        if ok:
            mark(lead["id"], "contacted")
            sent += 1
            if daily_quota.remaining() <= 0:
                print("[EMAIL] daily cap reached mid-run — stop; leads keep collecting")
                break
            time.sleep(0.35)
        elif hard:
            print("[EMAIL] hard stop (quota/auth/server) - wait for next loop")
            break
        else:
            mark(lead["id"], "failed")
            time.sleep(0.2)
    print(f"[EMAIL] sent={sent}")
    return sent


def load_env():
    envp = Path("/root/lead-scraper/.env")
    if not envp.exists():
        return
    for line in envp.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            val = v.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            os.environ.setdefault(k.strip(), val)


def main():
    global API_KEY, MAX_PER_RUN, LOOP_SEC, MIN_SCORE
    load_env()
    API_KEY = os.getenv("BREVO_API_KEY", API_KEY).strip()
    MAX_PER_RUN = int(os.getenv("AUTO_EMAIL_MAX_PER_RUN", str(MAX_PER_RUN)))
    LOOP_SEC = int(os.getenv("AUTO_EMAIL_LOOP_SEC", str(LOOP_SEC)))
    MIN_SCORE = float(os.getenv("AUTO_EMAIL_MIN_SCORE", str(MIN_SCORE)))
    print(
        f"[EMAIL] auto-emailer v5 max/run={MAX_PER_RUN} loop={LOOP_SEC}s score>={MIN_SCORE} "
        f"daily_max={daily_quota.daily_max()}"
    )
    while True:
        try:
            run_once()
        except Exception as e:
            print(f"[EMAIL] loop error: {e}")
        time.sleep(LOOP_SEC)


if __name__ == "__main__":
    main()
