#!/usr/bin/env python3
"""Lead feeder v4 — 24/7. Bing + curated banks. Keep collecting (stockpile beyond email cap)."""
from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(line_buffering=True)

SCRAPER_API = os.environ.get("SCRAPER_API", "http://127.0.0.1:8840")
DB_PATH = os.environ.get("DB_PATH", "/root/lead-scraper/data/leads.db")
DAILY_TARGET = int(os.environ.get("DAILY_GOOD_LEAD_TARGET", "500"))
GOOD_SCORE = float(os.environ.get("GOOD_LEAD_MIN_SCORE", "0.62"))
BATCH_SIZE = 20
DELAY = 5

UA = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

SKIP = {
    "google.com","bing.com","microsoft.com","yahoo.com","duckduckgo.com","facebook.com",
    "linkedin.com","twitter.com","x.com","instagram.com","youtube.com","wikipedia.org",
    "amazon.co.uk","ebay.co.uk","gov.uk","bbc.co.uk","yell.com","bark.com","clutch.co",
    "trustpilot.com","crunchbase.com","glassdoor.com","reddit.com","pinterest.com",
}

QUERIES = [
    'UK "web design" agency "contact us" info@',
    'UK "digital agency" "hello@" contact',
    'UK "managed IT" "sales@" OR "info@"',
    'UK "SEO agency" "enquiries@" OR "hello@"',
    'London "marketing agency" contact email',
    'Manchester "software company" contact',
    'Birmingham "IT support" "info@"',
    'UK "SaaS" "book a demo" contact',
    'UK "cyber security" consultancy contact',
    'UK "accountants" "info@" small business',
    'UK "recruitment agency" "hello@"',
    'UK "property management" "enquiries@"',
    'UK "ecommerce agency" contact',
    'UK "WordPress agency" "info@"',
    'UK "creative studio" "hello@"',
    'UK "MSP" "managed service" contact',
    'UK "AI consultancy" OR "automation agency" contact',
    'UK "branding agency" "info@"',
    'UK "video production" "hello@"',
    'UK "HR consultancy" contact email',
]

# High-yield contact page seeds (rotate continuously)

EXTRA_SEEDS = [
    "https://www.superdigital.co.uk/contact","https://www.madebyfire.com/contact",
    "https://www.airship.co.uk/contact","https://www.nudge.digital/contact",
    "https://www.howtocreate.co.uk/contact","https://www.boxuk.com/contact",
    "https://www.magnus.co.uk/contact","https://www.turbine.co.uk/contact",
    "https://www.ctidigital.com/contact","https://www.space48.com/contact",
    "https://www.amp.co.uk/contact","https://www.degould.com/contact",
    "https://www.kubbco.com/contact-us","https://www.zengenti.com/contact",
    "https://www.dxw.com/contact","https://www.torchbox.com/contact",
    "https://www.infomentum.com/contact","https://www.softwire.com/contact",
    "https://www.scottlogic.com/contact","https://www.madgex.com/contact",
    "https://www.cgtrader.com/contact","https://www.gohigheris.com/contact",
    "https://www.brightsolid.com/contact","https://www.nexus.org.uk/contact",
    "https://www.stormid.com/contact","https://www.hipposoftware.co.uk/contact",
    "https://www.codurance.com/contact","https://www.equalexperts.com/contact",
    "https://www.bjss.com/contact","https://www.capgemini.com/gb-en/contact-us/",
    "https://www.methods.co.uk/contact","https://www.kainos.com/contact",
    "https://www.softcat.com/contact","https://www.trustmarque.com/contact",
    "https://www.cdw.co.uk/contact","https://www.computacenter.com/en-gb/contact",
    "https://www.probrand.co.uk/contact","https://www.ukfast.co.uk/contact.html",
    "https://www.ans.co.uk/contact","https://www.nasstar.com/contact",
    "https://www.6dg.co.uk/contact","https://www.advania.co.uk/contact",
    "https://www.bytes.co.uk/contact","https://www.softcat.com/get-in-touch",
]

SEED_BANK = EXTRA_SEEDS + [
    "https://www.bluearray.co.uk/contact","https://www.deepbluemedia.co.uk/contact",
    "https://www.yellowball.co.uk/contact-us","https://www.rebootonline.com/contact/",
    "https://www.impression.co.uk/contact/","https://www.hallam.co.uk/contact/",
    "https://www.rawnet.com/contact","https://www.mediaworks.co.uk/contact-us/",
    "https://www.canddi.com/contact","https://www.reddico.co.uk/contact/",
    "https://www.pragmatic.agency/contact","https://www.weareframework.co.uk/contact",
    "https://www.bluestorm.design/contact","https://www.evolved.net/contact-us/",
    "https://www.netpremacy.com/contact","https://www.cogmedia.co.uk/contact",
    "https://www.pixel-kicks.co.uk/contact","https://www.greensmithdigital.co.uk/contact",
    "https://www.upperhand.co.uk/contact","https://www.digitalfunnel.co.uk/contact",
    "https://www.wolfenden.co.uk/contact/","https://www.brickweb.co.uk/contact-us",
    "https://www.kooky.co.uk/contact","https://www.madebyshape.co.uk/contact",
    "https://www.cti.uk.com/contact","https://www.liquidlight.co.uk/contact",
    "https://www.and.digital/contact","https://www.cxpartners.co.uk/contact",
    "https://www.spacecrafted.com/contact","https://www.thisisgain.com/contact",
    "https://www.angrycreative.com/contact","https://www.distilled.net/contact",
    "https://www.builtvisible.com/contact","https://www.propellernet.co.uk/contact",
    "https://www.journeyfurther.com/contact","https://www.founderandlightning.com/contact",
    "https://www.smartinsights.com/contact","https://www.epiphanysearch.co.uk/contact",
    "https://www.optimisey.com/contact","https://www.clickthrough-marketing.com/contact",
    "https://www.riseatseven.com/contact","https://www.havaslynx.com/contact",
    "https://www.thesearchfactory.co.uk/contact","https://www.kubbco.com/contact",
    "https://www.indieweb.co.uk/contact","https://www.studiolift.com/contact",
    "https://www.simpleweb.co.uk/contact","https://www.designbyfront.com/contact",
    "https://www.spacecraft.co.uk/contact","https://www.zolkc.com/contact",
    "https://www.wearedesignstudio.com/contact","https://www.mrcarlson.co.uk/contact",
    "https://www.nourishcreative.co.uk/contact","https://www.fathom.agency/contact",
    "https://www.amplify.co.uk/contact","https://www.wibble.co.uk/contact",
]


def good_today() -> int:
    try:
        con = sqlite3.connect(DB_PATH)
        n = con.execute(
            """
            SELECT COUNT(*) FROM leads
            WHERE datetime(created_at, 'unixepoch') >= date('now')
              AND score >= ?
              AND IFNULL(is_personal,0)=0
              AND email NOT LIKE '%@sentry.%'
              AND email NOT LIKE '%wixpress%'
              AND (
                is_role=1 OR email LIKE 'info@%' OR email LIKE 'hello@%'
                OR email LIKE 'sales@%' OR email LIKE 'contact@%'
                OR email LIKE 'enquiries@%' OR email LIKE 'office@%'
                OR email LIKE 'team@%' OR email LIKE 'partnerships@%'
              )
            """,
            (GOOD_SCORE,),
        ).fetchone()[0]
        con.close()
        return int(n)
    except Exception as e:
        print(f"[FEED] good_today error: {e}")
        return 0


def _clean_urls(urls: list[str]) -> list[str]:
    seen, clean = set(), []
    for u in urls:
        try:
            p = urllib.parse.urlparse(u)
        except Exception:
            continue
        host = (p.hostname or "").lower().removeprefix("www.")
        if not host or host in SKIP:
            continue
        base = ".".join(host.split(".")[-2:]) if "." in host else host
        if base in SKIP or base in seen:
            continue
        if any(x in host for x in ("bing.", "google.", "yahoo.", "duckduckgo", "microsoft.")):
            continue
        seen.add(base)
        path = (p.path or "/").lower()
        if any(h in path for h in ("/contact", "/about", "/team", "/get-in", "/enquire")):
            clean.append(f"{p.scheme or 'https'}://{p.netloc}{p.path}")
        else:
            clean.append(f"https://{host}/contact")
            clean.append(f"https://{host}/")
        if len(clean) >= BATCH_SIZE:
            break
    # dedupe preserve order
    out, s2 = [], set()
    for u in clean:
        if u not in s2:
            s2.add(u); out.append(u)
    return out[:BATCH_SIZE]


def _bing_unwrap(url: str) -> str:
    # Bing often wraps destinations as ...&u=a1aHR0cHM6Ly...
    try:
        from urllib.parse import urlparse, parse_qs, unquote
        import base64
        qs = parse_qs(urlparse(url).query)
        u = (qs.get("u") or [None])[0]
        if u and u.startswith("a1"):
            raw = u[2:]
            pad = "=" * (-len(raw) % 4)
            return base64.urlsafe_b64decode(raw + pad).decode("utf-8", "ignore")
        if u:
            return unquote(u)
    except Exception:
        pass
    return url


def search_bing(query: str) -> list[str]:
    q = urllib.parse.quote_plus(query)
    url = f"https://www.bing.com/search?q={q}&count=30&setlang=en-gb&cc=GB"
    req = urllib.request.Request(url, headers={"User-Agent": random.choice(UA), "Accept-Language": "en-GB,en;q=0.9"})
    try:
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        hrefs = re.findall(r'href="(https?://[^"]+)"', html)
        cites = re.findall(r'<cite[^>]*>(.*?)</cite>', html, re.I|re.S)
        out = []
        for h in hrefs:
            if "bing.com" in h or "microsoft.com" in h:
                h = _bing_unwrap(h)
            if h.startswith("http"):
                out.append(h)
        for c in cites:
            c = re.sub(r"<[^>]+>", "", c).strip()
            c = c.replace(" › ", "/").replace(" ", "")
            if c and not c.startswith("http"):
                c = "https://" + c
            if c.startswith("http"):
                out.append(c)
        return _clean_urls(out)
    except Exception as e:
        print(f"[BING] {e}")
        return []


def search_brave(query: str) -> list[str]:
    q = urllib.parse.quote_plus(query)
    url = f"https://search.brave.com/search?q={q}&source=web"
    req = urllib.request.Request(url, headers={"User-Agent": random.choice(UA)})
    try:
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        hrefs = re.findall(r'href="(https?://[^"]+)"', html)
        return _clean_urls(hrefs)
    except Exception as e:
        print(f"[BRAVE] {e}")
        return []


def crt_domains(keyword: str) -> list[str]:
    """Pull recent .co.uk domains mentioning keyword from crt.sh (best-effort)."""
    q = urllib.parse.quote(f"%{keyword}%.co.uk")
    url = f"https://crt.sh/?q={q}&output=json"
    req = urllib.request.Request(url, headers={"User-Agent": random.choice(UA)})
    try:
        raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
        data = json.loads(raw) if raw.strip().startswith("[") else []
        hosts = set()
        for row in data[:200]:
            name = (row.get("name_value") or "").lower()
            for part in name.split("\n"):
                part = part.strip().lstrip("*.")
                if part.endswith(".co.uk") and part.count(".") <= 3:
                    hosts.add(part)
        seeds = []
        for h in list(hosts)[:BATCH_SIZE]:
            seeds.append(f"https://{h}/contact")
            seeds.append(f"https://{h}/")
        return seeds[:BATCH_SIZE]
    except Exception as e:
        print(f"[CRT] {e}")
        return []


def submit_job(seeds: list[str], query: str) -> None:
    if not seeds:
        return
    data = json.dumps({"seeds": seeds, "query": query}).encode()
    req = urllib.request.Request(
        f"{SCRAPER_API}/jobs", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            jid = (result.get("job") or {}).get("id", "?")
            print(f"[FEED] Submitted {len(seeds)} → job {jid} | good={good_today()}/{DAILY_TARGET}")
    except Exception as e:
        print(f"[FEED] Submit error: {e}")


def wait_api():
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{SCRAPER_API}/health", timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(2)
    print("[FEED] API not ready — continuing")


def main():
    print(f"[FEED v4] 24/7 — target {DAILY_TARGET}/day score>={GOOD_SCORE}")
    wait_api()
    submit_job(SEED_BANK[:25], "seed-bank-priority")
    time.sleep(3)

    cycle = 0
    crt_kw = ["agency", "digital", "studio", "consult", "media", "tech", "cloud", "design"]
    while True:
        g = good_today()
        if g >= DAILY_TARGET:
            sleep_s = 86400 - (time.time() % 86400) + random.randint(90, 400)
            print(f"[FEED] Quota met ({g}/{DAILY_TARGET}). Sleep {int(sleep_s/60)}m")
            time.sleep(sleep_s)
            continue

        cycle += 1
        # Always push a rotating seed-bank chunk
        random.shuffle(SEED_BANK)
        submit_job(SEED_BANK[:18], f"seed-bank-cycle-{cycle}")
        time.sleep(2)

        random.shuffle(QUERIES)
        found = 0
        for i, query in enumerate(QUERIES):
            if good_today() >= DAILY_TARGET:
                break
            print(f"[FEED] c{cycle} [{i+1}/{len(QUERIES)}] need={DAILY_TARGET-good_today()} | {query[:70]}")
            seeds = search_bing(query) or search_brave(query)
            if seeds:
                submit_job(seeds, query)
                found += len(seeds)
            if i % 5 == 4:
                crt = crt_domains(random.choice(crt_kw))
                if crt:
                    submit_job(crt, f"crt:{crt_kw}")
            time.sleep(DELAY + random.randint(1, 4))

        print(f"[FEED] cycle {cycle} seeds={found} good={good_today()}/{DAILY_TARGET}. pause 60s")
        time.sleep(60)


if __name__ == "__main__":
    main()
