# Mobile + Mac + RTX setup

## What you want

| Device | Role |
|--------|------|
| **iPhone/iPad (Cursor app)** | Talk to agents remotely |
| **RTX Pro (`172.236.195.90`)** | Run shell, git, builds, GPU AI |
| **Mac** | Normal Cursor desktop — not the GPU worker |

## Mobile → RTX (recommended)

1. Install **[Cursor for iOS](https://apps.apple.com/app/cursor/id6767085653)** and sign in.
2. Dashboard → **Cloud Agents → Self-Hosted → Allow Self-Hosted Agents**.
3. Complete GPU worker on RTX (one-time Hostman console paste — see below).
4. In the **mobile app**, start an agent on repo `enterprise`:
   - Pick worker: **Self-Hosted Pool → `rtx-pro`**
   - Branch: `main`
5. Hybrid AI is automatic (RTX Nemotron first, Cursor when needed).

Mobile does **not** run models on the phone — it controls cloud agents that execute on **RTX**.

## Mac — keep using desktop normally

Your Mac is **not** the GPU worker unless you choose that.

| Mac use | Runs on |
|---------|---------|
| Desktop Cursor coding (local) | Mac |
| Cloud Agents with pool **`rtx-pro`** | **RTX** |
| **Remote Control** (`/remote-control`) | **Mac** (tools stay on Mac) |

**Do not use Remote Control** if you want RTX execution — use **Cloud Agent + pool `rtx-pro`** instead.

Mac and mobile share the same agents at [cursor.com/agents](https://cursor.com/agents).

## One-time: GPU worker (Hostman console)

```bash
export CURSOR_API_KEY='YOUR_SERVICE_ACCOUNT_KEY'
curl -fsSL https://raw.githubusercontent.com/dannyknightgc78-cloud/enterprise/main/infra/rtx-pro/scripts/setup-gpu-worker-console.sh | bash
```

Service account key: **Dashboard → Service Accounts** (Enterprise).

## Let cloud agents run setup for you (secrets)

Add these in **Dashboard → Cloud Agents → Secrets** (team or environment):

| Secret | Value |
|--------|--------|
| `CURSOR_API_KEY` | Service account key (starts worker, API calls) |
| `RTX_SSH_PRIVATE_KEY` | Full PEM private key matching authorized key on box |

Then start a new cloud agent — it can SSH and run setup without you pasting.

Our public key to authorize on the box:

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGh5uzhhDMuW+reaCiInxGD2EetWAK+QyxnW0TFnvxeu cursor-cloud-agent
```

## Verify worker

```bash
bash scripts/rtx-hybrid-cloud.sh status
```

Pool `rtx-pro` should show connected workers in **Dashboard → Cloud Agents → Self-Hosted**.
