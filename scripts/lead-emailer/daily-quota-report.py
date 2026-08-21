#!/usr/bin/env python3
"""Daily quota report: leads keep collecting; email capped at EMAIL_DAILY_MAX."""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, "/root/lead-scraper")
import email_daily_quota as daily_quota  # noqa: E402

DB = "/root/lead-scraper/data/leads.db"
LEAD_TARGET = int(os.environ.get("DAILY_GOOD_LEAD_TARGET", "500"))
con = sqlite3.connect(DB)
good = con.execute(
    """
SELECT COUNT(*) FROM leads
WHERE datetime(created_at,'unixepoch') >= date('now')
  AND score>=0.62 AND IFNULL(is_personal,0)=0
  AND email NOT LIKE '%@sentry.%'
"""
).fetchone()[0]
total = con.execute(
    "SELECT COUNT(*) FROM leads WHERE datetime(created_at,'unixepoch') >= date('now')"
).fetchone()[0]
contacted = con.execute(
    "SELECT COUNT(*) FROM leads WHERE status='contacted' AND datetime(updated_at,'unixepoch') >= date('now')"
).fetchone()[0]
pending = con.execute(
    """
SELECT COUNT(*) FROM leads
WHERE status IN ('new','synced') AND score>=0.62 AND IFNULL(is_personal,0)=0
"""
).fetchone()[0]
con.close()
email = daily_quota.sent_today()
print(
    json.dumps(
        {
            "date": time.strftime("%Y-%m-%d"),
            "good_today": good,
            "lead_target": LEAD_TARGET,
            "total_today": total,
            "pending_good": pending,
            "contacted_today": contacted,
            "email_sent": email["sent"],
            "email_max": email["max"],
            "email_remaining": email["remaining"],
            "email_capped": email["capped"],
        }
    )
)
