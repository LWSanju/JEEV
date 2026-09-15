"""Configuration-driven JEEV personality layer."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


class PersonalityManager:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.path = self.base_dir / "personality" / "personality.json"
        self.config = self._load()

    def _load(self) -> dict[str, Any]:
        default = {
            "enabled": True,
            "style": "friendly",
            "warmth": 0.8,
            "humor": 0.5,
            "sarcasm": 0.25,
            "proactivity": 0.4,
            "verbosity": "concise",
            "use_contextual_humor": True,
            "use_tanglish_when_user_does": True,
            "traits": ["calm", "sharp", "playful", "observant"],
            "rules": [],
        }
        try:
            if not self.path.exists():
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(default, indent=2), encoding="utf-8")
                return default
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else default
        except Exception:
            return default

    def reload(self) -> None:
        self.config = self._load()

    def system_instruction(self) -> str:
        if not bool(self.config.get("enabled", True)):
            return "[PERSONALITY] Keep the existing neutral JEEV conversation style."

        traits = ", ".join(str(x) for x in self.config.get("traits", []))
        rules = "\n".join(f"- {x}" for x in self.config.get("rules", []))
        style = str(self.config.get("style", "friendly"))
        verbosity = str(self.config.get("verbosity", "concise"))
        humor = float(self.config.get("humor", 0.5) or 0.0)
        sarcasm = float(self.config.get("sarcasm", 0.25) or 0.0)
        proactivity = float(self.config.get("proactivity", 0.4) or 0.0)

        return (
            "\n[CONFIGURED JEEV PERSONALITY]\n"
            f"Style: {style}.\n"
            f"Traits: {traits or 'calm, intelligent, natural'}.\n"
            f"Verbosity: {verbosity}.\n"
            f"Humor level: {humor:.2f}.\n"
            f"Sarcasm level: {sarcasm:.2f}.\n"
            f"Proactivity level: {proactivity:.2f}.\n"
            "Use contextual humor only when the conversation supports it.\n"
            "Never force jokes into tool execution, errors, safety-sensitive requests, or serious situations.\n"
            "Never change tool parameters because of personality.\n"
            f"Rules:\n{rules}\n"
        )

    def startup_instruction(self) -> str:
        style = str(self.config.get("style", "friendly"))
        return (
            "[SYSTEM STARTUP EVENT] JEEV has just started. "
            f"Give a brief warm welcome in a {style} style. "
            "Sound confident and natural. Mention Tamil/Tanglish support. "
            "Do not ask a question and do not call tools."
        )

    def should_add_banter(self, user_text: str) -> bool:
        if not bool(self.config.get("enabled", True)):
            return False
        text = str(user_text or "").strip().lower()
        if not text:
            return False
        blocked = {"serious", "urgent", "emergency", "error", "failed", "shutdown"}
        if any(word in text for word in blocked):
            return False
        probability = max(0.0, min(1.0, float(self.config.get("humor", 0.5) or 0.0)))
        return random.random() < probability
