"""Watchdog agent configuration from environment."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# Coolify / compose hash prefix: abc12345_homeassistant → treat as homeassistant for excludes.
_GHOST_COMPOSE_PREFIX = re.compile(r"^[a-f0-9]{8,}_(.+)$", re.I)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


# butler-agent + stratus-clinical-agent run via unified_server.py on host (LAB_USE_UNIFIED_AGENTS=1).
# homeassistant — optional; retired Coolify ghosts historically caused heal spam → heal spam.
DEFAULT_WATCH_EXCLUDE = (
    "watchdog-agent,vllm_engine,ollama,mystery-ollama,glucose-agent,carl-whisper,carl-piper,"
    "butler-agent,stratus-clinical-agent,qdrant,homeassistant,ops-agent"
)


def is_excluded_container(
    name: str,
    exclude: list[str] | set[str],
    *,
    compose_service: str = "",
) -> bool:
    # Hostman: tunnel is systemd, never docker-heal cloudflared*
    if (name or "").startswith("cloudflared") or (compose_service or "").startswith("cloudflared"):
        return True
    """True if name / compose service / Coolify-prefixed name is in WATCH_EXCLUDE."""
    if not exclude:
        return False
    ex = {str(x).strip() for x in exclude if str(x).strip()}
    n = (name or "").strip().lstrip("/")
    svc = (compose_service or "").strip()
    if n and n in ex:
        return True
    if svc and svc in ex:
        return True
    m = _GHOST_COMPOSE_PREFIX.match(n)
    if m and m.group(1) in ex:
        return True
    return False


@dataclass(frozen=True)
class WatchdogConfig:
    port: int = field(default_factory=lambda: _env_int("PORT", 8791))
    data_dir: str = field(default_factory=lambda: os.environ.get("WATCHDOG_DATA_DIR", "dashboard-data/watchdog"))
    check_interval_sec: float = field(default_factory=lambda: _env_float("CHECK_INTERVAL_SEC", 30.0))
    docker_host: str = field(default_factory=lambda: os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock"))

    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))
    telegram_enabled: bool = field(default_factory=lambda: _env_bool("TELEGRAM_ENABLED", True))

    watch_containers: list[str] = field(default_factory=lambda: _env_list("WATCH_CONTAINERS"))
    exclude_containers: list[str] = field(
        default_factory=lambda: _env_list("WATCH_EXCLUDE")
        or [p.strip() for p in DEFAULT_WATCH_EXCLUDE.split(",") if p.strip()]
    )
    exclude_images: list[str] = field(
        default_factory=lambda: _env_list("DISCOVER_EXCLUDE_IMAGES")
        or ["sovereign-builder", "ghostos-builder"]
    )
    watch_compose_project: str = field(default_factory=lambda: os.environ.get("WATCH_COMPOSE_PROJECT", ""))

    auto_heal: bool = field(default_factory=lambda: _env_bool("AUTO_HEAL", True))
    max_restarts_per_hour: int = field(default_factory=lambda: _env_int("MAX_RESTARTS_PER_HOUR", 3))
    restart_cooldown_sec: int = field(default_factory=lambda: _env_int("RESTART_COOLDOWN_SEC", 120))

    memory_leak_window: int = field(default_factory=lambda: _env_int("MEMORY_LEAK_WINDOW", 12))
    memory_leak_growth_pct: float = field(default_factory=lambda: _env_float("MEMORY_LEAK_GROWTH_PCT", 25.0))
    memory_leak_min_mb: float = field(default_factory=lambda: _env_float("MEMORY_LEAK_MIN_MB", 256.0))
    memory_leak_exclude: list[str] = field(
        default_factory=lambda: _env_list("MEMORY_LEAK_EXCLUDE")
        or ["carl-whisper", "carl-piper", "vllm_server", "ghostos-builder"]
    )
    memory_alert_pct: float = field(default_factory=lambda: _env_float("MEMORY_ALERT_PCT", 90.0))

    host_memory_alert_pct: float = field(default_factory=lambda: _env_float("HOST_MEMORY_ALERT_PCT", 92.0))
    host_disk_alert_pct: float = field(default_factory=lambda: _env_float("HOST_DISK_ALERT_PCT", 90.0))

    notify_on_heal: bool = field(default_factory=lambda: _env_bool("NOTIFY_ON_HEAL", True))
    notify_on_recovery: bool = field(default_factory=lambda: _env_bool("NOTIFY_ON_RECOVERY", True))
    notify_on_discover: bool = field(default_factory=lambda: _env_bool("NOTIFY_ON_DISCOVER", True))
    dry_run: bool = field(default_factory=lambda: _env_bool("DRY_RUN", False))

    auto_discover: bool = field(default_factory=lambda: _env_bool("AUTO_DISCOVER", True))
    docker_events_enabled: bool = field(default_factory=lambda: _env_bool("DOCKER_EVENTS_ENABLED", True))
    compose_heal: bool = field(default_factory=lambda: _env_bool("COMPOSE_HEAL", True))
    # Services managed outside compose (e.g. Hostman systems-agent systemd on :8788).
    # homeassistant is opt-in and a historical ghost spam source — never compose-heal.
    compose_heal_exclude: list[str] = field(
        default_factory=lambda: _env_list("COMPOSE_HEAL_EXCLUDE") or ["homeassistant"]
    )
    lab_root: str = field(default_factory=lambda: os.environ.get("LAB_ROOT", "/lab"))
    compose_file: str = field(default_factory=lambda: os.environ.get("COMPOSE_FILE", "/lab/docker-compose.yml"))
    compose_project: str = field(default_factory=lambda: os.environ.get("COMPOSE_PROJECT_NAME", "lab-dannygc"))
    memory_heal_pct: float = field(default_factory=lambda: _env_float("MEMORY_HEAL_PCT", 95.0))
    memory_leak_heal: bool = field(default_factory=lambda: _env_bool("MEMORY_LEAK_HEAL", True))

    rule_fix_enabled: bool = field(default_factory=lambda: _env_bool("RULE_FIX_ENABLED", True))
    rule_fix_min_restarts: int = field(default_factory=lambda: _env_int("RULE_FIX_MIN_RESTARTS", 2))

    # Consecutive failed readiness probes required before a bare service is considered
    # down and healed. A single transient probe failure must NOT trigger a restart.
    readiness_fail_threshold: int = field(default_factory=lambda: _env_int("READINESS_FAIL_THRESHOLD", 3))
    readiness_latency_ms_threshold: float = field(
        default_factory=lambda: _env_float("READINESS_LATENCY_MS_THRESHOLD", 8000.0)
    )

    # Quick in-check retry: each probe is attempted up to this many times with a short
    # backoff before being declared a failure, so a transient blip never feeds the streak.
    probe_retry_attempts: int = field(default_factory=lambda: _env_int("PROBE_RETRY_ATTEMPTS", 2))
    probe_retry_backoff_sec: float = field(default_factory=lambda: _env_float("PROBE_RETRY_BACKOFF_SEC", 0.75))

    # Time-evict stale "missing" registry entries (ghost containers) so they stop
    # flooding compose_heal retries. Default 24h grace before a vanished container is dropped.
    registry_missing_grace_sec: float = field(
        default_factory=lambda: _env_float("REGISTRY_MISSING_GRACE_SEC", 86400.0)
    )

    # Verify a bare-service heal actually fixed the probe. A heal that reports OK but
    # leaves the probe red is a probe/heal target mismatch — flagged, not counted as a restart.
    probe_verify_enabled: bool = field(default_factory=lambda: _env_bool("PROBE_VERIFY_ENABLED", True))
    probe_verify_attempts: int = field(default_factory=lambda: _env_int("PROBE_VERIFY_ATTEMPTS", 3))
    probe_verify_delay_sec: float = field(default_factory=lambda: _env_float("PROBE_VERIFY_DELAY_SEC", 2.0))
    probe_heal_mismatch_cooldown_sec: int = field(
        default_factory=lambda: _env_int("PROBE_HEAL_MISMATCH_COOLDOWN_SEC", 1800)
    )

    # Learn-and-heal: remember which remediation fixed a given crash signature and
    # re-apply it (bounded) before escalating to a manual-fix alert.
    learned_heal_enabled: bool = field(default_factory=lambda: _env_bool("LEARNED_HEAL_ENABLED", True))
    learned_heal_max_per_hour: int = field(default_factory=lambda: _env_int("LEARNED_HEAL_MAX_PER_HOUR", 1))

    # Circuit-breaker for repeated failed compose heals (stops ghost/no-such-service floods).
    compose_fail_max: int = field(default_factory=lambda: _env_int("COMPOSE_FAIL_MAX", 3))
    compose_fail_cooldown_sec: int = field(default_factory=lambda: _env_int("COMPOSE_FAIL_COOLDOWN_SEC", 3600))

    # Host bare-process heal daemon (glucose/arthritis/site on Hostman cloudit1).
    lab_heal_url: str = field(default_factory=lambda: os.environ.get("LAB_HEAL_URL", "").strip())
    lab_heal_timeout_sec: float = field(default_factory=lambda: _env_float("LAB_HEAL_TIMEOUT_SEC", 120.0))

    # Consolidate fragmented Butler/SpeakIt/Stratus when VRAM or process count spikes.
    gpu_fragment_heal: bool = field(default_factory=lambda: _env_bool("GPU_FRAGMENT_HEAL", True))
    gpu_vram_alert_pct: float = field(default_factory=lambda: _env_float("GPU_VRAM_ALERT_PCT", 88.0))
    gpu_fragment_min_count: int = field(default_factory=lambda: _env_int("GPU_FRAGMENT_MIN_COUNT", 2))
    gpu_process_storm_count: int = field(default_factory=lambda: _env_int("GPU_PROCESS_STORM_COUNT", 6))
    gpu_fragment_cooldown_sec: int = field(default_factory=lambda: _env_int("GPU_FRAGMENT_COOLDOWN_SEC", 600))
    gpu_fragment_heal_timeout_sec: float = field(
        default_factory=lambda: _env_float("GPU_FRAGMENT_HEAL_TIMEOUT_SEC", 180.0)
    )
    unified_agents_script: str = field(
        default_factory=lambda: os.environ.get(
            "UNIFIED_AGENTS_SCRIPT",
            os.path.join(os.environ.get("LAB_ROOT", "/lab"), "scripts", "start-unified-agents.sh"),
        ).strip()
    )

    # Aegis-Ego → Watchdog quarantine bridge (token-authed, local-network only).
    quarantine_enabled: bool = field(default_factory=lambda: _env_bool("QUARANTINE_ENABLED", True))
    quarantine_token: str = field(default_factory=lambda: os.environ.get("AEGIS_QUARANTINE_TOKEN", "").strip())
    quarantine_default_mode: str = field(
        default_factory=lambda: (os.environ.get("QUARANTINE_DEFAULT_MODE", "freeze").strip() or "freeze")
    )
    quarantine_max_per_hour: int = field(default_factory=lambda: _env_int("QUARANTINE_MAX_PER_HOUR", 5))
    quarantine_cooldown_sec: int = field(default_factory=lambda: _env_int("QUARANTINE_COOLDOWN_SEC", 60))
    quarantine_allow_cidrs: list[str] = field(
        default_factory=lambda: _env_list("QUARANTINE_ALLOW_CIDRS")
        or ["127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    )

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def is_excluded(self, name: str, *, compose_service: str = "") -> bool:
        return is_excluded_container(
            name,
            self.exclude_containers,
            compose_service=compose_service,
        )


def load_config() -> WatchdogConfig:
    return WatchdogConfig()
