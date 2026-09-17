from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from typing import Callable

from app.config import settings

logger = logging.getLogger(__name__)

_deadline = time.monotonic() + 30.0
_lock = threading.Lock()
_watcher_started = False
_shutdown_requested = False


def touch_heartbeat() -> None:
    """Browser is alive — postpone auto-shutdown."""
    global _deadline
    with _lock:
        _deadline = time.monotonic() + settings.heartbeat_timeout_sec


def mark_leaving() -> None:
    """Tab is closing/refreshing — shut down soon unless heartbeat resumes."""
    global _deadline
    with _lock:
        _deadline = time.monotonic() + settings.leave_grace_sec


def seconds_until_deadline() -> float:
    with _lock:
        return _deadline - time.monotonic()


def _pids_on_port(port: int) -> list[int]:
    pids: set[int] = set()
    try:
        if sys.platform == "win32":
            out = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            needle = f":{port} "
            for line in out.splitlines():
                if needle not in line or "LISTENING" not in line.upper():
                    continue
                parts = line.split()
                if not parts:
                    continue
                try:
                    pids.add(int(parts[-1]))
                except ValueError:
                    continue
        else:
            out = subprocess.check_output(
                ["lsof", "-ti", f"tcp:{port}"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            for part in out.split():
                try:
                    pids.add(int(part))
                except ValueError:
                    continue
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        logger.warning("Could not inspect port %s: %s", port, exc)
    return sorted(pid for pid in pids if pid > 0)


def _kill_pid(pid: int) -> None:
    if pid == os.getpid():
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        logger.warning("Failed to stop pid %s: %s", pid, exc)


def stop_frontend() -> None:
    for pid in _pids_on_port(settings.web_port):
        logger.info("Stopping frontend pid %s on port %s", pid, settings.web_port)
        _kill_pid(pid)


def shutdown_all(reason: str = "client gone") -> None:
    global _shutdown_requested
    with _lock:
        if _shutdown_requested:
            return
        _shutdown_requested = True
    logger.info("Shutting down services (%s)", reason)
    stop_frontend()

    def _exit() -> None:
        time.sleep(0.35)
        os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()


def start_heartbeat_watcher(
    *,
    enabled: bool,
    on_timeout: Callable[[str], None] | None = None,
) -> None:
    """Stop API + frontend when browser heartbeats stop."""
    global _watcher_started
    if not enabled or _watcher_started:
        return
    _watcher_started = True
    touch_heartbeat()

    def _loop() -> None:
        # Allow initial page load before arming.
        time.sleep(6.0)
        touch_heartbeat()
        while True:
            remaining = seconds_until_deadline()
            if remaining <= 0:
                (on_timeout or shutdown_all)("browser closed or idle")
                return
            time.sleep(0.5)

    threading.Thread(target=_loop, name="heartbeat-watcher", daemon=True).start()
    logger.info(
        "Auto-shutdown armed (heartbeat=%ss, leave_grace=%ss, web_port=%s)",
        settings.heartbeat_timeout_sec,
        settings.leave_grace_sec,
        settings.web_port,
    )
