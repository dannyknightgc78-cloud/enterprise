#!/usr/bin/env python3
"""Shared daily send cap for Portal Biz emailers (UTC day)."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEADS_DB = Path(os.environ.get("LEADS_DB", "/root/lead-scraper/data/leads.db"))
EMAILER_DB = Path(os.environ.get("BATCH_EMAILER_DB", "/opt/batch-emailer/data/emailer.db"))
STATE = Path(os.environ.get("EMAIL_DAILY_STATE", "/var/lib/portal-emailer/daily.json"))


def daily_max() -> int:
    return max(0, int(os.environ.get("EMAIL_DAILY_MAX", "300")))


def utc_day_start() -> float:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def _count_leads_contacted(start: float) -> int:
    if not LEADS_DB.is_file():
        return 0
    con = sqlite3.connect(LEADS_DB)
    try:
        return int(
            con.execute(
                "SELECT COUNT(*) FROM leads WHERE status=? AND updated_at>=?",
                ("contacted", start),
            ).fetchone()[0]
        )
    finally:
        con.close()


def _count_deliveries_sent(start: float) -> int:
    if not EMAILER_DB.is_file():
        return 0
    con = sqlite3.connect(EMAILER_DB)
    try:
        return int(
            con.execute(
                "SELECT COUNT(*) FROM deliveries WHERE status=? AND created_at>=?",
                ("sent", start),
            ).fetchone()[0]
        )
    finally:
        con.close()


def sent_today() -> dict:
    start = utc_day_start()
    auto = _count_leads_contacted(start)
    bulk = _count_deliveries_sent(start)
    total = auto + bulk
    cap = daily_max()
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "auto_contacted": auto,
        "bulk_sent": bulk,
        "sent": total,
        "max": cap,
        "remaining": max(0, cap - total),
        "capped": total >= cap,
    }


def remaining() -> int:
    return int(sent_today()["remaining"])


def seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    nxt = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(60, int((nxt - now).total_seconds()))


def write_state(extra: dict | None = None) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    doc = sent_today()
    if extra:
        doc.update(extra)
    STATE.write_text(json.dumps(doc, indent=2) + "\n")
