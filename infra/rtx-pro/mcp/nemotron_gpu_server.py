#!/usr/bin/env python3
"""MCP server: local Nemotron on RTX Pro + hybrid mode switch (cursor vs local AI)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
MODE_FILE = ROOT / ".hybrid-mode"
PROGRESS_LOG = Path("/tmp/cursor-gpu-relay-progress.log")

LITELLM_URL = os.environ.get(
    "LITELLM_URL", "http://127.0.0.1:4000/v1/chat/completions"
)
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "sk-rtx-local")
NIM_URL = os.environ.get("NIM_HEALTH_URL", "http://127.0.0.1:8000/v1/models")

mcp = FastMCP("nemotron-gpu")


def _log_progress(message: str) -> None:
    line = json.dumps({"msg": message})
    try:
        with PROGRESS_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        r = httpx.get(url, timeout=timeout)
        return r.status_code < 400
    except Exception:
        return False


def _read_mode() -> str:
    try:
        mode = MODE_FILE.read_text(encoding="utf-8").strip().lower()
        if mode in {"cursor", "local", "hybrid"}:
            return mode
    except OSError:
        pass
    return "hybrid"


def _write_mode(mode: str) -> None:
    MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODE_FILE.write_text(mode, encoding="utf-8")
    _log_progress(f"hybrid mode -> {mode}")


@mcp.tool()
def gpu_status() -> str:
    """Check RTX Pro relay: Nemotron NIM, LiteLLM, hybrid mode, and worker health."""
    nim = _http_ok(NIM_URL)
    litellm = _http_ok(LITELLM_URL.replace("/v1/chat/completions", "/health/liveliness"))
    mode = _read_mode()
    gpu_name = "unknown"
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            gpu_name = out.stdout.strip().split("\n")[0]
    except Exception:
        pass

    status = {
        "hardware": gpu_name,
        "nemotron_nim": nim,
        "litellm_gateway": litellm,
        "hybrid_mode": mode,
        "pool": os.environ.get("CURSOR_WORKER_POOL_NAME", "rtx-pro"),
        "progress_log": str(PROGRESS_LOG),
        "ready": nim and litellm,
    }
    _log_progress(f"gpu_status ready={status['ready']} mode={mode}")
    return json.dumps(status, indent=2)


@mcp.tool()
def get_hybrid_mode() -> str:
    """Return current AI routing mode: cursor (cloud Router), local (Nemotron), or hybrid."""
    return _read_mode()


@mcp.tool()
def set_hybrid_mode(mode: str) -> str:
    """Switch AI routing: 'cursor' = Cursor cloud models, 'local' = Nemotron on GPU, 'hybrid' = auto."""
    mode = mode.strip().lower()
    if mode not in {"cursor", "local", "hybrid"}:
        return json.dumps({"error": "mode must be cursor, local, or hybrid"})
    _write_mode(mode)
    return json.dumps({"hybrid_mode": mode, "message": f"Switched to {mode} AI"})


@mcp.tool()
def ask_local_ai(prompt: str, model: str = "execution") -> str:
    """Send a prompt to Nemotron 3.5 on local RTX Pro GPU (zero API token cost)."""
    mode = _read_mode()
    if mode == "cursor":
        return json.dumps(
            {
                "skipped": True,
                "reason": "hybrid mode is cursor — say 'use gpus' or set_hybrid_mode('local') first",
            }
        )

    _log_progress(f"ask_local_ai model={model} chars={len(prompt)}")
    try:
        r = httpx.post(
            LITELLM_URL,
            headers={
                "Authorization": f"Bearer {LITELLM_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 1.0,
                "top_p": 0.95,
                "max_tokens": 4096,
            },
            timeout=120.0,
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        _log_progress("ask_local_ai done")
        return content
    except Exception as e:
        _log_progress(f"ask_local_ai error: {e}")
        return json.dumps({"error": str(e), "hint": "Run: cd infra/rtx-pro && docker compose up -d"})


@mcp.tool()
def relay_progress(limit: int = 20) -> str:
    """Return recent GPU relay progress lines (same stream shown during tool execution)."""
    if not PROGRESS_LOG.exists():
        return json.dumps({"lines": [], "message": "No progress yet"})
    lines = PROGRESS_LOG.read_text(encoding="utf-8").strip().splitlines()
    tail = lines[-limit:] if limit > 0 else lines
    parsed = []
    for line in tail:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            parsed.append({"msg": line})
    return json.dumps({"lines": parsed}, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
