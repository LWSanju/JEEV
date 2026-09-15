# ============================================================
# JEEV — SMART SEND MESSAGE
# ============================================================
#
# Responsibilities:
#   1. Send exactly what the user dictates when a message is supplied.
#   2. Compose a message from the current/previous conversation when
#      the user asks JEEV to "tell/send/reply/explain" something.
#   3. Understand English + Tanglish naturally.
#   4. Reuse recent conversation context without inventing facts.
#   5. WhatsApp is delegated to whatsapp_control.py.
#   6. Telegram remains handled here.
#
# IMPORTANT:
#   This module does NOT decide what the user means from a vague tool call
#   alone. main.py / the model can pass compose_instruction or raw_command.
#   When composition is requested, the FREE-ONLY OpenRouter client is used.
# ============================================================

import json
import re
import urllib.parse
import webbrowser
from typing import Any


# ------------------------------------------------------------
# Context helpers
# ------------------------------------------------------------

def _stringify_context(value: Any, limit: int = 14000) -> str:
    """Turn common JEEV memory/history shapes into readable text."""
    if value is None:
        return ""

    try:
        if isinstance(value, str):
            text = value
        elif isinstance(value, (list, tuple)):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    role = item.get("role", item.get("speaker", ""))
                    content = item.get(
                        "content",
                        item.get("text", item.get("message", "")),
                    )
                    if content:
                        parts.append(
                            f"{role}: {content}" if role else str(content)
                        )
                else:
                    parts.append(str(item))
            text = "\n".join(parts)
        elif isinstance(value, dict):
            # Prefer conversation-like fields if present.
            for key in (
                "messages",
                "history",
                "conversation",
                "recent",
                "turns",
            ):
                if key in value:
                    text = _stringify_context(value[key], limit)
                    if text:
                        return text[-limit:]
            text = json.dumps(value, ensure_ascii=False, default=str)
        else:
            text = str(value)
    except Exception:
        text = str(value)

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[-limit:]


def _get_context(parameters: dict, session_memory=None) -> str:
    """Collect only conversation context useful for message composition."""
    candidates = [
        parameters.get("conversation_context"),
        parameters.get("recent_conversation"),
        parameters.get("history"),
        parameters.get("session_context"),
        session_memory,
    ]

    chunks = []
    for item in candidates:
        text = _stringify_context(item)
        if text and text not in chunks:
            chunks.append(text)

    return "\n\n--- RECENT CONTEXT ---\n".join(chunks)[-18000:]


# ------------------------------------------------------------
# Message mode detection
# ------------------------------------------------------------

_LITERAL_KEYS = (
    "message_text",
    "text",
    "message",
    "content",
)

_COMPOSE_KEYS = (
    "compose_instruction",
    "message_instruction",
    "intent",
    "what_to_say",
)


def _first_value(parameters: dict, keys) -> str:
    for key in keys:
        value = parameters.get(key)
        if value is not None:
            value = str(value).strip()
            if value:
                return value
    return ""


def _looks_like_compose_request(parameters: dict, instruction: str) -> bool:
    explicit = str(
        parameters.get("compose", parameters.get("use_context", ""))
    ).strip().lower()

    if explicit in {"true", "1", "yes", "compose", "smart", "context"}:
        return True

    if _first_value(parameters, _COMPOSE_KEYS):
        return True

    # These are instructions, not literal message text.
    lowered = instruction.lower().strip()
    compose_patterns = (
        "tell him",
        "tell her",
        "tell them",
        "send him",
        "send her",
        "send them",
        "reply to him",
        "reply to her",
        "reply to them",
        "explain to him",
        "explain to her",
        "explain to them",
        "message him",
        "message her",
        "message them",
        "say something about",
        "say about",
        "send a message about",
        "send a message regarding",
        "respond about",
        "reply about",
        "continue the conversation",
        "reply based on",
        "from our previous talk",
        "based on our previous talk",
        "based on previous conversation",
    )
    return any(p in lowered for p in compose_patterns)


def _clean_instruction(parameters: dict) -> str:
    return _first_value(parameters, _COMPOSE_KEYS)


# ------------------------------------------------------------
# FREE-ONLY contextual composition
# ------------------------------------------------------------

def _compose_message(
    instruction: str,
    context: str,
    requested_language: str = "",
) -> str:
    """
    Compose only when the caller asks for contextual composition.

    The installed or_client.py is responsible for enforcing the user's
    FREE-ONLY OpenRouter policy.
    """
    if not instruction:
        return ""

    try:
        from or_client import client
    except Exception as exc:
        print(f"[JEEV][SendMessage] OpenRouter unavailable for composition: {exc}")
        return ""

    language = requested_language.strip().lower()

    if language in {"tanglish", "tanglish tamil", "tamil english"}:
        language_rule = (
            "Write natural conversational Tanglish: Tamil meaning expressed "
            "mostly in Roman/English letters, mixed naturally with English. "
            "Do not use Tamil script unless the user explicitly asks for it."
        )
    elif language in {"tamil", "ta"}:
        language_rule = "Write natural Tamil in Tamil script."
    elif language in {"english", "en"}:
        language_rule = "Write natural conversational English."
    else:
        language_rule = (
            "Choose naturally between conversational English and Tanglish "
            "based on the user's instruction/context. If the surrounding "
            "conversation is Tanglish, Tanglish is preferred."
        )

    prompt = f"""
You are JEEV's message-writing component.

The user wants JEEV to send a message to another person.

INSTRUCTION:
{instruction}

RECENT CONVERSATION CONTEXT:
{context if context else "[No usable previous conversation was provided.]"}

RULES:
- Produce ONLY the message that should be sent. No quotes, labels, explanation,
  "here is the message", or commentary.
- Understand English, Tamil, and Tanglish instructions.
- Preserve the user's intended meaning, names, numbers, dates, plans, and tone.
- If the instruction says to continue/reply based on the previous conversation,
  use the relevant previous topic instead of making up a new topic.
- Do not invent facts, promises, events, feelings, or details that are absent
  from the instruction/context.
- If the user gives exact wording, preserve it rather than creatively rewriting it.
- If the user asks for a casual message, keep it natural and human.
- Do not make the message unnecessarily long.
- {language_rule}
"""

    try:
        result = client.chat(
            prompt,
            system=(
                "You compose outbound personal messages. "
                "Never add facts that are not supported by the instruction "
                "or supplied conversation context."
            ),
            max_tokens=900,
            temperature=0.35,
        )
        text = str(result or "").strip()

        # Remove accidental wrapper quotes only.
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
            text = text[1:-1].strip()

        # Guard against common assistant preambles.
        prefixes = (
            "here is the message:",
            "message:",
            "here's the message:",
            "sure, here is the message:",
        )
        low = text.lower()
        for prefix in prefixes:
            if low.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        return text
    except Exception as exc:
        print(f"[JEEV][SendMessage] Contextual composition failed: {exc}")
        return ""


def _resolve_message_text(
    parameters: dict,
    session_memory=None,
) -> tuple[str, str]:
    """
    Return (message_text, mode).

    Priority:
      1. Explicit message_text/text/content = literal.
      2. Explicit compose_instruction = smart composition.
      3. compose/use_context + instruction = smart composition.
      4. raw_command/command/user_text can be used for smart composition
         only when the caller explicitly asks for compose/context.
    """
    literal = _first_value(parameters, _LITERAL_KEYS)
    if literal:
        return literal, "literal"

    instruction = _clean_instruction(parameters)

    compose_requested = _looks_like_compose_request(parameters, instruction)

    if not instruction and compose_requested:
        instruction = _first_value(
            parameters,
            ("raw_command", "command", "user_text", "transcript"),
        )

    if compose_requested and instruction:
        context = _get_context(parameters, session_memory)
        language = str(
            parameters.get("language", parameters.get("message_language", ""))
        ).strip()

        composed = _compose_message(
            instruction=instruction,
            context=context,
            requested_language=language,
        )
        if composed:
            return composed, "contextual"

    # If no literal message and no explicit composition request, do not guess.
    return "", "missing"


# ------------------------------------------------------------
# Main dispatcher
# ------------------------------------------------------------

def send_message(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
):
    """
    Generic messaging dispatcher.

    Literal example:
      {
        "receiver": "Arun",
        "message_text": "I'll call you at 6.",
        "platform": "whatsapp"
      }

    Smart/context example:
      {
        "receiver": "Arun",
        "compose_instruction":
            "Tell him about what we were discussing earlier and keep it casual",
        "platform": "whatsapp"
      }

    The first sends exactly the supplied text.
    The second composes a message from the recent conversation context.
    """

    parameters = dict(parameters or {})

    receiver = str(parameters.get("receiver", "")).strip()
    platform = str(parameters.get("platform", "")).strip().lower()

    if not receiver:
        return "No recipient was provided."

    message_text, mode = _resolve_message_text(
        parameters,
        session_memory=session_memory,
    )

    if not message_text:
        return (
            "No message text was provided. "
            "Tell me what to send, or ask me to compose it from our previous conversation."
        )

    print(
        "[JEEV][SendMessage] "
        f"Message mode={mode}; receiver={receiver}; platform={platform or 'unspecified'}"
    )
    print(f"[JEEV][SendMessage] Prepared message: {message_text}")

    # ========================================================
    # WHATSAPP
    # ========================================================

    if platform in (
        "whatsapp",
        "whatsapp desktop",
        "whatsapp web",
    ):
        print(
            "[JEEV][SendMessage] "
            "Delegating WhatsApp to whatsapp_control."
        )

        try:
            from actions.whatsapp_control import whatsapp_control

            return whatsapp_control(
                parameters={
                    "action": "send_message",
                    "receiver": receiver,
                    "message_text": message_text,
                },
                response=response,
                player=player,
            )

        except Exception as e:
            print(
                "[JEEV][SendMessage] "
                f"WhatsApp controller error: {e}"
            )
            return f"WhatsApp control failed: {e}"

    # ========================================================
    # TELEGRAM
    # ========================================================

    if platform == "telegram":
        try:
            encoded_message = urllib.parse.quote(message_text)
            url = (
                "https://t.me/share/url"
                f"?text={encoded_message}"
            )

            print(
                "[JEEV][SendMessage] "
                "Opening Telegram sharing..."
            )
            webbrowser.open(url)

            return (
                f"Telegram sharing opened for "
                f"{receiver}."
            )

        except Exception as e:
            print(
                "[JEEV][SendMessage] "
                f"Telegram error: {e}"
            )
            return (
                "Could not prepare the Telegram "
                f"message: {e}"
            )

    # ========================================================
    # PLATFORM NOT SPECIFIED
    # ========================================================

    if not platform:
        return (
            "No messaging platform was specified. "
            "For WhatsApp, use WhatsApp Desktop."
        )

    return f"Platform '{platform}' is not supported yet."


# ============================================================
# COMPATIBILITY ALIAS
# ============================================================

def sendMessage(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
):
    return send_message(
        parameters=parameters,
        response=response,
        player=player,
        session_memory=session_memory,
    )
