# Corrections — 2026-08-20

## Sentinel / Stratus / Phantom / Voice (urgent)
- **Cause:** nginx `root /root/stratus/...` → www-data Permission denied → **500** for public clients; previously also mis-proxied to lab C.A.R.L. `:4173`.
- **Fix:**
  - Deploy Stratus Sentinel UI to `/var/www/sentinel-ui` (readable by nginx).
  - `sentinel` + `stratus` → vault UI + `/vault` `/api` → `:8793`, `/voice` `/face` → `:8795`.
  - `phantom` → `/var/www/phantom-web` (Phantom product, not vault).
  - `voice` → same Sentinel UI (not C.A.R.L.).
- **Verify:** titles `Stratus Sentinel — Stratus Vault` / `Phantom`; header `x-sentinel-origin: stratus-ui-dist`.

## Ghosts
- `ghosts.dannygc.cloud` → `:3015` **G7 — DannyGC Command Centre** (HTTP 200).

## Vultr / Trooper scrub (live monitors)
- Nimbus Live `sites.json` / `servers.json`: no trooper/vultr.
- `WATCH_DEFAULT_NODE_ID=hostman`
- `black-alert.json` `ai_target=rtx-pro` (not trooper)
- `inventory-sync/inventory.json` synced without live trooper/vultr hosts
- `route_guard` → `guard-hostman-routing.sh`

## Site audit snapshot
- 111 hostnames probed; ~50 OK titles; many legacy product hostnames still serve lab SPA titled C.A.R.L. via `:4173`/`:8788` (portalbiz stubs, glucose/arthritis SPA shell, etc.) — not Sentinel.

## GhostGrid / vault / RTX (earlier)
- ABX key restored; vault admin open; RTX hybrid CLI wired.
