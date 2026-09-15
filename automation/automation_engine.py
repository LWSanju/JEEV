"""
JEEV MARK I - Proactive Automation Engine

Additive module. It does not replace or modify any existing JEEV tool.
All automation is configuration-driven through automation/automations.json.

Safety design:
- Disabled by default until the user enables individual routines.
- No credentials, device indexes, usernames, paths, or API keys are hardcoded.
- High-risk tools (messaging, shutdown, destructive actions, coding agents,
  arbitrary desktop/browser control) are never executable from this scheduler.
- Tool arguments come only from the external JSON configuration.
- Every execution is logged.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


SAFE_AUTOMATION_TOOLS = {
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

BLOCKED_AUTOMATION_TOOLS = {
    "send_message",
    "whatsapp_control",
    "gmail_control",
    "shutdown_jarvis",
    "computer_control",
    "computer_settings",
    "desktop_control",
    "browser_control",
    "file_controller",
    "file_processor",
    "screen_process",
    "dev_agent",
    "code_helper",
    "agent_task",
    "game_updater",
}


class AutomationEngine:
    def __init__(
        self,
        base_dir: str | Path,
        tool_runner: Callable[[str, dict], Any] | None = None,
        notifier: Callable[[str], None] | None = None,
        logger: Callable[[str], None] | None = None,
    ):
        self.base_dir = Path(base_dir)
        self.config_path = self.base_dir / "automation" / "automations.json"
        self.tool_runner = tool_runner
        self.notifier = notifier
        self.logger = logger or (lambda message: print(message))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False
        self._last_run: dict[str, str] = {}
        self._lock = threading.RLock()

    # ---------------------------------------------------------
    # CONFIG
    # ---------------------------------------------------------
    def load(self) -> dict:
        default = {"enabled": False, "timezone": "local", "routines": []}
        try:
            if not self.config_path.exists():
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                self.config_path.write_text(
                    json.dumps(default, indent=2), encoding="utf-8"
                )
                return default
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else default
        except Exception as exc:
            self.logger(f"[Automation] ⚠️ Config load failed: {exc}")
            return default

    # ---------------------------------------------------------
    # LIFECYCLE
    # ---------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            config = self.load()
            if not bool(config.get("enabled", False)):
                self.logger("[Automation] ℹ️ Engine loaded; scheduler disabled in config.")
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="JEEV-Automation",
                daemon=True,
            )
            self._started = True
            self._thread.start()
            self.logger("[Automation] ✅ Scheduler started.")

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._started = False
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None
        self.logger("[Automation] 🔴 Scheduler stopped.")

    # ---------------------------------------------------------
    # SCHEDULER
    # ---------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop_event.wait(15.0):
            try:
                self.run_due()
            except Exception as exc:
                self.logger(f"[Automation] ⚠️ Scheduler error: {exc}")
                traceback.print_exc()

    def run_due(self, now: datetime | None = None) -> int:
        config = self.load()
        if not bool(config.get("enabled", False)):
            return 0

        now = now or datetime.now()
        count = 0
        for routine in config.get("routines", []):
            if not isinstance(routine, dict):
                continue
            if not bool(routine.get("enabled", False)):
                continue
            if self._is_due(routine, now):
                if self._run_routine(routine, now):
                    count += 1
        return count

    def _is_due(self, routine: dict, now: datetime) -> bool:
        schedule = routine.get("schedule", {})
        if not isinstance(schedule, dict):
            return False

        kind = str(schedule.get("type", "daily")).lower()
        target_time = str(schedule.get("time", "")).strip()
        if not target_time:
            return False

        try:
            hour, minute = [int(x) for x in target_time.split(":", 1)]
            if now.hour != hour or now.minute != minute:
                return False
        except (TypeError, ValueError):
            return False

        if kind == "daily":
            pass
        elif kind == "weekdays":
            if now.weekday() >= 5:
                return False
        elif kind == "weekly":
            wanted = schedule.get("weekday", now.weekday())
            try:
                if now.weekday() != int(wanted):
                    return False
            except (TypeError, ValueError):
                return False
        else:
            return False

        key = str(routine.get("id") or routine.get("name") or target_time)
        stamp = now.strftime("%Y-%m-%d %H:%M")
        with self._lock:
            if self._last_run.get(key) == stamp:
                return False
        return True

    def _run_routine(self, routine: dict, now: datetime) -> bool:
        name = str(routine.get("name") or routine.get("id") or "unnamed")
        key = str(routine.get("id") or name)
        action = routine.get("action", {})
        if not isinstance(action, dict):
            return False

        action_type = str(action.get("type", "speak")).lower()
        success = False
        result: Any = None

        try:
            if action_type == "speak":
                message = str(action.get("message", "")).strip()
                if not message:
                    return False
                if self.notifier:
                    self.notifier(message)
                result = message
                success = True

            elif action_type == "tool":
                tool_name = str(action.get("tool", "")).strip()
                if tool_name not in SAFE_AUTOMATION_TOOLS:
                    self.logger(
                        f"[Automation] 🚫 Blocked routine '{name}': tool '{tool_name}' is not scheduler-safe."
                    )
                    return False
                if tool_name in BLOCKED_AUTOMATION_TOOLS:
                    return False
                if not self.tool_runner:
                    return False
                args = action.get("args", {})
                if not isinstance(args, dict):
                    args = {}
                result = self.tool_runner(tool_name, args)
                success = True
                if self.notifier and bool(action.get("announce_result", True)):
                    self.notifier(self._format_result(name, result))

            else:
                self.logger(f"[Automation] ⚠️ Unknown action type '{action_type}' in '{name}'.")
                return False

            with self._lock:
                self._last_run[key] = now.strftime("%Y-%m-%d %H:%M")
            self.logger(f"[Automation] ▶ {name} → {str(result)[:180]}")
            return success
        except Exception as exc:
            self.logger(f"[Automation] ❌ {name} failed: {exc}")
            traceback.print_exc()
            return False

    @staticmethod
    def _format_result(name: str, result: Any) -> str:
        if isinstance(result, dict):
            if "message" in result:
                return f"{name}: {result['message']}"
            if "result" in result:
                return f"{name}: {result['result']}"
        text = str(result or "completed").strip()
        return f"{name}: {text}"
