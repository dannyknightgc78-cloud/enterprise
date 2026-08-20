# RTX Pro Hybrid Relay — Enterprise GPU Pool

Route **Cloud Agent tool execution** to your RTX Pro box while keeping **Cursor Router** for frontier planning in the cloud. Local **Nemotron 3.5 Lightning** handles high-volume execution-tier inference at zero API token cost.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Cursor Cloud (you / dashboard / this agent)                │
│  • Agent loop + Cursor Router (Auto → Cost/Balance)         │
│  • Frontier models for hard reasoning                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS outbound (no inbound ports)
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  RTX Pro workstation (pool=rtx-pro)                         │
│  ┌─────────────────┐  ┌──────────────────────────────────┐  │
│  │ agent worker    │  │ Nemotron 3.5 NIM (NVFP4, GPU)    │  │
│  │ shell/git/build │  │ + LiteLLM → model: execution     │  │
│  └─────────────────┘  └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

| Layer | Where | Saves tokens how |
|-------|--------|------------------|
| Planning / hard edits | Cursor Router (cloud) | Routes routine turns to Grok 4.5 / Composer |
| Tool execution | RTX Pro worker | No cloud VM compute; local builds/tests |
| Execution inference | Nemotron 3.5 local | No per-token API billing |

## Quick start (on RTX Pro)

```bash
git clone https://github.com/dannyknightgc78-cloud/enterprise.git /opt/cursor-workers/enterprise
cd /opt/cursor-workers/enterprise/infra/rtx-pro

cp .env.example .env
# Edit: NGC_API_KEY, CURSOR_API_KEY (service account)

bash scripts/install-rtx-pro.sh
bash scripts/preflight.sh
bash worker/start-worker.sh
```

## Cursor dashboard (one-time admin)

1. **Cloud Agents → Self-Hosted** → enable **Allow Self-Hosted Agents** (or **Require** for all runs)
2. **Team Settings → Models** → enable **Cursor Router** + **Grok 4.5**; default **Auto → Cost**
3. Create a **service account** API key (personal keys cannot start pool workers)

## Trigger agents on RTX Pro

| Surface | Trigger |
|---------|---------|
| Cloud Agent chat | Select pool **rtx-pro** in worker selector |
| GitHub | `@cursoragent pool=rtx-pro fix the CI config` |
| Slack | `@Cursor pool=rtx-pro ...` |
| API | `"usePrivateWorker": true, "labels": ["pool=rtx-pro"]` |

## Local Nemotron (optional scripts/hooks)

```bash
bash scripts/route-local.sh execution "Summarize this diff in 3 bullets"
```

OpenAI-compatible endpoints on the RTX Pro box:

- NIM direct: `http://127.0.0.1:8000/v1`
- LiteLLM logical models: `http://127.0.0.1:4000/v1` (`execution`, `fast-chat`)

## Files

| Path | Purpose |
|------|---------|
| `docker-compose.yml` | Nemotron NIM + LiteLLM + health sidecar |
| `litellm/config.yaml` | Routes to local Nemotron |
| `worker/start-worker.sh` | Registers pool worker with Cursor cloud |
| `worker/labels.json` | `hardware=rtx-pro`, `inference=nemotron-3.5-lightning` |
| `systemd/*.service` | Boot persistence |
| `scripts/install-rtx-pro.sh` | One-shot installer |

## Notes

- The **agent inference loop stays in Cursor cloud** unless you BYOK a custom endpoint. This stack relays **tool calls** and provides **local Nemotron** for worker-side scripts.
- Worker needs outbound HTTPS to `api2.cursor.sh` and `api2direct.cursor.sh`.
- NGC login required for NIM image pulls: https://org.ngc.nvidia.com/setup/api-key
