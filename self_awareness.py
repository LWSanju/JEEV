"""
JEEV lightweight self-awareness.

This module is intentionally deterministic and local. It does not call an
LLM, perform web requests, or store a second long-term memory database.

Its job is to give JEEV a grounded representation of:
- who JEEV is
- what JEEV is currently doing
- what JEEV recently did
- what JEEV recently said
- what the user most recently said

Gemini remains responsible for natural-language reasoning. This module supplies
the facts Gemini should use when the user refers to JEEV as "you", "your",
"your last answer", "what did you do", etc.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
import json
import threading
from typing import Any


class SelfAwareness:
    """Small, thread-safe, deterministic self-context for JEEV."""

    def __init__(
        self,
        name: str = "JEEV",
        role: str = "personal AI assistant",
        max_events: int = 18,
    ) -> None:
        self.name = str(name or "JEEV")
        self.role = str(role or "personal AI assistant")
        self.max_events = max(6, int(max_events))

        self._lock = threading.RLock()
        self._state = "initializing"

        self._events = deque(maxlen=self.max_events)

        self._last_user_text = ""
        self._last_response_text = ""
        self._last_action = None
        self._last_action_result = None
        self._last_action_ok = None
        self._turn_number = 0

    # ---------------------------------------------------------
    # STATE
    # ---------------------------------------------------------

    def set_state(self, state: str) -> None:
        with self._lock:
            self._state = str(state or "unknown").strip().lower()

    def get_state(self) -> str:
        with self._lock:
            return self._state

    # ---------------------------------------------------------
    # CONVERSATION
    # ---------------------------------------------------------

    def record_user_turn(
        self,
        user_text: str,
        response_text: str = "",
    ) -> None:
        user_text = self._clean(user_text)
        response_text = self._clean(response_text)

        if not user_text and not response_text:
            return

        with self._lock:
            self._turn_number += 1

            if user_text:
                self._last_user_text = user_text

            if response_text:
                self._last_response_text = response_text

            self._events.append(
                {
                    "type": "conversation",
                    "turn": self._turn_number,
                    "user": user_text,
                    "jeev": response_text,
                    "time": self._now(),
                }
            )

    # ---------------------------------------------------------
    # ACTIONS
    # ---------------------------------------------------------

    def record_action(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        result: Any,
    ) -> None:
        tool_name = self._clean(tool_name)
        arguments = dict(arguments or {})

        result_text = self._clean(
            result if isinstance(result, str) else json.dumps(
                result,
                ensure_ascii=False,
                default=str,
            )
        )

        ok = self._infer_success(result)

        with self._lock:
            self._last_action = {
                "tool": tool_name,
                "arguments": arguments,
                "time": self._now(),
            }
            self._last_action_result = result_text
            self._last_action_ok = ok

            self._events.append(
                {
                    "type": "action",
                    "tool": tool_name,
                    "arguments": self._compact_arguments(arguments),
                    "result": self._compact(result_text),
                    "success": ok,
                    "time": self._now(),
                }
            )

    # ---------------------------------------------------------
    # PROMPT CONTEXT
    # ---------------------------------------------------------

    def prompt_context(self) -> str:
        """
        Return a compact factual block for Gemini.

        This explicitly teaches self-reference resolution without asking
        Gemini to pretend it has human consciousness.
        """
        with self._lock:
            state = self._state
            last_user = self._last_user_text
            last_response = self._last_response_text
            last_action = dict(self._last_action or {})
            last_result = self._last_action_result or ""
            last_ok = self._last_action_ok
            events = list(self._events)[-8:]
            turn_number = self._turn_number

        lines = [
            "[JEEV SELF-AWARENESS — GROUNDED CONTEXT]",
            f"Identity: You are {self.name}, {self.role}.",
            "Self-reference rule: when the user says 'you', 'your', "
            "'yourself', 'what did you do', 'what did you say', or "
            "'you did X', resolve that reference to JEEV unless the "
            "sentence clearly refers to another person or thing.",
            "Do not treat JEEV as a third-party stranger in the conversation.",
            "Do not claim consciousness, feelings, memories, or actions that "
            "are not supported by this context.",
            "Use actual recorded actions and responses when answering questions "
            "about what JEEV did or said.",
            f"Current JEEV state: {state}.",
            f"Conversation turn: {turn_number}.",
        ]

        if last_action:
            lines.append(
                "Most recent JEEV action: "
                f"{last_action.get('tool', 'unknown')} "
                f"with {self._compact(json.dumps(last_action.get('arguments', {}), ensure_ascii=False, default=str), 260)}."
            )
            if last_ok is True:
                lines.append("Most recent JEEV action status: SUCCESS.")
            elif last_ok is False:
                lines.append("Most recent JEEV action status: FAILED.")
            else:
                lines.append("Most recent JEEV action status: UNKNOWN.")
            if last_result:
                lines.append(
                    "Most recent JEEV action result: "
                    f"{self._compact(last_result, 420)}"
                )

        if last_response:
            lines.append(
                "JEEV's most recent spoken/text response: "
                f"{self._compact(last_response, 500)}"
            )

        if last_user:
            lines.append(
                "User's most recent utterance: "
                f"{self._compact(last_user, 500)}"
            )

        if events:
            lines.append("Recent grounded JEEV events:")
            for event in events[-6:]:
                if event.get("type") == "action":
                    status = (
                        "success"
                        if event.get("success") is True
                        else "failed"
                        if event.get("success") is False
                        else "unknown"
                    )
                    lines.append(
                        f"- action: {event.get('tool', 'unknown')} "
                        f"({status}); result={event.get('result', '')}"
                    )
                elif event.get("type") == "conversation":
                    lines.append(
                        f"- conversation: user={self._compact(event.get('user', ''), 180)}; "
                        f"jeev={self._compact(event.get('jeev', ''), 220)}"
                    )

        lines.extend(
            [
                "Self-reference examples:",
                "- 'You opened the wrong app' means JEEV's most recent relevant action.",
                "- 'Your last answer was wrong' means JEEV's most recent response.",
                "- 'What did you just do?' means inspect the most recent recorded JEEV action.",
                "- 'Why did you do that?' means explain the recorded action/result; "
                "if no reason is recorded, say so instead of inventing one.",
                "- 'Are you listening?' means report JEEV's current state.",
                "- If the user corrects JEEV, acknowledge the correction and use the "
                "new information; do not become defensive.",
            ]
        )

        return "\n".join(lines)

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _compact(value: Any, limit: int = 300) -> str:
        text = str(value or "").replace("\n", " ").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)] + "..."

    @staticmethod
    def _compact_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
        compacted = {}
        for key, value in arguments.items():
            if isinstance(value, str):
                compacted[key] = SelfAwareness._compact(value, 220)
            else:
                compacted[key] = value
        return compacted

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%H:%M:%S")

    @staticmethod
    def _infer_success(result: Any) -> bool | None:
        if isinstance(result, dict):
            if "ok" in result:
                return bool(result["ok"])
            if "success" in result:
                return bool(result["success"])
            if result.get("blocked") is True:
                return False

        text = str(result or "").strip().lower()
        if not text:
            return None

        failure_markers = (
            " failed",
            "error:",
            "exception",
            "couldn't",
            "could not",
            "unable to",
            "not found",
            "blocked",
        )
        if text.startswith("failed") or any(marker in text for marker in failure_markers):
            return False

        success_markers = (
            "success",
            "completed",
            "done",
            "opened",
            "sent",
            "saved",
            "closed",
            "playing",
            "started",
        )
        if any(marker in text for marker in success_markers):
            return True

        return None
