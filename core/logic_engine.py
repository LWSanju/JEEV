"""
JEEV MARK I - LOGIC ENGINE

Drop-in replacement for core/logic_engine.py.

Goals:
- Opening/closing normal applications is NOT dangerous.
- WhatsApp sending/replying remains high-risk and requires one confirmation.
- WhatsApp recipient/message validation is explicit.
- WhatsApp Web is never allowed.
- Shutdown protection applies to JEEV itself.
- Tool/task state is thread-safe.
"""
from __future__ import annotations

import re
import time
import uuid
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List


TOOL_POLICIES: Dict[str, Dict[str, Any]] = {
    "open_app": {"risk": "low", "requires_confirmation": False},
    "web_search": {"risk": "low", "requires_confirmation": False},
    "weather_report": {"risk": "low", "requires_confirmation": False},
    "youtube_video": {"risk": "low", "requires_confirmation": False},
    "screen_process": {"risk": "medium", "requires_confirmation": False},
    "file_processor": {"risk": "medium", "requires_confirmation": False},
    "file_controller": {"risk": "medium", "requires_confirmation": False},
    "desktop_control": {"risk": "medium", "requires_confirmation": False},
    "browser_control": {"risk": "medium", "requires_confirmation": False},
    "computer_control": {"risk": "medium", "requires_confirmation": False},
    # Normal application navigation is intentionally NOT dangerous.
    "computer_settings": {"risk": "medium", "requires_confirmation": False},
    "media_control": {"risk": "low", "requires_confirmation": False},
    "spotify_control": {"risk": "low", "requires_confirmation": False},
    "flight_finder": {"risk": "low", "requires_confirmation": False},
    "reminder": {"risk": "low", "requires_confirmation": False},
    "code_helper": {"risk": "medium", "requires_confirmation": False},
    "dev_agent": {"risk": "medium", "requires_confirmation": False},
    "agent_task": {"risk": "medium", "requires_confirmation": False},
    "game_updater": {"risk": "medium", "requires_confirmation": False},
    "save_memory": {"risk": "low", "requires_confirmation": False},

    # External side effect: sending a WhatsApp message.
    "send_message": {
        "risk": "high",
        "requires_confirmation": True,
        "requires_validation": True,
    },
    "whatsapp_control": {
        "risk": "high",
        "requires_confirmation": False,  # only send/reply becomes true
        "requires_validation": True,
    },

    "shutdown_jarvis": {
        "risk": "critical",
        "requires_confirmation": True,
        "requires_validation": True,
    },
}


# Actions that are genuinely destructive.  open_app/close_app are absent.
DANGEROUS_ACTIONS = {
    "shutdown",
    "shutdown_pc",
    "poweroff",
    "power_off",
    "reboot",
    "restart_system",
    "format",
    "delete",
    "remove",
    "uninstall",
    "kill_process",
    "terminate_process",
    "wipe",
}


@dataclass
class LogicDecision:
    allowed: bool = True
    tool_name: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    risk: str = "low"
    requires_confirmation: bool = False
    requires_verification: bool = False
    task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskState:
    task_id: str
    user_request: str
    tool_name: str
    status: str = "created"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: Any = None
    error: Optional[str] = None


class LogicEngine:
    def __init__(self, memory=None, logger=None):
        self.memory = memory
        self.logger = logger
        self._tasks: Dict[str, TaskState] = {}
        self._lock = threading.RLock()
        self._last_request = ""
        self._last_tool = ""
        self._last_args: Dict[str, Any] = {}

    def _log(self, message: str):
        try:
            if self.logger:
                self.logger(message)
                return
        except Exception:
            pass
        print(f"[LOGIC] {message}")

    @staticmethod
    def normalize_text(text: Any) -> str:
        if text is None:
            return ""
        return re.sub(r"\s+", " ", str(text).strip().lower())

    def get_policy(self, tool_name: str) -> Dict[str, Any]:
        return TOOL_POLICIES.get(
            tool_name,
            {"risk": "medium", "requires_confirmation": False, "requires_validation": False},
        )

    def create_task(self, user_request: str, tool_name: str) -> str:
        task_id = "JEEV-" + uuid.uuid4().hex[:8].upper()
        with self._lock:
            self._tasks[task_id] = TaskState(
                task_id=task_id,
                user_request=user_request or "",
                tool_name=tool_name or "",
            )
        return task_id

    def update_task(self, task_id: str, status: str, result=None, error=None):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = status
            task.updated_at = time.time()
            task.result = result
            task.error = error

    def get_task(self, task_id: str) -> Optional[TaskState]:
        with self._lock:
            return self._tasks.get(task_id)

    @staticmethod
    def _contains_whatsapp_web(args: Dict[str, Any]) -> bool:
        combined = " ".join(
            str(v) for v in args.values() if v is not None
        ).lower()
        return "web.whatsapp" in combined or "whatsapp web" in combined

    def validate_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        user_request: str = "",
    ) -> LogicDecision:
        args = dict(args or {})
        tool_name = str(tool_name or "").strip()
        policy = self.get_policy(tool_name)
        risk = str(policy.get("risk", "medium"))

        decision = LogicDecision(
            allowed=bool(tool_name),
            tool_name=tool_name,
            args=args,
            risk=risk,
            requires_confirmation=bool(policy.get("requires_confirmation", False)),
            requires_verification=risk in {"high", "critical"},
        )

        if not tool_name:
            decision.reason = "No tool name was provided."
            return decision

        # ----------------------------------------------------
        # NORMAL APP CONTROL
        # ----------------------------------------------------
        # open_app and computer_settings/close_app are allowed.
        # A normal app close is not treated as a destructive system action.
        if tool_name in {"open_app", "computer_settings"}:
            action = self.normalize_text(args.get("action", ""))
            if action in {"close_app", "open_app", "launch_app", "focus_app", "close", "open"}:
                decision.requires_confirmation = False
                decision.requires_verification = False

        # ----------------------------------------------------
        # WHATSAPP
        # ----------------------------------------------------
        if tool_name == "whatsapp_control":
            if self._contains_whatsapp_web(args):
                decision.allowed = False
                decision.reason = "WhatsApp Web is prohibited. Use WhatsApp Desktop."
                return decision

            action = self.normalize_text(args.get("action", ""))
            receiver = str(
                args.get("receiver", args.get("contact", "")) or ""
            ).strip()
            message = str(
                args.get("message_text", args.get("message", "")) or ""
            ).strip()

            # Sending/replying is the only WhatsApp operation requiring confirmation.
            sending = action in {"send", "send_message", "reply", "send_reply"}
            decision.requires_confirmation = sending
            decision.requires_verification = sending

            # Navigation can be executed without confirmation.
            if action in {"open", "open_app", "focus", "status"}:
                decision.requires_confirmation = False
                decision.requires_verification = False

            # A contact can be selected by number after JEEV has displayed
            # several matching candidates (e.g. receiver="2").
            if action in {"open_chat", "chat", "send_message", "send"}:
                # For a new message, the actual controller will resolve an
                # ambiguous receiver.  Do not silently choose the first match.
                if not receiver:
                    decision.allowed = False
                    decision.reason = "WhatsApp recipient is missing. Ask the user who to send it to."
                    return decision

            if sending and not message:
                decision.allowed = False
                decision.reason = "WhatsApp message text is missing. Ask the user what message to send."
                return decision

        # ----------------------------------------------------
        # GENERIC SEND MESSAGE
        # ----------------------------------------------------
        if tool_name == "send_message":
            receiver = str(args.get("receiver", "") or "").strip()
            message = str(args.get("message_text", "") or "").strip()
            platform = str(args.get("platform", "") or "").strip()
            if not receiver:
                decision.allowed = False
                decision.reason = "Message recipient is missing."
                return decision
            if not message:
                decision.allowed = False
                decision.reason = "Message text is missing."
                return decision
            if not platform:
                decision.allowed = False
                decision.reason = "Messaging platform is missing."
                return decision
            decision.requires_confirmation = True
            decision.requires_verification = True

        # ----------------------------------------------------
        # GENERIC DESTRUCTIVE ACTIONS
        # ----------------------------------------------------
        action = self.normalize_text(args.get("action", ""))
        if action in DANGEROUS_ACTIONS:
            decision.requires_confirmation = True
            decision.requires_verification = True
            if tool_name in {"computer_settings", "computer_control"}:
                decision.risk = "critical" if action in {"shutdown", "shutdown_pc", "poweroff", "power_off", "reboot"} else "high"

        # ----------------------------------------------------
        # JEEV SHUTDOWN
        # ----------------------------------------------------
        if tool_name == "shutdown_jarvis":
            normalized = self.normalize_text(user_request)
            explicit_phrases = (
                "shut down jeev", "shutdown jeev", "turn off jeev",
                "turn jeev off", "exit jeev", "quit jeev", "close jeev",
                "stop jeev", "terminate jeev", "end jeev",
            )
            if not any(p in normalized for p in explicit_phrases):
                decision.allowed = False
                decision.reason = "JEEV shutdown requires an explicit request to shut down JEEV itself."
                return decision

        # ----------------------------------------------------
        # WHATSAPP/BROWSER SEPARATION
        # ----------------------------------------------------
        if tool_name == "browser_control":
            combined = " ".join(str(v) for v in args.values() if v is not None).lower()
            if "whatsapp" in combined or "web.whatsapp" in combined:
                decision.allowed = False
                decision.reason = "WhatsApp actions must use whatsapp_control."
                return decision

        decision.reason = "Tool request passed logic validation."
        return decision

    def decide(self, tool_name: str, args: Dict[str, Any], user_request: str = "") -> LogicDecision:
        self._last_request = user_request or ""
        self._last_tool = tool_name or ""
        self._last_args = dict(args or {})
        decision = self.validate_tool(tool_name, args, user_request)
        if decision.allowed:
            decision.task_id = self.create_task(user_request or "", tool_name)
            self.update_task(decision.task_id, "validated")
        self._log(
            f"{tool_name} -> {'ALLOW' if decision.allowed else 'BLOCK'} "
            f"({decision.reason})"
        )
        return decision

    def before_execution(self, decision: LogicDecision) -> bool:
        if not decision.allowed:
            return False
        if decision.task_id:
            self.update_task(decision.task_id, "executing")
        return True

    def after_execution(self, decision: LogicDecision, result: Any):
        if decision.task_id:
            self.update_task(decision.task_id, "completed", result=result)
        self._log(f"{decision.tool_name} completed.")

    def execution_failed(self, decision: LogicDecision, error: Exception):
        if decision.task_id:
            self.update_task(decision.task_id, "failed", error=str(error))
        self._log(f"{decision.tool_name} failed: {error}")

    def analyze_request(self, user_request: str) -> Dict[str, Any]:
        text = self.normalize_text(user_request)
        action_words = {
            "open", "launch", "start", "send", "message", "play", "pause",
            "stop", "search", "find", "download", "delete", "remove", "close",
            "shutdown", "restart", "create", "write", "read", "move", "copy", "rename",
        }
        high_risk_words = {"send", "delete", "shutdown", "restart", "remove", "message"}
        words = set(text.split())
        return {
            "text": text,
            "is_empty": not bool(text),
            "is_question": text.endswith("?"),
            "is_action": bool(words.intersection(action_words)),
            "is_high_risk": bool(words.intersection(high_risk_words)),
        }

    def create_plan(self, user_request: str, tool_name: str, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        decision = self.decide(tool_name, args, user_request)
        if not decision.allowed:
            return [{"step": 1, "action": "blocked", "reason": decision.reason}]

        plan = [{"step": 1, "action": "validate", "tool": tool_name}]
        if decision.requires_confirmation:
            plan.append({"step": len(plan) + 1, "action": "confirmation", "tool": tool_name})
        plan.append({"step": len(plan) + 1, "action": "execute", "tool": tool_name})
        if decision.requires_verification:
            plan.append({"step": len(plan) + 1, "action": "verify", "tool": tool_name})
        return plan

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            active = sum(
                1 for t in self._tasks.values()
                if t.status not in {"completed", "failed"}
            )
            return {
                "active_tasks": active,
                "total_tasks": len(self._tasks),
                "last_request": self._last_request,
                "last_tool": self._last_tool,
            }


_logic_engine = None
_logic_engine_lock = threading.Lock()


def get_logic_engine(memory=None, logger=None) -> LogicEngine:
    global _logic_engine
    with _logic_engine_lock:
        if _logic_engine is None:
            _logic_engine = LogicEngine(memory=memory, logger=logger)
    return _logic_engine