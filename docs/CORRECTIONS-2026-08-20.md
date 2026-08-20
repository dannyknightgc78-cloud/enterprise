# Corrections — 2026-08-20

## Sentinel / Stratus / Phantom / Voice (urgent)
- **Cause:** nginx `root /root/stratus/...` → www-data Permission denied → **500** for public clients; previously also mis-proxied to lab C.A.R.L. `:4173`.
- **Fix:**
  - Deploy Stratus Sentinel UI to `/var/www/sentinel-ui` (readable by nginx).
  - `sentinel` + `stratus` → vault UI + `/vault` `/api` → `:8793`, `/voice` `/face` → `:8795`.
  - `phantom` → `/var/www/phantom-web` (Phantom product, not vault).
  - `voice` → same Sentinel UI (not C.A.R.L.).
- **Verify:** titles `Stratus Sentinel — Stratus Vault` / `Phantom`; header `x-sentinel-origin: stratus-ui-dist`.

## Vultr / Trooper scrub (live monitors)
- Nimbus Live `sites.json` / `servers.json`: no trooper/vultr.
- `WATCH_DEFAULT_NODE_ID=hostman`
- `black-alert.json` `ai_target=rtx-pro` (not trooper)
- `inventory-sync/inventory.json` synced without live trooper/vultr hosts
- `route_guard` → `guard-hostman-routing.sh`
- **Route guard false alarm (2026-08-20):** watchdog-agent Docker was probing `127.0.0.1` (empty in-container) → `Connection refused` / “portal misrouted” for `cloud` + `dashboard` even while public sites returned 200. Fixed: `ROUTE_GUARD_ORIGIN=http://host.docker.internal`, bind-mounted `route_guard.py`, browser UA, bash guard Python fallback (no curl in image), mount `/etc/nginx:ro`. Sites themselves were fine (CloudIt `:8816`, Hub `:3012`).

## cloudflared max-restarts alert (2026-08-20)
- **Cause:** two systemd connectors on the **same** tunnel `8cc6cd76…` (`cloudflared.service` + `cloudflared-mysteryproject.service`) with conflicting ingress → exits / restart storms. Watchdog then alerted “Manual fix needed: cloudflared” (compose advice is wrong — Hostman uses systemd, not docker compose).
- **Fix:** keep a single unit `cloudflared.service` (`/etc/cloudflared/config.yml`, `--protocol http2`); **mask** `cloudflared-mysteryproject`; add `cloudflared*` to `WATCH_EXCLUDE`; stop heal scripts from restarting the duplicate.

## Site audit snapshot
- 111 hostnames probed; ~50 OK titles; many legacy product hostnames still serve lab SPA titled C.A.R.L. via `:4173`/`:8788` (portalbiz stubs, glucose/arthritis SPA shell, etc.) — not Sentinel.

## GhostGrid / vault / RTX (earlier)
- ABX key restored; vault admin open; RTX hybrid CLI wired.

## Ghosts (urgent — was wrong → fixed)
- **Wrong:** Hostman A → `/opt/g7-home` `:3015` (G7 Command Centre).
- **Correct:** Mac **home-edge** tunnel `518d4da0-…` → `127.0.0.1:8850` (**Ghost Home**).
- **Fix:** DNS CNAME `ghosts` → `518d4da0-ca44-4df1-a759-6a2941c61d4f.cfargotunnel.com` (proxied). Disabled Hostman ghosts vhost (`ghosts…conf.disabled-ghosthome-20260820`).
- **G7** moved to `g7.dannygc.cloud` → Hostman `:3015`.
- **Live verify (2026-08-20):** title `Ghost Home`; health `platform=mac+phone`, `aether_ready=true`.
- **Telegram:** plain English “fix ghosts home” / “why is ghosts home not fixed” → probe + auto-repair DNS/nginx if misrouted.
- If a phone still shows G7: hard-refresh / clear Cloudflare cache — edge is already Ghost Home.

## Nimbus / services monitor (bigger board)
- `nimbus.dannygc.cloud` + `services.dannygc.cloud` → Hostman `:3099` (`/opt/nimbus-live`).
- UI: fleet health %, attention rail, key-host chips (ghosts/g7/sentinel/…), filter, infra + lead/emailer pulse, plain-English Telegram tip.
- `sites.json` expect for ghosts tightened to `Ghost Home` (no longer accepts G7 title as OK).

## Telegram plain English
- `@Nimbusfixbot` accepts normal language: status, ghosts fix, services monitor, quiet route-guard, full scan, heal, etc.
- Help `/commands` lists Plain English examples first.

## Lead scraper + bulk emailer (24/7 → 50 good/day)
- **Services always-on:** `lead-scraper`, `lead-feeder`, `auto-emailer`, `batch-emailer`, `bulk-campaign-auto` (`Restart=always`).
- **Quota:** feeder targets **50 good leads/day** (`score>=0.62`, role/corporate, junk filtered). Sleeps when quota met.
- **Feeder v4:** curated UK seed bank + Bing (+ Brave/crt best-effort). DDG abandoned (dead).
- **Quality:** drop sentry/wixpress/noreply; higher score gate; RTX scoring URL `127.0.0.1:18001`.
- **Email:** premium HTML with Portal gallery/home/pricing links + clear **Unsubscribe** CTA; List-Unsubscribe header.
- **Auto send max (2026-08-20):**
  - `auto-emailer` v4: Brevo **HTTP API**, up to **80/run**, loop **90s**, role prefixes only, junk purge.
  - `batch-emailer` uses Brevo API (SMTP login on this account returns 535; API path works).
  - `bulk-campaign-auto`: continuous campaign drain of unsent contacts every **180s** (`skip_sent=true`).
  - `lead-sync.timer`: sync good leads into mailer contacts every **15 min**.
- **Nimbus:** leads endpoints intentionally **not** shown in Nimbus Live.
- **Telegram (2026-08-20):** lead-scraper `alert_lead` posts to Nimbus bot **disabled** (`TELEGRAM_LEADS_ENABLED=0`); scraper/emailer keep running silently.
- **Report:** `python3 /root/lead-scraper/daily-quota-report.py`
- **Constraint:** Brevo free plan / daily send capacity is the hard ceiling (blocked/deferred show in aggregated report).
