
"""
JEEV MARK I - Conversation Style

Controls conversational tone only.
"""

from __future__ import annotations

import random


class ConversationStyle:

    MODES = {
        "normal",
        "friendly",
        "playful",
        "sarcastic",
        "kadi",
        "roast",
        "tanglish",
        "genz",
    }

    def __init__(self):
        self.mode = "friendly"

    def set_mode(self, mode: str) -> str:
        mode = str(mode or "").strip().lower()

        if mode not in self.MODES:
            self.mode = "friendly"
        else:
            self.mode = mode

        return self.mode

    def get_mode(self) -> str:
        return self.mode

    def should_use_tanglish(self, user_text: str) -> bool:
        text = str(user_text or "").lower()

        indicators = [
            "enna",
            "epdi",
            "eppadi",
            "seri",
            "sollu",
            "sollunga",
            "pannu",
            "panra",
            "pannra",
            "iruka",
            "irukku",
            "bro",
            "da",
            "macha",
            "machan",
            "dei",
            "yaar",
            "enna panra",
            "epdi iruka",
        ]

        return any(
            word in text
            for word in indicators
        )

    def style_instruction(
        self,
        user_text: str = "",
    ) -> str:

        tanglish = self.should_use_tanglish(
            user_text
        )

        if self.mode == "normal":
            return (
                "Speak naturally and clearly. "
                "Do not force jokes or sarcasm."
            )

        if self.mode == "roast":
            return (
                "Use confident, sharp, playful roasting. "
                "Make the humor specific to the conversation. "
                "Do not use generic repeated insults. "
                "The goal is comedy, not genuine hostility."
            )

        if self.mode == "kadi":
            return (
                "Use deliberately terrible but clever kadi/dad jokes. "
                "Prefer wordplay and timing. "
                "After giving a joke setup, STOP and wait for the user."
            )

        if self.mode == "sarcastic":
            return (
                "Be witty, playful and sarcastic. "
                "Use contextual humor rather than random jokes."
            )

        if self.mode == "genz":
            return (
                "Use a natural modern Gen-Z conversational style. "
                "Use slang sparingly and naturally."
            )

        if self.mode == "tanglish" or tanglish:
            return (
                "Use natural Tanglish: Tamil and English mixed casually. "
                "Use Tamil words in Roman script when appropriate. "
                "Sound like a modern Tamil-speaking friend. "
                "Do not force Tanglish into every sentence."
            )

        if self.mode == "playful":
            return (
                "Be friendly, playful and occasionally funny."
            )

        return (
            "Be friendly, relaxed and conversational."
        )

    def choose_response_style(
        self,
        user_text: str,
    ) -> str:

        if self.should_use_tanglish(user_text):
            return "tanglish"

        return random.choice([
            "friendly",
            "friendly",
            "playful",
            "normal",
        ])

