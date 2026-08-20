# RTX Pro hybrid relay — type here, execute on GPU, progress streams back

## Live status (checked from cloud)

| Path | Status |
|------|--------|
| **Nemotron on RTX** via `https://ai.dannygc.cloud/v1` | **LIVE** (`nemotron-3.5-lightning:latest`) |
| **SSH** `root@172.236.195.90` | **Blocked** — authorize key on box |
| **Pool worker** `rtx-pro` | **Not running** until SSH + `CURSOR_API_KEY` |

Cloud agents can use **your RTX Nemotron now** via tunnel when you say `use gpus` (MCP `ask_local_ai` → `ai.dannygc.cloud`). Tool execution (shell/git) still needs the pool worker on the box.

Full setup: **[infra/rtx-pro/README.md](infra/rtx-pro/README.md)**

## Type these in Cursor chat

| You type | What happens |
|----------|----------------|
| **`use gpus`** | Switches to local Nemotron on RTX Pro; tools run on pool `rtx-pro` |
| **`use cursor`** | Switches back to Cursor cloud models (Router) |
| **`gpu status`** | Shows Nemotron + worker relay state |
| **`hybrid`** | Auto: Cursor plans, GPU executes/summarizes |

Progress appears inline (🖥️ running → ✅ done) as if you were on the server.

## One-time: boot your RTX Pro (paste in terminal there)

```bash
curl -fsSL https://raw.githubusercontent.com/dannyknightgc78-cloud/enterprise/cursor/rtx-pro-hybrid-relay-4fb3/infra/rtx-pro/scripts/bootstrap.sh | bash
```

Then edit `/opt/cursor-workers/enterprise/infra/rtx-pro/.env`:
- `NGC_API_KEY` — NVIDIA NGC
- `CURSOR_API_KEY` — **service account** key (Dashboard → Service Accounts)

Restart worker:
```bash
cd /opt/cursor-workers/enterprise/infra/rtx-pro && bash worker/start-worker.sh
```

## Start Cloud Agents on GPU pool

- Dashboard: worker selector → **`rtx-pro`**
- Or include in prompt: **`use gpus`** (hooks auto-switch to local AI)

## MCP tools (on worker)

- `gpu_status` — relay health
- `set_hybrid_mode` — `cursor` | `local` | `hybrid`
- `ask_local_ai` — Nemotron 3.5 on GPU
- `relay_progress` — live server-style log

## Cursor Cloud Agent instructions

When running as a Cloud Agent for this repo:

1. On first turn, call MCP `gpu_status`. If not ready, give user the bootstrap curl command above.
2. Honor user mode switches (`use gpus` / `use cursor`).
3. Prefer pool **`rtx-pro`** for all tool execution.
4. Use **Auto → Cost** for Cursor-side inference when in cursor/hybrid mode.
