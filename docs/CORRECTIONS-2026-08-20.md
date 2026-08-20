# Corrections — 2026-08-20

## GhostGrid / services tamper
- **Cause:** ABX container signing key did not match Aug-11 ledger (`69e9…`).
- **Fix:** Restored matching Ed25519 keypair from Vultr backup into `abx-staging/keys`; restarted `ghostgrid-abx`.
- **Result:** `GET /api/abx/verify` → **PASS**; services `ghostgrid_probe` → `tamper: false`.

## Vault (open admin)
- Added `STRATUS_AUTH_TOKEN` / `NIMBUS_AUTH_TOKEN` to `secrets/lab-vault.env`.
- Hydrated Stratus vault secrets (17): Cloudflare tokens + RTX hybrid URLs.
- Catalog folders: Cloudflare, Nimbus, Dev, **RTX Pro AI**.
- Status: `adminMode=true`, `locked=false`, `integrity.safe=true`.

## RTX hybrid wiring
| Path | How |
|------|-----|
| CPU commands | `rtx-hybrid cpu "…"` → SSH `root@172.236.195.90` |
| LLM | Hostman `:18001` → RTX Ollama (`nemotron-3.5-lightning`, `qwen2.5vl:7b`) |
| TTS | Hostman `:15500` → RTX Piper `:5500` |
| Genie | `INFERENCE_BASE_URL=http://127.0.0.1:18001/v1` |

CLI on Hostman: `rtx-hybrid status|models|chat|cpu|piper`

## Nimbus Live
- `nimbus.dannygc.cloud` → local monitor `:3099` (Telegram on state change).
- Does not rely on tunnels for origin checks; also probes public HTTPS.
