# RTX Pro hybrid relay

See **[infra/rtx-pro/README.md](infra/rtx-pro/README.md)** for full setup.

## Cursor Cloud Agent instructions

When running as a Cloud Agent for this repo, prefer the **RTX Pro self-hosted pool** so tool execution (shell, git, builds) runs on local GPUs instead of Cursor-managed VMs.

### Trigger self-hosted pool

- Dashboard: worker selector → pool **`rtx-pro`**
- GitHub comment: `@cursoragent pool=rtx-pro <task>`
- Slack: `@Cursor pool=rtx-pro <task>`

### Model routing (token savings)

- Use **Auto → Cost** in the model picker for Cursor Router (Teams/Enterprise).
- Hard multi-step planning stays on frontier models in the cloud.
- High-volume execution inference on the worker box uses **Nemotron 3.5 Lightning** via `http://127.0.0.1:4000/v1` (LiteLLM model `execution`).

### Prerequisites on RTX Pro

1. `infra/rtx-pro/.env` with `NGC_API_KEY` and `CURSOR_API_KEY` (service account)
2. `docker compose up -d` in `infra/rtx-pro/`
3. `bash infra/rtx-pro/worker/start-worker.sh` running under systemd or tmux

### Verify relay

```bash
bash infra/rtx-pro/scripts/preflight.sh
```
