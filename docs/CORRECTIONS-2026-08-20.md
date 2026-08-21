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
- **Route guard false alarm (2026-08-20 → 2026-08-21):** watchdog-agent Docker was probing `127.0.0.1` (empty in-container) → `Connection refused` / “portal misrouted” for `cloud` + `dashboard` even while public sites returned 200. Fixed: `ROUTE_GUARD_ORIGIN=http://195.133.93.104`, `ROUTE_GUARD_TELEGRAM=0` (default), bind-mounted `route_guard.py` + `monitor.py` (monitor also requires explicit Telegram opt-in), browser UA, bash guard default origin Hostman IP, debounce. Sites themselves were fine (CloudIt `:8816`, Hub `:3012`).

## cloudflared max-restarts alert (2026-08-20 → hardened 2026-08-21)
- **Cause:** two systemd connectors on the **same** tunnel `8cc6cd76…` (`cloudflared.service` + `cloudflared-mysteryproject.service`) with conflicting ingress → exits / restart storms. Watchdog then alerted “Manual fix needed: cloudflared” (compose advice is wrong — Hostman uses systemd, not docker compose).
- **Also (2026-08-21):** `/root/lab-dannygc/.env` `WATCH_EXCLUDE` **overrode** compose defaults and **omitted** `cloudflared*`, so watchdog still tried docker-heal on tunnel name → max-restarts Telegram pages. Heal cron `heal-hostman-services.sh` defaulted `LAB_ROOT` to a **Mac path** and blindly `systemctl restart cloudflared` on public degrade.
- **Fix:**
  - keep a single unit `cloudflared.service` (`/etc/cloudflared/config.yml`, `--protocol http2`); **mask** `cloudflared-mysteryproject`
  - `WATCH_EXCLUDE` includes `cloudflared,cloudflared-cloudme,cloudflared-mysteryproject,cloudflared-lab`
  - `config.is_excluded_container` hard-skips any `cloudflared*` name
  - heal cron: `LAB_ROOT=/root/lab-dannygc`; only **start if inactive** (no restart spam)
  - unit: `StartLimitIntervalSec` under `[Unit]` (not `[Service]`)
- **Live:** `cloudflared` active since 2026-08-20; mysteryproject masked; sites `cloud`/`dashboard` HTTP 200.

## Site audit snapshot
- 111 hostnames probed; ~50 OK titles; many legacy product hostnames still serve lab SPA titled C.A.R.L. via `:4173`/`:8788` (portalbiz stubs, glucose/arthritis SPA shell, etc.) — not Sentinel.

## GhostGrid / vault / RTX (earlier)
- ABX key restored; vault admin open; RTX hybrid CLI wired.

## Ghosts (urgent — was wrong → fixed → Hostman fallback 2026-08-21)
- **Wrong:** Hostman A → `/opt/g7-home` `:3015` (G7 Command Centre).
- **Correct (Mac):** home-edge tunnel `518d4da0-…` → `127.0.0.1:8850` (**Ghost Home**).
- **2026-08-21:** home-edge went **down** (0 connections) → public **530/1033**. Served cached **Ghost Home** on Hostman (`/var/www/ghost-home`), moved hostname onto Hostman tunnel `8cc6cd76-…`, removed from dead home-edge ingress. Health: `platform=hostman-fallback`.
- **Restore Mac later:** start home-edge cloudflared on Mac, CNAME `ghosts` back to `518d4da0….cfargotunnel.com`, remove Hostman ingress rule.
- **G7** stays on `g7.dannygc.cloud` only.

## Live heal Telegram spam (2026-08-21)
- `@Nimbusfixbot` was paging every failed live heal (genie/butler/gpu) including Trooper `fix-empire-tunnel.sh` output and Mac-path errors.
- **Fix:** `NIMBUS_LIVE_HEAL_TELEGRAM=0` (default); only Hostman may live-heal; GPU heal uses `trooper-ai-tunnel` not Trooper tunnel script; Telegram only on success if explicitly enabled; longer cooldowns.

## Nimbus / services monitor (bigger board)
- `nimbus.dannygc.cloud` + `services.dannygc.cloud` → Hostman `:3099` (`/opt/nimbus-live`).
- UI: fleet health %, attention rail, key-host chips (ghosts/g7/sentinel/…), filter, infra + lead/emailer pulse, plain-English Telegram tip.
- `sites.json` expect for ghosts tightened to `Ghost Home` (no longer accepts G7 title as OK).

## Telegram plain English
- `@Nimbusfixbot` accepts normal language: status, ghosts fix, services monitor, quiet route-guard, full scan, heal, etc.
- Help `/commands` lists Plain English examples first.

## landing.dannygc.cloud (was missing → gallery → suite login → black/gold marketing)
- **Cause:** no DNS/vhost; restores briefly hit the cyan **product gallery** then the **suite login shell** (wrong colours/layout).
- **Correct:** black-and-gold marketing home (`/opt/portal-biz/public/home-landing.html`, accent `#c9a962` on `#070b14`) — same visual language as Portal Biz product sites.
- **Suite login** stays at `https://portalbiz.cloudsit.app/`.
- **Gallery** stays at `https://portalbiz.cloudsit.app/public/landing.html`.
- **Also:** suite demo button + public pricing restyled to gold (were green/blue leftovers).
- **Verify:** `https://landing.dannygc.cloud/` shows `<h1>Portal Biz</h1>` + `#c9a962`, HTTP 200.

## G7 vs RTX Pro (AI / load)
- **RTX Pro** `172.236.195.90` **is** the live AI: 2× RTX PRO 6000 Blackwell (~96GB). Hostman SSH tunnel `:18000` → vLLM **Qwen3-VL-30B**, `:18001` → Ollama **nemotron-3.5-lightning** + **qwen2.5vl:7b**. Public `ai`/`api`/`nemotron`/`qwen`/`ollama.dannygc.cloud` hit `:18001`.
- **USA G7** `172.233.177.166`: 50 CPU / 125GB RAM / 2.5TB, **no GPU**, nginx off, idle. Fine as a **web origin replica / failover**, not GPU load-balance. AI stays on RTX Pro.

## Lead scraper + bulk emailer (24/7)
- **Services always-on:** `lead-scraper`, `lead-feeder`, `auto-emailer`, `batch-emailer`, `bulk-campaign-auto` (`Restart=always`).
- **Leads keep collecting:** feeder stockpile target **500 good/day** (`score>=0.62`). Continues even when email is capped.
- **Email hard cap (2026-08-21):** **`EMAIL_DAILY_MAX=300`** (UTC day) across auto-emailer + batch/bulk.
  - Shared helper: `/root/lead-scraper/email_daily_quota.py`
  - At cap: emailers sleep until UTC midnight; lead scrape/sync still runs.
  - `auto-emailer` v5: max **40/run**, loop **120s**, respects remaining daily room.
  - `batch-emailer` `/api/campaigns/{id}/send?limit=` + health `daily` block.
  - `bulk-campaign-auto`: still syncs contacts when capped; only sends while room left.
- **Feeder v4:** curated UK seed bank + Bing (+ Brave/crt best-effort). DDG abandoned (dead).
- **Quality:** drop sentry/wixpress/noreply; higher score gate; RTX scoring URL `127.0.0.1:18001`.
- **Email:** premium HTML with Portal gallery/home/pricing links + clear **Unsubscribe** CTA; List-Unsubscribe header.
- **lead-sync.timer:** sync good leads into mailer contacts every **15 min**.
- **Nimbus:** leads endpoints intentionally **not** shown in Nimbus Live.
- **Telegram:** lead-scraper posts to Nimbus bot **disabled** (`TELEGRAM_LEADS_ENABLED=0`).
- **Report:** `python3 /root/lead-scraper/daily-quota-report.py` (includes `email_sent` / `email_max` / `email_remaining`).
- **Constraint:** Brevo plan capacity still applies under the 300/day software cap.
