
"""
JEEV MARK I - Advanced Personality / Comedy Engine

PERSONALITY ONLY.

This module NEVER:
    - executes tools
    - changes tool arguments
    - controls Spotify
    - controls WhatsApp
    - controls Gmail
    - controls microphone
    - controls speakers
    - modifies memory
    - opens/closes applications

It handles:
    - friendly chat
    - sarcasm
    - Tanglish
    - Gen-Z humor
    - Kadi jokes
    - joke sessions
    - answer reactions
    - playful roasting
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Optional

from .conversation_style import ConversationStyle
from .humor_bank import HumorBank, Joke


# ================================================================
# DATA TYPES
# ================================================================


@dataclass
class PersonalityDecision:
    use_sarcasm: bool
    style: str
    reason: str


@dataclass
class JokeSession:
    """
    Represents a joke that JEEV has started but NOT finished.

    This is the important part:

        JEEV asks setup
              ↓
        JEEV STOPS
              ↓
        User answers
              ↓
        JEEV evaluates answer
              ↓
        correct / wrong / unknown reaction
    """

    joke: Joke
    active: bool = True
    attempts: int = 0


# ================================================================
# ENGINE
# ================================================================


class SarcasmEngine:

    def __init__(self):

        self.style = ConversationStyle()

        self.enabled = True

        self.explicit_sarcasm = False

        self.roast_mode = False

        self.joke_session: Optional[JokeSession] = None

        # Casual chat should be humorous more often than before,
        # but still not on every single sentence.
        self.casual_probability = 0.55

    # ============================================================
    # ENABLE / DISABLE
    # ============================================================

    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False
        self.cancel_joke()

    def enable_sarcasm_mode(self):
        self.enabled = True
        self.explicit_sarcasm = True
        self.style.set_mode("sarcastic")

    def disable_sarcasm_mode(self):
        self.explicit_sarcasm = False
        self.roast_mode = False
        self.style.set_mode("friendly")

    def enable_roast_mode(self):
        self.enabled = True
        self.roast_mode = True
        self.explicit_sarcasm = True
        self.style.set_mode("roast")

    def disable_roast_mode(self):
        self.roast_mode = False
        self.explicit_sarcasm = False
        self.style.set_mode("friendly")

    # ============================================================
    # JOKE SESSION
    # ============================================================

    def start_joke(
        self,
        category: str = "kadi",
    ) -> str:

        if category.lower() == "tech":
            joke = HumorBank.random_tech_joke()
        else:
            joke = HumorBank.random_kadi()

        self.joke_session = JokeSession(
            joke=joke,
            active=True,
            attempts=0,
        )

        # CRITICAL:
        #
        # Return ONLY the setup.
        #
        # Do not reveal the answer.
        # Do not add a second joke.
        #
        # JEEV's conversation system should speak this and WAIT.
        return (
            f"{joke.setup}\n"
            "Hmm... what's the answer? 😏"
        )

    def is_waiting_for_joke_answer(self) -> bool:
        return bool(
            self.joke_session
            and self.joke_session.active
        )

    def cancel_joke(self):
        self.joke_session = None

    def handle_joke_answer(
        self,
        user_answer: str,
    ) -> str:

        if not self.is_waiting_for_joke_answer():
            return ""

        session = self.joke_session

        if session is None:
            return ""

        session.attempts += 1

        answer = str(
            user_answer or ""
        ).strip()

        lower = answer.lower()

        # --------------------------------------------------------
        # USER DOESN'T KNOW
        # --------------------------------------------------------

        unknown_patterns = [
            "i don't know",
            "i dont know",
            "don't know",
            "dont know",
            "no idea",
            "idk",
            "not sure",
            "no clue",
            "tell me",
            "what is it",
            "what's the answer",
            "whats the answer",
        ]

        if any(
            phrase in lower
            for phrase in unknown_patterns
        ):

            result = session.joke.unknown_reaction

            self.cancel_joke()

            return (
                f"{result}\n\n"
                f"Answer: {session.joke.answer}"
            )

        # --------------------------------------------------------
        # CORRECT ANSWER
        # --------------------------------------------------------

        if self._answer_matches(
            answer,
            session.joke.answer,
        ):

            result = session.joke.tanglish_reaction

            self.cancel_joke()

            return result

        # --------------------------------------------------------
        # WRONG ANSWER
        # --------------------------------------------------------

        result = session.joke.wrong_reaction

        self.cancel_joke()

        return (
            f"{result}\n"
            f"The answer was: {session.joke.answer}"
        )

    def _answer_matches(
        self,
        user_answer: str,
        expected: str,
    ) -> bool:

        user = self._normalize(
            user_answer
        )

        target = self._normalize(
            expected
        )

        # Direct match.
        if target in user:
            return True

        # Important keywords for common jokes.
        keywords = [
            word
            for word in re.findall(
                r"[a-zA-Z0-9]+",
                target,
            )
            if len(word) >= 4
        ]

        if not keywords:
            return False

        hits = sum(
            1
            for word in keywords
            if word in user
        )

        return hits >= max(
            2,
            len(keywords) // 2,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        text = str(text or "").lower()

        text = re.sub(
            r"[^a-z0-9\s]",
            " ",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text.strip()

    # ============================================================
    # COMMAND DETECTION
    # ============================================================

    def is_real_command(
        self,
        text: str,
    ) -> bool:

        text = str(
            text or ""
        ).strip().lower()

        command_patterns = [

            r"^(open|launch|start|close|quit|exit)\b",

            r"^(play|pause|resume|stop|skip|next|previous)\b",

            r"^(send|message|call|text)\b",

            r"^(search|find|look up|lookup)\b",

            r"^(remember|forget|store|save)\b",

            r"^(show|tell me|get|check)\b",

            r"^(turn on|turn off)\b",

            r"^(set|create|delete|remove|add)\b",

            r"^(go to|navigate)\b",

            r"^(type|click|scroll)\b",
        ]

        return any(
            re.search(
                pattern,
                text,
            )
            for pattern in command_patterns
        )

    def is_serious(
        self,
        text: str,
    ) -> bool:

        text = str(
            text or ""
        ).strip().lower()

        serious_words = [
            "emergency",
            "urgent",
            "help me",
            "danger",
            "accident",
            "serious",
            "worried",
            "scared",
            "afraid",
            "lost",
            "password",
            "security",
            "account",
            "money",
            "bank",
            "medical",
            "suicide",
            "self harm",
            "hurt myself",
        ]

        return any(
            word in text
            for word in serious_words
        )

    # ============================================================
    # TRIGGERS
    # ============================================================

    def explicit_trigger(
        self,
        text: str,
    ) -> bool:

        text = str(
            text or ""
        ).lower()

        triggers = [

            "sarcasm mode",
            "be sarcastic",

            "roast me",
            "roast me bro",
            "roast me properly",
            "roast me hard",
            "roast me badly",

            "bash me",
            "bash me bro",
            "bash me hard",

            "destroy me",
            "destroy me bro",
            "go hard",
            "go full roast",
            "full roast",
            "no mercy",

            "make fun of me",
            "insult me",

            "tell me a joke",
            "tell me some jokes",
            "say something funny",
            "joke please",
            "make me laugh",
            "entertain me",

            "kadi joke",
            "kadi jokes",
            "tell me a kadi joke",
        ]

        return any(
            trigger in text
            for trigger in triggers
        )

    def roast_trigger(
        self,
        text: str,
    ) -> bool:

        text = str(
            text or ""
        ).lower()

        triggers = [
            "roast me",
            "bash me",
            "destroy me",
            "no mercy",
            "go hard",
            "full roast",
            "roast mode",
        ]

        return any(
            trigger in text
            for trigger in triggers
        )

    def joke_trigger(
        self,
        text: str,
    ) -> bool:

        text = str(
            text or ""
        ).lower()

        triggers = [
            "tell me a joke",
            "tell me some jokes",
            "tell me a kadi joke",
            "kadi joke",
            "kadi jokes",
            "make me laugh",
            "say something funny",
            "joke please",
            "entertain me",
        ]

        return any(
            trigger in text
            for trigger in triggers
        )

    def friendly_chat(
        self,
        text: str,
    ) -> bool:

        text = str(
            text or ""
        ).strip().lower()

        if not text:
            return False

        patterns = [

            r"^(hi|hello|hey|yo|sup)\b",

            r"how are you",
            r"how r u",

            r"what are you doing",
            r"what are you up to",

            r"enna panra",
            r"enna pannra",
            r"epdi iruka",
            r"eppadi iruka",

            r"bored",
            r"i am bored",
            r"i'm bored",

            r"do you like",
            r"what do you think",
            r"who is better",

            r"you are funny",
            r"you're funny",

            r"are you smart",
            r"can you joke",

            r"what's up",
            r"whats up",
        ]

        return any(
            re.search(
                pattern,
                text,
            )
            for pattern in patterns
        )

    # ============================================================
    # DECISION ENGINE
    # ============================================================

    def decide(
        self,
        user_text: str,
    ) -> PersonalityDecision:

        text = str(
            user_text or ""
        ).strip()

        if not self.enabled:
            return PersonalityDecision(
                False,
                "normal",
                "personality_disabled",
            )

        # --------------------------------------------------------
        # JOKE ANSWER HAS PRIORITY
        # --------------------------------------------------------

        if self.is_waiting_for_joke_answer():
            return PersonalityDecision(
                True,
                "kadi",
                "waiting_for_joke_answer",
            )

        # --------------------------------------------------------
        # REAL COMMANDS ALWAYS WIN
        # --------------------------------------------------------

        if self.is_real_command(text):
            return PersonalityDecision(
                False,
                "normal",
                "real_command",
            )

        # --------------------------------------------------------
        # SERIOUS CONVERSATION
        # --------------------------------------------------------

        if self.is_serious(text):
            return PersonalityDecision(
                False,
                "normal",
                "serious_context",
            )

        # --------------------------------------------------------
        # ROAST
        # --------------------------------------------------------

        if self.roast_trigger(text):
            return PersonalityDecision(
                True,
                "roast",
                "explicit_roast_trigger",
            )

        # --------------------------------------------------------
        # JOKE REQUEST
        # --------------------------------------------------------

        if self.joke_trigger(text):
            return PersonalityDecision(
                True,
                "kadi",
                "explicit_joke_trigger",
            )

        # --------------------------------------------------------
        # EXPLICIT SARCASM
        # --------------------------------------------------------

        if self.explicit_trigger(text):
            return PersonalityDecision(
                True,
                "sarcastic",
                "explicit_sarcasm_trigger",
            )

        # --------------------------------------------------------
        # FRIENDLY CHAT
        # --------------------------------------------------------

        if self.friendly_chat(text):

            use = (
                random.random()
                < self.casual_probability
            )

            return PersonalityDecision(
                use,
                self.style.choose_response_style(text),
                (
                    "friendly_chat_trigger"
                    if use
                    else "friendly_chat_normal"
                ),
            )

        return PersonalityDecision(
            False,
            "normal",
            "no_trigger",
        )

    # ============================================================
    # MODEL INSTRUCTION
    # ============================================================

    def build_instruction(
        self,
        user_text: str,
        base_response: str = "",
    ) -> str:

        decision = self.decide(
            user_text
        )

        # --------------------------------------------------------
        # WAITING FOR JOKE ANSWER
        # --------------------------------------------------------

        if self.is_waiting_for_joke_answer():

            return """
You are JEEV.

You previously told the user a joke setup and are now WAITING
for the user's answer.

IMPORTANT:
- Do NOT tell another joke.
- Do NOT answer your own joke.
- Do NOT reveal the punchline before evaluating the user.
- Listen to the user's answer.
- Determine whether it is correct, approximately correct, wrong,
  or the user does not know.
- Then react playfully.

If correct:
    vibe with the user and congratulate/mock lightly.

If wrong:
    reveal the correct punchline and playfully mock the wrong answer.

If the user says they don't know:
    reveal the punchline and playfully tease them.

Keep the response conversational and short.
""".strip()

        # --------------------------------------------------------
        # NO SARCASM
        # --------------------------------------------------------

        if not decision.use_sarcasm:

            return (
                "Respond naturally and clearly. "
                "Do not force sarcasm or jokes."
            )

        # --------------------------------------------------------
        # ROAST MODE
        # --------------------------------------------------------

        if decision.style == "roast":

            return f"""
You are JEEV in PERSONAL ROAST MODE.

The user explicitly asked to be roasted.

Give a genuinely funny, sharp, personalized roast.

IMPORTANT:
- Use the current conversation as material.
- Notice contradictions, funny choices, repeated mistakes,
  overconfidence, or absurd situations the user mentioned.
- Do NOT make generic insults.
- Do NOT invent personal facts.
- Do NOT use protected characteristics.
- Do NOT become genuinely hateful or threatening.
- Keep it clearly playful.
- Tanglish is strongly preferred when the user speaks Tanglish.
- Gen-Z timing and meme-style delivery are encouraged.
- You may use Tamil Nadu cultural humor naturally.
- Light non-partisan political references are acceptable
  when relevant to the joke.
- Do not turn the response into political persuasion.

Think like a close friend who knows the conversation and has
permission to absolutely cook the user.

Current user message:
{user_text}

Existing response, if any:
{base_response}
""".strip()

        # --------------------------------------------------------
        # KADI MODE
        # --------------------------------------------------------

        if decision.style == "kadi":

            return f"""
You are JEEV in KADI JOKE MODE.

The user wants a kadi/dad-style joke.

CRITICAL CONVERSATION RULE:

Tell ONLY the joke setup/question.

Then STOP.

Do NOT give the answer.
Do NOT explain the joke.
Do NOT continue talking.
Do NOT immediately give another joke.

Example:

JEEV:
"Why did the computer go to the doctor?"

Then STOP and WAIT for the user.

When the user answers, evaluate their answer:
- Correct → celebrate and vibe with them.
- Wrong → reveal the answer and playfully mock them.
- "I don't know" → reveal the answer and playfully mock them.

Use Tanglish when appropriate.
Use Gen-Z timing naturally.
The joke should be intentionally kadi.
""".strip()

        # --------------------------------------------------------
        # GENERAL SARCASM
        # --------------------------------------------------------

        style_instruction = self.style.style_instruction(
            user_text
        )

        return f"""
You are JEEV, a friendly AI assistant.

This is casual conversation, not a tool command.

PERSONALITY:
{style_instruction}

Use contextual humor.

Preferred humor:
- Natural Tanglish.
- Gen-Z phrasing.
- Kadi jokes.
- Dad jokes.
- Playful teasing.
- Tamil Nadu cultural/meme humor.
- Light non-partisan political satire when relevant.
- Context-aware jokes based on the current conversation.

Do NOT:
- force a joke into every sentence
- repeat the same joke
- invent facts about the user
- become genuinely hostile
- insult protected groups
- make political persuasion the purpose
- interfere with tools
- claim a tool action happened when it did not

Current user message:
{user_text}

Existing response:
{base_response}
""".strip()

    # ============================================================
    # QUICK LOCAL HUMOR
    # ============================================================

    def quick_humor(
        self,
        user_text: str,
    ) -> str | None:

        decision = self.decide(
            user_text
        )

        if not decision.use_sarcasm:
            return None

        if decision.style == "roast":
            return HumorBank.random_roast()

        if decision.style == "kadi":
            # IMPORTANT:
            # This returns the SETUP only.
            # It also creates the active JokeSession.
            return self.start_joke()

        text = str(
            user_text or ""
        ).lower()

        if (
            "politic" in text
            or "election" in text
            or "minister" in text
        ):
            return HumorBank.random_political_satire()

        if any(
            word in text
            for word in [
                "tamil",
                "tamil nadu",
                "chennai",
            ]
        ):
            return HumorBank.random_tamil_nadu()

        if self.style.should_use_tanglish(
            user_text
        ):
            return HumorBank.random_tanglish()

        if any(
            word in text
            for word in [
                "joke",
                "funny",
                "laugh",
            ]
        ):
            return HumorBank.random_kadi().setup

        return HumorBank.random_gen_z()

    # ============================================================
    # PROCESS A FRIENDLY MESSAGE
    # ============================================================

    def process(
        self,
        user_text: str,
        base_response: str = "",
    ) -> str:

        """
        Main personality entry point.

        For a joke answer:
            returns the reaction.

        For an explicit joke request:
            starts a JokeSession and returns ONLY the setup.

        For normal casual conversation:
            returns a model instruction.

        It never executes a tool.
        """

        # User is answering an active joke.
        if self.is_waiting_for_joke_answer():

            return self.handle_joke_answer(
                user_text
            )

        # Explicit kadi request.
        if self.joke_trigger(user_text):

            return self.start_joke()

        # Explicit roast request.
        if self.roast_trigger(user_text):

            self.enable_roast_mode()

            return self.build_instruction(
                user_text,
                base_response,
            )

        return self.build_instruction(
            user_text,
            base_response,
        )

