"""
JEEV MARK I - Event Driven Proactive Engine

Additive layer. It does not replace existing tools or routing.

Supported triggers:
- startup
- idle_for_seconds
- app_started / app_stopped
- foreground_app
- file_changed
- user_said (text intent/keyword)
- interval

Actions:
- speak
- safe existing JEEV tool

All routines are configuration-driven. High-risk tools are never available to
this engine. Event payloads intentionally avoid storing clipboard contents or
full file contents.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SAFE_TOOLS = {
    "open_app",
    "web_search",
    "weather_report",
    "youtube_video",
    "media_control",
    "spotify_control",
    "flight_finder",
    "reminder",
    "save_memory",
}


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def _process_snapshot() -> set[str]:
    """Return lowercase process names without requiring psutil."""
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        names: set[str] = set()
        for line in (result.stdout or "").splitlines():
            if not line.strip():
                continue
            first = line.split('","', 1)[0].strip('" ')
            if first:
                names.add(first.lower())
        return names
    except Exception:
        return set()


def _foreground_process() -> str:
    """Best-effort Windows foreground process name."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid.value)
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return Path(buf.value).stem.lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""
    return ""


def _idle_seconds() -> float:
    if os.name != "nt":
        return 0.0
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            now = ctypes.windll.kernel32.GetTickCount()
            return max(0.0, (now - info.dwTime) / 1000.0)
    except Exception:
        pass
    return 0.0


class EventDrivenEngine:
    def __init__(
        self,
        base_dir: str | Path,
        tool_runner: Callable[[str, dict], Any] | None = None,
        notifier: Callable[[str], None] | None = None,
        logger: Callable[[str], None] | None = None,
    ):
        self.base_dir = Path(base_dir)
        self.config_path = self.base_dir / "automation" / "proactive.json"
        self.tool_runner = tool_runner
        self.notifier = notifier
        self.logger = logger or print
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False
        self._lock = threading.RLock()
        self._last_fired: dict[str, float] = {}
        self._processes: set[str] = set()
        self._foreground = ""
        self._files: dict[str, float] = {}
        self._last_activity = time.monotonic()
        self._startup_fired = False

    def _load(self) -> dict[str, Any]:
        default = {"enabled": True, "poll_seconds": 3, "routines": []}
        try:
            if not self.config_path.exists():
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                self.config_path.write_text(json.dumps(default, indent=2), encoding="utf-8")
                return default
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else default
        except Exception as exc:
            self.logger(f"[Proactive] Config load failed: {exc}")
            return default

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            cfg = self._load()
            if not bool(cfg.get("enabled", True)):
                self.logger("[Proactive] Engine disabled in proactive.json")
                return
            self._stop.clear()
            self._processes = _process_snapshot()
            self._foreground = _foreground_process()
            self._thread = threading.Thread(target=self._loop, name="JEEV-Proactive", daemon=True)
            self._started = True
            self._thread.start()
            self.logger("[Proactive] Event engine started.")

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            self._started = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        self.logger("[Proactive] Event engine stopped.")

    def on_user_text(self, text: str) -> int:
        """Evaluate user_said routines immediately, without waiting for polling."""
        if not text:
            return 0
        count = 0
        cfg = self._load()
        if not bool(cfg.get("enabled", True)):
            return 0
        for routine in cfg.get("routines", []):
            if not isinstance(routine, dict) or not routine.get("enabled", False):
                continue
            trigger = routine.get("trigger", {})
            if str(trigger.get("type", "")).lower() != "user_said":
                continue
            phrases = trigger.get("phrases", [])
            normalized = _norm(text)
            matched = any(_norm(p) in normalized for p in phrases if p)
            if matched and self._cooldown_ok(routine):
                if self._run(routine, {"type": "user_said", "text": text}):
                    count += 1
        return count

    def _loop(self) -> None:
        first = True
        while not self._stop.is_set():
            try:
                cfg = self._load()
                if bool(cfg.get("enabled", True)):
                    now = time.monotonic()
                    if first:
                        self._check_startup(cfg)
                        first = False
                    self._check_process_events(cfg)
                    self._check_foreground(cfg)
                    self._check_idle(cfg)
                    self._check_files(cfg)
                    self._check_intervals(cfg)
                poll = max(1, min(30, int(cfg.get("poll_seconds", 3) or 3)))
            except Exception as exc:
                self.logger(f"[Proactive] Loop error: {exc}")
                poll = 5
            self._stop.wait(poll)

    def _routines(self, cfg: dict, kind: str):
        for routine in cfg.get("routines", []):
            if not isinstance(routine, dict) or not routine.get("enabled", False):
                continue
            trigger = routine.get("trigger", {})
            if isinstance(trigger, dict) and str(trigger.get("type", "")).lower() == kind:
                yield routine, trigger

    def _check_startup(self, cfg: dict) -> None:
        if self._startup_fired:
            return
        self._startup_fired = True
        for routine, _ in self._routines(cfg, "startup"):
            if self._cooldown_ok(routine):
                self._run(routine, {"type": "startup"})

    def _check_process_events(self, cfg: dict) -> None:
        current = _process_snapshot()
        started, stopped = current - self._processes, self._processes - current
        self._processes = current
        for routine, trigger in self._routines(cfg, "app_started"):
            wanted = _norm(trigger.get("process", ""))
            if wanted and any(wanted == p or wanted in p for p in started):
                if self._cooldown_ok(routine):
                    self._run(routine, {"type": "app_started", "process": wanted})
        for routine, trigger in self._routines(cfg, "app_stopped"):
            wanted = _norm(trigger.get("process", ""))
            if wanted and any(wanted == p or wanted in p for p in stopped):
                if self._cooldown_ok(routine):
                    self._run(routine, {"type": "app_stopped", "process": wanted})

    def _check_foreground(self, cfg: dict) -> None:
        current = _foreground_process()
        if not current or current == self._foreground:
            return
        self._foreground = current
        for routine, trigger in self._routines(cfg, "foreground_app"):
            wanted = _norm(trigger.get("process", ""))
            if wanted and (wanted == current or wanted in current):
                if self._cooldown_ok(routine):
                    self._run(routine, {"type": "foreground_app", "process": current})

    def _check_idle(self, cfg: dict) -> None:
        idle = _idle_seconds()
        for routine, trigger in self._routines(cfg, "idle_for_seconds"):
            try:
                threshold = float(trigger.get("seconds", 0))
            except (TypeError, ValueError):
                continue
            if threshold > 0 and idle >= threshold and self._cooldown_ok(routine):
                self._run(routine, {"type": "idle_for_seconds", "seconds": idle})

    def _check_files(self, cfg: dict) -> None:
        for routine, trigger in self._routines(cfg, "file_changed"):
            path = Path(os.path.expandvars(str(trigger.get("path", ""))))
            pattern = str(trigger.get("pattern", "*"))
            if not path.exists() or not path.is_dir():
                continue
            try:
                current: dict[str, float] = {}
                for item in path.glob(pattern):
                    if item.is_file():
                        current[str(item.resolve())] = item.stat().st_mtime_ns
                previous = self._files
                changed = [p for p, stamp in current.items() if previous.get(p) not in (None, stamp)]
                created = [p for p in current if p not in previous]
                self._files = current
                if changed or (created and bool(trigger.get("include_created", True))):
                    if self._cooldown_ok(routine):
                        self._run(routine, {"type": "file_changed", "changed": changed[:5], "created": created[:5]})
            except Exception as exc:
                self.logger(f"[Proactive] File watcher error: {exc}")

    def _check_intervals(self, cfg: dict) -> None:
        now = time.monotonic()
        for routine, trigger in self._routines(cfg, "interval"):
            try:
                seconds = float(trigger.get("seconds", 0))
            except (TypeError, ValueError):
                continue
            if seconds > 0 and now - self._last_fired.get(self._key(routine), 0) >= seconds:
                self._run(routine, {"type": "interval", "seconds": seconds})

    def _key(self, routine: dict) -> str:
        return str(routine.get("id") or routine.get("name") or id(routine))

    def _cooldown_ok(self, routine: dict) -> bool:
        cooldown = float(routine.get("cooldown_seconds", 300) or 300)
        key = self._key(routine)
        now = time.monotonic()
        if now - self._last_fired.get(key, 0) < max(0, cooldown):
            return False
        return True

    def _run(self, routine: dict, event: dict) -> bool:
        name = str(routine.get("name") or routine.get("id") or "proactive routine")
        action = routine.get("action", {})
        if not isinstance(action, dict):
            return False
        action_type = str(action.get("type", "speak")).lower()
        try:
            if action_type == "speak":
                message = str(action.get("message", "")).strip()
                if not message:
                    return False
                if self.notifier:
                    self.notifier(message)
            elif action_type == "tool":
                tool = str(action.get("tool", "")).strip()
                if tool not in SAFE_TOOLS or not self.tool_runner:
                    self.logger(f"[Proactive] Blocked unsafe/unavailable tool: {tool}")
                    return False
                args = action.get("args", {})
                if not isinstance(args, dict):
                    args = {}
                result = self.tool_runner(tool, args)
                if bool(action.get("announce_result", False)) and self.notifier:
                    self.notifier(f"{name}: {result}")
            else:
                self.logger(f"[Proactive] Unknown action '{action_type}' in {name}")
                return False
            self._last_fired[self._key(routine)] = time.monotonic()
            self.logger(f"[Proactive] Fired: {name} ← {event.get('type')}")
            return True
        except Exception as exc:
            self.logger(f"[Proactive] {name} failed: {exc}")
            return False
