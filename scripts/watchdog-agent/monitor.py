"""Background monitoring loop — health checks, memory leaks, host alerts, auto-discovery."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import psutil

from compose_healer import ComposeHealer
from config import WatchdogConfig
from docker_client import DockerWatch
from docker_events import DockerEventWatcher
from healer import SelfHealer
from memory_tracker import MemoryTracker
from gpu_healer import GpuHealer
from process_healer import ProcessHealer
from route_guard import scan as route_guard_scan
from readiness import probe_for_container, probe_needs_heal, run_readiness_checks
from registry import ContainerRegistry
from storage import EventStore
from telegram_notifier import TelegramNotifier

log = logging.getLogger("watchdog.monitor")

# Wait for Docker to finish create/restart before healing — avoids false heals during compose.
_TRANSIENT_STATUSES = frozenset({"created", "restarting", "removing"})


class WatchdogMonitor:
    def __init__(
        self,
        config: WatchdogConfig,
        docker: DockerWatch,
        store: EventStore,
        telegram: TelegramNotifier,
        healer: SelfHealer,
        process_healer: ProcessHealer,
        gpu_healer: GpuHealer,
        memory: MemoryTracker,
        registry: ContainerRegistry,
        compose_healer: ComposeHealer,
    ) -> None:
        self._config = config
        self._docker = docker
        self._store = store
        self._telegram = telegram
        self._healer = healer
        self._process_healer = process_healer
        self._gpu_healer = gpu_healer
        self._memory = memory
        self._registry = registry
        self._compose_healer = compose_healer
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_status: dict[str, str] = {}
        self._host_alerted = {"memory": False, "disk": False}
        self._docker_alerted = False
        self._readiness_failures: dict[str, int] = {}
        self._event_lock = threading.Lock()
        self._events = DockerEventWatcher(config, self._on_docker_event)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="watchdog-monitor", daemon=True)
        self._thread.start()
        self._events.start()
        log.info(
            "Watchdog monitor started (interval=%ss, auto_discover=%s, events=%s)",
            self._config.check_interval_sec,
            self._config.auto_discover,
            self._config.docker_events_enabled,
        )

    def stop(self) -> None:
        self._stop.set()
        self._events.stop()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def last_scan(self) -> dict[str, Any]:
        return self._store.load_state()

    def _on_docker_event(self, event: dict[str, Any]) -> None:
        """Immediate heal on die/oom/unhealthy — don't wait for poll cycle."""
        name = event.get("name", "")
        reason = f"docker event: {event.get('reason', event.get('action'))}"
        compose_svc = event.get("compose_service") or ""
        log.warning("Docker event %s on %s", event.get("action"), name)
        self._store.append_event({"type": "docker_event", "container": name, **event})

        with self._event_lock:
            if not self._docker.available:
                return
            if self._config.is_excluded(name, compose_service=str(compose_svc)):
                self._registry.unwatch(name, reason=f"{reason} (excluded)")
                return
            if not self._docker.container_exists(name):
                self._registry.unwatch(name, reason=reason)
                return
            row = self._docker.get_container_row(name)
            if row is None and compose_svc:
                if self._config.is_excluded(compose_svc, compose_service=str(compose_svc)):
                    return
                self._registry.record_failure(name, reason)
                self._compose_healer.compose_up(compose_svc, reason=reason)
                return
            if row is not None:
                self._registry.record_failure(name, reason)
                result = self._healer.heal_container(row, reason=reason)
                if result.get("ok") and not result.get("cancelled"):
                    self._registry.record_heal(name, reason)

    def _is_excluded(self, name: str, row: dict[str, Any] | None = None) -> bool:
        svc = (row or {}).get("compose_service") or ""
        return self._config.is_excluded(name, compose_service=str(svc))

    def _heal_row(self, row: dict[str, Any], *, reason: str, actions: list[dict[str, Any]]) -> None:
        name = row["name"]
        if self._is_excluded(name, row):
            return
        self._registry.record_failure(name, reason)
        result = self._healer.heal_container(row, reason=reason)
        if result.get("ok"):
            actions.append(result)
            self._registry.record_heal(name, reason)

    def _run(self) -> None:
        if self._config.telegram_configured and self._config.telegram_enabled:
            self._telegram.alert(
                "Watchdog online",
                f"Auto-discover: {'ON' if self._config.auto_discover else 'OFF'}\n"
                f"Docker events: {'ON' if self._config.docker_events_enabled else 'OFF'}\n"
                f"Compose heal: {'ON' if self._config.compose_heal else 'OFF'}\n"
                f"Poll every {self._config.check_interval_sec:.0f}s",
                severity="info",
            )

        while not self._stop.is_set():
            try:
                self._scan()
            except Exception:
                log.exception("Watchdog scan failed")
            self._stop.wait(self._config.check_interval_sec)

    def _scan(self) -> None:
        now = time.time()
        if not self._docker.available:
            self._store.append_event({"type": "docker_unavailable"})
            if not self._docker_alerted:
                self._docker_alerted = True
                self._telegram.alert("Docker unreachable", "Watchdog cannot reach Docker socket.", severity="critical")
            return

        self._docker_alerted = False

        containers = self._docker.list_containers()
        discovery: dict[str, Any] = {}
        if self._config.auto_discover:
            discovery = self._registry.sync(containers)

        host = self._host_stats()
        actions: list[dict[str, Any]] = []

        # Re-create missing compose services learned from registry
        if self._config.compose_heal and discovery.get("missing_compose"):
            compose_actions = self._compose_healer.heal_missing(
                discovery["missing_compose"],
                reason="container missing from registry",
            )
            actions.extend(compose_actions)

        for row in containers:
            name = row["name"]
            status = row["status"]
            health = row.get("health")
            prev = self._last_status.get(name)

            if status in _TRANSIENT_STATUSES:
                pass
            elif status != "running" or health == "unhealthy":
                reason = "unhealthy" if health == "unhealthy" else f"status={status}"
                if row.get("oom_killed"):
                    reason = "OOM killed"
                with self._event_lock:
                    self._heal_row(row, reason=reason, actions=actions)
            elif status == "running":
                readiness = probe_for_container(name)
                if readiness is not None:
                    from readiness import optional_probe_names

                    probe_name = str(readiness.get("name") or "")
                    if probe_name in optional_probe_names():
                        self._readiness_failures[name] = 0
                    elif not probe_needs_heal(readiness):
                        self._readiness_failures[name] = 0
                    else:
                        streak = self._readiness_failures.get(name, 0) + 1
                        self._readiness_failures[name] = streak
                        detail = readiness.get("error") or f"probe failed ({readiness.get('latencyMs')}ms)"
                        self._store.append_event(
                            {
                                "type": "readiness_fail",
                                "container": name,
                                "streak": streak,
                                "probe": probe_name,
                                "detail": detail,
                            }
                        )
                        if streak >= self._config.readiness_fail_threshold:
                            reason = f"readiness death-loop ({streak}x): {detail}"
                            log.warning("%s — %s", name, reason)
                            self._telegram.alert(
                                f"Readiness fail: {name}",
                                f"{streak} consecutive probe failures.\n{detail}",
                                severity="critical",
                            )
                            with self._event_lock:
                                self._heal_row(row, reason=reason, actions=actions)
                                self._readiness_failures[name] = 0

            if status == "running" and prev and prev not in ("running",) and self._config.notify_on_recovery:
                detail = f"Container is running again (was {prev})."
                if health == "healthy":
                    detail += " Healthcheck passed."
                self._telegram.alert(
                    f"Recovered: {name}",
                    detail,
                    severity="ok",
                )

            self._last_status[name] = status

            mem_mb = row.get("memory_mb")
            self._memory.record(name, mem_mb, now=now)

            mem_pct = row.get("memory_pct")
            if mem_pct is not None and mem_pct >= self._config.memory_alert_pct:
                if not self._memory.already_alerted(f"{name}:high"):
                    self._memory.mark_alerted(f"{name}:high")
                    detail = f"{name} at {mem_pct}% of limit ({mem_mb} MB)"
                    self._store.append_event({"type": "memory_high", "container": name, "detail": detail})
                    self._telegram.alert("High container memory", detail, severity="warning")
                    if mem_pct >= self._config.memory_heal_pct and status == "running":
                        with self._event_lock:
                            self._heal_row(row, reason=f"memory critical {mem_pct}%", actions=actions)

            leak = None if name in self._config.memory_leak_exclude else self._memory.check_leak(name)
            if leak and not self._memory.already_alerted(f"{name}:leak"):
                self._memory.mark_alerted(f"{name}:leak")
                detail = (
                    f"{name}: {leak['first_mb']} MB → {leak['last_mb']} MB "
                    f"(+{leak['growth_pct']}% over {leak['samples']} samples)"
                )
                self._store.append_event({"type": "memory_leak", "container": name, "detail": detail, "leak": leak})
                self._telegram.alert("Possible memory leak", detail, severity="warning")
                if self._config.memory_leak_heal and status == "running":
                    with self._event_lock:
                        self._heal_row(row, reason=f"memory leak +{leak['growth_pct']}%", actions=actions)

            if leak is None:
                self._memory.clear_alert(f"{name}:leak")

        self._check_host(host)

        if os.environ.get("ROUTE_GUARD_ENABLED", "1").strip().lower() in ("1", "true", "yes"):
            route_action = route_guard_scan(fix=self._config.auto_heal)
            if route_action.get("issues") and not route_action.get("ok"):
                actions.append({"type": "route_guard", **route_action})
                if self._config.auto_heal and route_action.get("fixed") and route_action.get("recovered"):
                    self._telegram.alert(
                        "Route guard: cloud/dashboard recovered",
                        "Rebuilt hub-dashboard and repointed nginx away from Butler/mysteryproject.",
                        severity="heal",
                    )
                elif (
                    self._config.auto_heal
                    and route_action.get("alert")
                    and route_action.get("issues")
                    and os.environ.get("ROUTE_GUARD_TELEGRAM", "0").strip().lower() in {"1", "true", "yes", "on"}
                ):
                    # Debounced + explicit opt-in only (default off — Docker origin false alarms)
                    self._telegram.alert(
                        "Route guard: portal misrouted",
                        "\n".join(route_action.get("issues") or []),
                        severity="critical",
                    )

        readiness = run_readiness_checks(latency_threshold_ms=self._config.readiness_latency_ms_threshold)
        bare_actions = self._process_healer.scan_probes(readiness.get("probes") or [])
        actions.extend(bare_actions)

        gpu_action = self._gpu_healer.scan()
        if gpu_action:
            actions.append(gpu_action)

        state = {
            "ts": now,
            "containers": containers,
            "host": host,
            "memory_history": self._memory.snapshot(),
            "actions": actions,
            "readiness": readiness,
            "discovery": discovery,
            "docker_ok": True,
        }
        self._store.save_state(state)

    def _host_stats(self) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "memory_pct": round(vm.percent, 1),
            "memory_used_gb": round(vm.used / (1024**3), 2),
            "memory_total_gb": round(vm.total / (1024**3), 2),
            "disk_pct": round(disk.percent, 1),
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "cpu_pct": round(psutil.cpu_percent(interval=0.1), 1),
        }

    def _check_host(self, host: dict[str, Any]) -> None:
        mem_pct = host.get("memory_pct", 0)
        if mem_pct >= self._config.host_memory_alert_pct:
            if not self._host_alerted["memory"]:
                self._host_alerted["memory"] = True
                detail = f"Host memory at {mem_pct}% ({host.get('memory_used_gb')} / {host.get('memory_total_gb')} GB)"
                self._store.append_event({"type": "host_memory", "detail": detail})
                self._telegram.alert("Host memory critical", detail, severity="critical")
        else:
            self._host_alerted["memory"] = False

        disk_pct = host.get("disk_pct", 0)
        if disk_pct >= self._config.host_disk_alert_pct:
            if not self._host_alerted["disk"]:
                self._host_alerted["disk"] = True
                detail = f"Host disk at {disk_pct}% ({host.get('disk_free_gb')} GB free)"
                self._store.append_event({"type": "host_disk", "detail": detail})
                self._telegram.alert("Host disk critical", detail, severity="critical")
        else:
            self._host_alerted["disk"] = False
