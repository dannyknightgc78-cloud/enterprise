from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import smtplib
import sqlite3
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("BATCH_EMAILER_DB", str(ROOT / "data" / "emailer.db")))
PUBLIC_BASE = os.environ.get("BATCH_EMAILER_PUBLIC_BASE", "https://mailer.cloudsit.app").rstrip("/")
ADMIN_TOKEN = os.environ.get("BATCH_EMAILER_ADMIN_TOKEN", "").strip()
MAX_BATCH = int(os.environ.get("BATCH_EMAILER_MAX_BATCH", "100"))
EMAIL_DAILY_MAX = int(os.environ.get("EMAIL_DAILY_MAX", "300"))


def _utc_day_start() -> float:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _sent_today_counts(conn: sqlite3.Connection) -> dict[str, int]:
    start = _utc_day_start()
    bulk = int(
        conn.execute(
            "SELECT COUNT(*) FROM deliveries WHERE status=? AND created_at>=?",
            ("sent", start),
        ).fetchone()[0]
    )
    auto = 0
    leads_db = Path(os.environ.get("LEADS_DB", "/root/lead-scraper/data/leads.db"))
    if leads_db.is_file():
        lconn = sqlite3.connect(leads_db)
        try:
            auto = int(
                lconn.execute(
                    "SELECT COUNT(*) FROM leads WHERE status=? AND updated_at>=?",
                    ("contacted", start),
                ).fetchone()[0]
            )
        finally:
            lconn.close()
    total = auto + bulk
    return {
        "auto_contacted": auto,
        "bulk_sent": bulk,
        "sent": total,
        "max": EMAIL_DAILY_MAX,
        "remaining": max(0, EMAIL_DAILY_MAX - total),
    }

app = FastAPI(title="Batch Emailer", version="1.0")


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS contacts (
      id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT DEFAULT '', tags TEXT DEFAULT '',
      unsubscribed INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS campaigns (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, subject TEXT NOT NULL, html TEXT NOT NULL,
      text TEXT DEFAULT '', tags TEXT DEFAULT '', created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS deliveries (
      id INTEGER PRIMARY KEY, campaign_id INTEGER NOT NULL, email TEXT NOT NULL,
      status TEXT NOT NULL, detail TEXT DEFAULT '', created_at REAL NOT NULL
    );
    """)
    return conn


def admin(authorization: str | None = Header(default=None)) -> None:
    if not ADMIN_TOKEN or not authorization or not hmac.compare_digest(
        authorization.removeprefix("Bearer ").strip(), ADMIN_TOKEN
    ):
        raise HTTPException(status_code=401, detail="admin_authorization_required")


class Contact(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=160)
    tags: str = Field(default="", max_length=500)


class Campaign(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    subject: str = Field(min_length=1, max_length=240)
    html: str = Field(min_length=1, max_length=500_000)
    text: str = Field(default="", max_length=200_000)
    tags: str = Field(default="", max_length=500)


def token_for(email: str) -> str:
    salt = os.environ.get("BATCH_EMAILER_UNSUBSCRIBE_SALT", ADMIN_TOKEN or "local-salt")
    return hmac.new(salt.encode(), email.lower().encode(), hashlib.sha256).hexdigest()[:32]


def smtp_send(to: str, subject: str, html: str, text: str, unsubscribe: str) -> None:
    """Prefer Brevo HTTP API; fall back to SMTP if configured."""
    import json
    import urllib.error
    import urllib.request

    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    if api_key:
        sender_email = os.environ.get("BREVO_SENDER_EMAIL") or os.environ.get("SMTP_FROM", "sales@dannygc.cloud")
        sender_name = os.environ.get("BREVO_SENDER_NAME", "Portal Biz")
        payload = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html.replace("{{unsubscribe_url}}", unsubscribe),
            "textContent": text or "",
            "headers": {"List-Unsubscribe": f"<{unsubscribe}>"},
        }
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode(),
            headers={
                "api-key": api_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status >= 300:
                    raise RuntimeError(f"brevo_http_{resp.status}")
                return
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")[:300]
            raise RuntimeError(f"brevo_http_{e.code}:{body}") from e

    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        raise RuntimeError("no_email_transport_configured")
    msg = EmailMessage()
    msg["From"] = os.environ.get("SMTP_FROM", "noreply@dannygc.cloud")
    msg["To"] = to
    msg["Subject"] = subject
    msg["List-Unsubscribe"] = f"<{unsubscribe}>"
    msg.set_content(text or "This email is best viewed as HTML.")
    msg.add_alternative(html.replace("{{unsubscribe_url}}", unsubscribe), subtype="html")
    port = int(os.environ.get("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=30) as server:
        if os.environ.get("SMTP_TLS", "1").lower() not in {"0", "false", "no"}:
            server.starttls()
        user, password = os.environ.get("SMTP_USER", ""), os.environ.get("SMTP_PASSWORD", "")
        if user:
            server.login(user, password)
        server.send_message(msg)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (ROOT / "static" / "index.html").read_text()


@app.get("/api/health")
def health() -> dict[str, Any]:
    with db() as conn:
        daily = _sent_today_counts(conn)
    return {
        "ok": True,
        "service": "batch-emailer",
        "smtpConfigured": bool(os.environ.get("SMTP_HOST") or os.environ.get("BREVO_API_KEY")),
        "daily": daily,
    }


@app.get("/api/capabilities")
def capabilities() -> dict[str, Any]:
    return {"ok": True, "features": ["contacts", "tag filtering", "HTML/text templates", "preview", "dry-run", "rate-limited SMTP delivery", "unsubscribe links", "delivery log"]}


@app.get("/u/{token}")
def unsubscribe(token: str):
    with db() as conn:
        rows = conn.execute("SELECT email FROM contacts WHERE unsubscribed=0").fetchall()
        for row in rows:
            if hmac.compare_digest(token_for(row["email"]), token):
                conn.execute("UPDATE contacts SET unsubscribed=1 WHERE email=?", (row["email"],))
                conn.commit()
                return HTMLResponse("""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><title>Unsubscribed</title>
<style>body{margin:0;font-family:DM Sans,system-ui,sans-serif;background:#070b14;color:#eef3ff;display:grid;min-height:100vh;place-items:center;padding:24px}
.card{max-width:520px;background:#0f1628;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:28px}
a{color:#38bdf8;font-weight:700}</style></head>
<body><div class=card><h1>You’re unsubscribed</h1>
<p>You will not receive future Portal Biz campaign emails.</p>
<p><a href=\"https://portalbiz.cloudsit.app/\">Return to Portal Biz</a> · <a href=\"https://portalbiz.cloudsit.app/public/landing.html\">Product gallery</a></p>
</div></body></html>""")
    return HTMLResponse("<h1>Link expired</h1>", status_code=404)


@app.post("/api/contacts", dependencies=[Depends(admin)])
def add_contact(body: Contact):
    with db() as conn:
        conn.execute("INSERT INTO contacts(email,name,tags,created_at) VALUES(?,?,?,?) ON CONFLICT(email) DO UPDATE SET name=excluded.name,tags=excluded.tags", (str(body.email).lower(), body.name, body.tags, time.time()))
        conn.commit()
    return {"ok": True, "email": str(body.email).lower()}


@app.get("/api/contacts", dependencies=[Depends(admin)])
def list_contacts():
    with db() as conn:
        rows = conn.execute("SELECT id,email,name,tags,unsubscribed,created_at FROM contacts ORDER BY id DESC").fetchall()
    return {"ok": True, "contacts": [dict(r) for r in rows]}


@app.post("/api/campaigns", dependencies=[Depends(admin)])
def create_campaign(body: Campaign):
    with db() as conn:
        cur = conn.execute("INSERT INTO campaigns(name,subject,html,text,tags,created_at) VALUES(?,?,?,?,?,?)", (body.name, body.subject, body.html, body.text, body.tags, time.time()))
        conn.commit()
        return {"ok": True, "campaign_id": cur.lastrowid}


def recipients(conn: sqlite3.Connection, tags: str, skip_sent: bool = True, limit: int | None = None) -> list[str]:
    wanted = {x.strip().lower() for x in tags.split(",") if x.strip()}
    rows = conn.execute("SELECT email,tags FROM contacts WHERE unsubscribed=0").fetchall()
    out = []
    cap = MAX_BATCH if limit is None else max(0, min(MAX_BATCH, int(limit)))
    if cap <= 0:
        return []
    for r in rows:
        tags_set = {x.strip().lower() for x in (r["tags"] or "").split(",") if x.strip()}
        if wanted and not wanted.intersection(tags_set):
            continue
        email = r["email"]
        if skip_sent:
            prior = conn.execute(
                "SELECT 1 FROM deliveries WHERE lower(email)=lower(?) AND status='sent' LIMIT 1",
                (email,),
            ).fetchone()
            if prior:
                continue
        out.append(email)
        if len(out) >= cap:
            break
    return out


@app.post("/api/campaigns/{campaign_id}/send", dependencies=[Depends(admin)])
def send_campaign(campaign_id: int, dry_run: bool = True, skip_sent: bool = True, limit: int | None = None):
    with db() as conn:
        campaign = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if not campaign:
            raise HTTPException(404, "campaign_not_found")
        daily = _sent_today_counts(conn)
        room = daily["remaining"]
        if not dry_run and room <= 0:
            return {
                "ok": True,
                "campaign_id": campaign_id,
                "dry_run": dry_run,
                "count": 0,
                "results": [],
                "daily": daily,
                "capped": True,
            }
        effective_limit = room if limit is None else min(int(limit), room)
        if dry_run:
            effective_limit = MAX_BATCH if limit is None else min(MAX_BATCH, int(limit))
        targets = recipients(conn, campaign["tags"], skip_sent=skip_sent, limit=effective_limit)
        results = []
        local_sent = 0
        for email in targets:
            status, detail = ("dry_run", "not sent") if dry_run else ("sent", "")
            try:
                if not dry_run:
                    # Account for uncommitted sends in this request.
                    if daily["remaining"] - local_sent <= 0:
                        status, detail = "skipped", "email_daily_max"
                        results.append({"email": email, "status": status, "detail": detail})
                        break
                    smtp_send(email, campaign["subject"], campaign["html"], campaign["text"], f"{PUBLIC_BASE}/u/{token_for(email)}")
                    local_sent += 1
                    time.sleep(0.25)
            except Exception as e:
                status, detail = "failed", str(e)[:240]
            conn.execute(
                "INSERT INTO deliveries(campaign_id,email,status,detail,created_at) VALUES(?,?,?,?,?)",
                (campaign_id, email, status, detail, time.time()),
            )
            results.append({"email": email, "status": status, "detail": detail})
        conn.commit()
        daily = _sent_today_counts(conn)
    return {
        "ok": True,
        "campaign_id": campaign_id,
        "dry_run": dry_run,
        "count": len(results),
        "results": results,
        "daily": daily,
    }


@app.get("/api/campaigns/{campaign_id}/deliveries", dependencies=[Depends(admin)])
def deliveries(campaign_id: int):
    with db() as conn:
        rows = conn.execute("SELECT email,status,detail,created_at FROM deliveries WHERE campaign_id=? ORDER BY id DESC", (campaign_id,)).fetchall()
    return {"ok": True, "deliveries": [dict(r) for r in rows]}
