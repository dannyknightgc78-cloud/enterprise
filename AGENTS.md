# RTX Pro hybrid relay — automatic, no typing required

## Default behavior (automatic)

Every agent session for this repo **automatically**:

- Routes **local AI** to your RTX Nemotron via `https://ai.dannygc.cloud/v1` (live)
- Sets mode **`local`** on session start (hooks + `scripts/rtx-auto-enable.sh`)
- Uses MCP **`ask_local_ai`** for routine execution work (saves Cursor tokens)
- Uses **Cursor models** only for hard planning/reasoning

**You do not need to type `use gpus`, `gpu status`, or switch commands.**

Override only if you explicitly say **`use cursor`**.

## Cursor Cloud Agent instructions

1. **First turn:** run `bash scripts/rtx-hybrid-cloud.sh status` silently — do not prompt the user.
2. **Default:** use MCP `ask_local_ai` for summaries, refactors, test output, repetitive tasks.
3. **Never** ask the user to paste bootstrap or type mode commands unless tunnel is down.
4. Prefer pool **`rtx-pro`** when available; if worker offline, continue with tunnel AI + cloud tools without blocking.

## Infrastructure

| Path | Auto? |
|------|-------|
| Nemotron AI | ✅ Auto via `ai.dannygc.cloud` |
| Shell/git on RTX box | Needs pool worker (one-time server setup) |

Details: **[infra/rtx-pro/README.md](infra/rtx-pro/README.md)**
