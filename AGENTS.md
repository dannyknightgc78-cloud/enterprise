# RTX hybrid relay — automatic, RTX first, Cursor when needed

## Default (no typing)

Every agent session:

1. **RTX Nemotron first** — routine AI via `https://ai.dannygc.cloud/v1` (MCP `ask_local_ai`)
2. **Cursor when needed** — hard planning, architecture, complex reasoning
3. **Mode `hybrid`** — set automatically on boot (`scripts/rtx-auto-enable.sh`)

Override only if user says **`use cursor`** or **`rtx only`**.

## Cloud Agent instructions

- First turn: silently run `bash scripts/rtx-hybrid-cloud.sh status`
- Prefer RTX for execution-tier work; escalate to Cursor models when quality/complexity requires it
- Never ask user to type mode commands unless tunnel is down

Details: **[infra/rtx-pro/README.md](infra/rtx-pro/README.md)**
