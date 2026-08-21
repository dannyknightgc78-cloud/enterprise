"""Guard cloud/dashboard routes. Public HTTPS is authoritative.

Inside Docker, origin probes to 127.0.0.1 always fail — that must NEVER page Telegram.
Set ROUTE_GUARD_TELEGRAM=1 only if you want critical pages after debounce.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
import urllib.request
from typing import Any

log = logging.getLogger("watchdog.route_guard")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_BAD = ("mysteryproject", "butler // neural relay", "cloud me ")
_CLOUD_GOOD = ("cloudit", "sovereign command")
_DASH_GOOD = ("dannygc hub", "hub-dashboard", "photobooth")
_HOST_EXPECT = {
    "cloud.dannygc.cloud": _CLOUD_GOOD,
    "dashboard.dannygc.cloud": _DASH_GOOD,
}
_HOSTS = tuple(_HOST_EXPECT.keys())
_COOLDOWN_UNTIL = 0.0
_FAIL_STREAK = 0
_LAST_ALERT_TS = 0.0


def _origin_base() -> str:
    return os.environ.get("ROUTE_GUARD_ORIGIN", "http://195.133.93.104").rstrip("/")


def _telegram_pages_enabled() -> bool:
    return os.environ.get("ROUTE_GUARD_TELEGRAM", "0").strip().lower() in {"1", "true", "yes", "on"}


def _fetch_public(host: str) -> str:
    req = urllib.request.Request(
        f"https://{host}/",
        headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        return res.read(2500).decode("utf-8", errors="replace").lower()


def _fetch_origin(host: str) -> str:
    base = _origin_base()
    req = urllib.request.Request(
        f"{base}/",
        headers={"Host": host, "User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
    )
    with urllib.request.urlopen(req, timeout=8) as res:
        return res.read(2500).decode("utf-8", errors="replace").lower()


def _host_ok(host: str) -> tuple[bool, str]:
    # Public first — if public is correct, we are OK regardless of Docker origin.
    pub_err = None
    try:
        body = _fetch_public(host)
        if any(b in body for b in _BAD):
            return False, f"{host}: public wrong app"
        expect = _HOST_EXPECT.get(host, _DASH_GOOD)
        if any(g in body for g in expect):
            if host == "cloud.dannygc.cloud" and "dannygc hub" in body and "cloudit" not in body:
                return False, f"{host}: public still Hub"
            return True, f"{host}: public ok"
        return False, f"{host}: public markers missing"
    except Exception as exc:  # noqa: BLE001
        pub_err = exc

    # Fallback origin (Hostman nginx) — never treat connection-refused-only as page-worthy alone
    try:
        body = _fetch_origin(host)
        expect = _HOST_EXPECT.get(host, _DASH_GOOD)
        if any(b in body for b in _BAD):
            return False, f"{host}: origin wrong app (public={pub_err})"
        if any(g in body for g in expect):
            return True, f"{host}: origin ok (public={pub_err})"
        return False, f"{host}: origin markers missing (public={pub_err})"
    except Exception as loc_exc:  # noqa: BLE001
        return False, f"{host}: probe failed (public={pub_err}; origin={loc_exc})"


def scan(*, fix: bool = True) -> dict[str, Any]:
    global _COOLDOWN_UNTIL, _FAIL_STREAK, _LAST_ALERT_TS  # noqa: PLW0603
    now = time.time()
    debounce = int(os.environ.get("ROUTE_GUARD_FAIL_DEBOUNCE", "4"))
    alert_cd = float(os.environ.get("ROUTE_GUARD_ALERT_COOLDOWN_SEC", "3600"))

    issues: list[str] = []
    for host in _HOSTS:
        ok, detail = _host_ok(host)
        if not ok:
            issues.append(detail)

    if not issues:
        _FAIL_STREAK = 0
        return {"ok": True, "hosts": list(_HOSTS), "alert": False}

    _FAIL_STREAK += 1
    action: dict[str, Any] = {
        "ok": False,
        "issues": issues,
        "fixed": False,
        "fail_streak": _FAIL_STREAK,
        "alert": False,
    }

    # Auto-fix on origin only after debounce; never page Telegram by default
    script = os.environ.get(
        "ROUTE_GUARD_SCRIPT",
        os.path.join(os.environ.get("LAB_ROOT", "/root/lab-dannygc"), "scripts/guard-hostman-routing.sh"),
    )
    on_origin = _origin_base() in (
        "http://127.0.0.1",
        "http://localhost",
        "http://host.docker.internal",
        "http://195.133.93.104",
    )
    if fix and on_origin and os.path.isfile(script) and _FAIL_STREAK >= debounce and now >= _COOLDOWN_UNTIL:
        try:
            subprocess.run(["bash", script, "--fix"], check=False, timeout=300)
            action["fixed"] = True
            _COOLDOWN_UNTIL = now + float(os.environ.get("ROUTE_GUARD_COOLDOWN_SEC", "600"))
            issues2 = []
            for host in _HOSTS:
                ok, detail = _host_ok(host)
                if not ok:
                    issues2.append(detail)
            if not issues2:
                _FAIL_STREAK = 0
                return {"ok": True, "recovered": True, "fixed": True, "alert": False, "issues": []}
            action["issues"] = issues2
        except Exception as exc:  # noqa: BLE001
            action["error"] = str(exc)

    # Soft until debounce; Telegram only if explicitly enabled
    if _FAIL_STREAK < debounce:
        action["ok"] = True
        action["soft"] = True
        log.info("route soft fail %s/%s: %s", _FAIL_STREAK, debounce, "; ".join(issues))
        return action

    if _telegram_pages_enabled() and (now - _LAST_ALERT_TS) >= alert_cd:
        action["alert"] = True
        _LAST_ALERT_TS = now
        log.warning("route guard alert: %s", "; ".join(action.get("issues") or issues))
    else:
        action["ok"] = True  # do not trip monitor critical path
        action["alert"] = False
        log.warning("route guard degraded (telegram suppressed): %s", "; ".join(action.get("issues") or issues))
    return action
