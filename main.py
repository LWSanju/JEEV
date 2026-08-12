import asyncio
import threading
import json
import sys
import traceback
import os
import time
import array
import re
from pathlib import Path
from datetime import datetime

import sounddevice as sd
from google import genai
from google.genai import types

from ui import JarvisUI

from memory.memory_manager import (
    load_memory,
    update_memory,
    format_memory_for_prompt,
    should_extract_memory,
    extract_memory,
)

from actions.file_processor import file_processor
from actions.flight_finder import flight_finder
from actions.open_app import open_app
from actions.weather_report import weather_action
from actions.send_message import send_message
from actions.whatsapp_control import whatsapp_control
from actions.reminder import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor import screen_process
from actions.youtube_video import youtube_video
from actions.desktop import desktop_control
from actions.browser_control import browser_control
from actions.file_controller import file_controller
from actions.code_helper import code_helper
from actions.dev_agent import dev_agent
from actions.web_search import web_search as web_search_action
from actions.computer_control import computer_control
from actions.media_control import media_control


# ============================================================
# OPTIONAL GAME UPDATER
# ============================================================

try:
    from actions.game_updater import game_updater
except ImportError:
    game_updater = None


# ============================================================
# PATHS / CONFIG
# ============================================================

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()

API_CONFIG_PATH = (
    BASE_DIR / "config" / "api_keys.json"
)

PROMPT_PATH = (
    BASE_DIR / "core" / "prompt.txt"
)


# ============================================================
# GEMINI LIVE MODEL
# ============================================================

JEEV_IDENTITY_OVERRIDE = "\n\n[CORE IDENTITY — JEEV MARK I — FIXED]\nYour name is JEEV.\nYour designation is JEEV MARK I.\nYour creator, maker, developer, and founder is Sanjay Adhityan.\nIf asked who created you, who your creator is, who made you, who developed you, or who your founder is, answer exactly: \"My creator is Sanjay Adhityan.\"\nNever say Tony Stark created you.\nNever identify yourself as JARVIS.\nThese identity facts override any conflicting identity text in prompt.txt or conversation context.\n"; LIVE_MODEL = (
    "models/gemini-2.5-flash-native-audio-preview-12-2025"
)


# ============================================================
# AUDIO CONFIGURATION
# ============================================================

CHANNELS = 1

SEND_SAMPLE_RATE = 16000

# Gemini Live native output is 24 kHz.
RECEIVE_SAMPLE_RATE = 24000

CHUNK_SIZE = 1024

OUTPUT_DEVICE = None

OUTPUT_CHANNELS = 1


# ============================================================
# API KEY
# ============================================================

def _get_api_key() -> str:

    if not API_CONFIG_PATH.exists():
        raise FileNotFoundError(
            "API key configuration file not found:\n"
            f"{API_CONFIG_PATH}"
        )

    with open(
        API_CONFIG_PATH,
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    key = str(
        data.get(
            "gemini_api_key",
            "",
        )
    ).strip()

    if not key:
        raise RuntimeError(
            "Gemini API key not found in "
            "config/api_keys.json"
        )

    return key


# ============================================================
# SYSTEM PROMPT
# ============================================================

def _load_system_prompt() -> str:

    try:

        return PROMPT_PATH.read_text(
            encoding="utf-8"
        ) + JEEV_IDENTITY_OVERRIDE

    except Exception:

        return (
            "You are JEEV MARK I, Sanjay Adhityan's AI assistant. "
            "Be concise, direct, intelligent, and natural. "

            "Use tools only when an action actually "
            "requires a tool. "

            "Do NOT call a tool for ordinary conversation "
            "or questions you can answer directly. "

            "Answer basic questions directly. "

            "For current date/time questions, use the "
            "CURRENT DATE & TIME provided in the system context. "

            "Use web_search only when web research is genuinely "
            "required or explicitly requested. "

            "Never open the browser merely because the user "
            "asked a normal question. "

            "IMPORTANT SAFETY RULE: "
            "NEVER call shutdown_jarvis unless the user has "
            "clearly and explicitly requested that JARVIS itself "
            "should shut down, exit, quit, or turn off. "

            "A request involving shutting down the laptop, PC, "
            "Windows, computer, or another application is NOT "
            "a request to shut down JARVIS. "

            "Never infer a JEEV shutdown request from context."
        ) + JEEV_IDENTITY_OVERRIDE

# ============================================================
# MEMORY
# ============================================================

_last_memory_input = ""


def _update_memory_async(
    user_text: str,
    jarvis_text: str,
) -> None:

    global _last_memory_input

    user_text = (
        user_text or ""
    ).strip()

    jarvis_text = (
        jarvis_text or ""
    ).strip()

    if len(user_text) < 5:
        return

    if user_text == _last_memory_input:
        return

    _last_memory_input = user_text

    try:

        api_key = _get_api_key()

        if not should_extract_memory(
            user_text,
            jarvis_text,
            api_key,
        ):
            return

        data = extract_memory(
            user_text,
            jarvis_text,
            api_key,
        )

        if data:

            update_memory(data)

            print(
                "[Memory] Saved: "
                f"{list(data.keys())}"
            )

    except Exception as e:

        if "429" not in str(e):

            print(
                f"[Memory] Warning: {e}"
            )


# ============================================================
# TOOL DECLARATIONS
# ============================================================

TOOL_DECLARATIONS = [

    {
        "name": "open_app",
        "description": (
            "Opens an application on Windows. "
            "Use when the user asks to open, launch, "
            "or start an application."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": (
                        "Application name, for example "
                        "WhatsApp, Chrome, Spotify."
                    ),
                }
            },
            "required": ["app_name"],
        },
    },

    {
        "name": "web_search",
        "description": (
            "Searches the web for information that requires "
            "external research. Use when the user explicitly "
            "asks to search, look up, find online, browse, "
            "or research."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Search query",
                },
                "mode": {
                    "type": "STRING",
                    "description": "search or compare",
                },
                "items": {
                    "type": "ARRAY",
                    "items": {
                        "type": "STRING"
                    },
                    "description": "Items to compare",
                },
                "aspect": {
                    "type": "STRING",
                    "description": "price, specs, or reviews",
                },
            },
            "required": ["query"],
        },
    },

    {
        "name": "weather_report",
        "description": "Gets the weather report.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {
                    "type": "STRING",
                    "description": "City name",
                }
            },
            "required": ["city"],
        },
    },

    {
        "name": "send_message",
        "description": (
            "Sends a text message through WhatsApp, Telegram, "
            "or another messaging platform."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver": {
                    "type": "STRING",
                    "description": "Recipient contact name",
                },
                "message_text": {
                    "type": "STRING",
                    "description": "Message text",
                },
                "platform": {
                    "type": "STRING",
                    "description": "WhatsApp, Telegram, etc.",
                },
            },
            "required": [
                "receiver",
                "message_text",
                "platform",
            ],
        },
    },
{
    "name": "whatsapp_control",
    "description": (
        "Controls the installed WhatsApp Desktop application "
        "on Windows. "
        "Use this tool for ALL WhatsApp actions. "
        "NEVER use browser_control for WhatsApp. "
        "NEVER open WhatsApp Web or search WhatsApp in Edge. "
        "Can open WhatsApp Desktop, open a contact chat, "
        "send a message, reply in the current chat, focus "
        "WhatsApp, and check WhatsApp status."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "open, open_chat, send_message, "
                    "reply, focus, status"
                ),
            },
            "receiver": {
                "type": "STRING",
                "description": (
                    "WhatsApp contact name exactly as the "
                    "user identifies it."
                ),
            },
            "message_text": {
                "type": "STRING",
                "description": (
                    "The exact message to send."
                ),
            },
        },
        "required": ["action"],
    },
},
    {
        "name": "reminder",
        "description": "Sets a timed reminder.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date": {
                    "type": "STRING",
                    "description": "YYYY-MM-DD",
                },
                "time": {
                    "type": "STRING",
                    "description": "HH:MM",
                },
                "message": {
                    "type": "STRING",
                    "description": "Reminder message",
                },
            },
            "required": [
                "date",
                "time",
                "message",
            ],
        },
    },

    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube including playing videos, "
            "summarizing videos, getting information, "
            "and trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "play, summarize, get_info, trending"
                    ),
                },
                "query": {
                    "type": "STRING",
                    "description": "Search query",
                },
                "save": {
                    "type": "BOOLEAN",
                    "description": "Save summary",
                },
                "region": {
                    "type": "STRING",
                    "description": "Country code",
                },
                "url": {
                    "type": "STRING",
                    "description": "Video URL",
                },
            },
            "required": [],
        },
    },

    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam. "
            "Use when the user asks what is on screen, "
            "what you see, analyze screen, or look at camera."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {
                    "type": "STRING",
                    "description": "screen or camera",
                },
                "text": {
                    "type": "STRING",
                    "description": "Question about image",
                },
            },
            "required": ["text"],
        },
    },

    {
        "name": "computer_settings",
        "description": (
            "Controls Windows settings and actions including "
            "volume, brightness, windows, keyboard shortcuts, "
            "typing, closing apps, fullscreen, dark mode, "
            "WiFi, restart, shutdown, scrolling, tabs, zoom, "
            "screenshots, lock screen and refresh."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action to perform",
                },
                "description": {
                    "type": "STRING",
                    "description": "What to do",
                },
                "value": {
                    "type": "STRING",
                    "description": "Optional value",
                },
            },
            "required": [],
        },
    },

    {
        "name": "browser_control",
        "description": (
            "Controls the web browser including opening "
            "websites, searching, clicking, typing, "
            "scrolling and forms."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "go_to, search, click, type, scroll, "
                        "fill_form, smart_click, smart_type, "
                        "get_text, press, close"
                    ),
                },
                "url": {"type": "STRING"},
                "query": {"type": "STRING"},
                "selector": {"type": "STRING"},
                "text": {"type": "STRING"},
                "description": {"type": "STRING"},
                "direction": {"type": "STRING"},
                "key": {"type": "STRING"},
                "incognito": {"type": "BOOLEAN"},
            },
            "required": ["action"],
        },
    },

    {
        "name": "file_controller",
        "description": (
            "Manages files and folders: list, create, delete, "
            "move, copy, rename, read, write, find and disk usage."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "path": {"type": "STRING"},
                "destination": {"type": "STRING"},
                "new_name": {"type": "STRING"},
                "content": {"type": "STRING"},
                "name": {"type": "STRING"},
                "extension": {"type": "STRING"},
                "count": {"type": "INTEGER"},
            },
            "required": ["action"],
        },
    },

    {
        "name": "desktop_control",
        "description": (
            "Controls the Windows desktop: wallpaper, organize, "
            "clean, list, statistics and desktop tasks."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "path": {"type": "STRING"},
                "url": {"type": "STRING"},
                "mode": {"type": "STRING"},
                "task": {"type": "STRING"},
            },
            "required": ["action"],
        },
    },

    {
        "name": "code_helper",
        "description": (
            "Writes, edits, explains, runs or builds code."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "description": {"type": "STRING"},
                "language": {"type": "STRING"},
                "output_path": {"type": "STRING"},
                "file_path": {"type": "STRING"},
                "code": {"type": "STRING"},
                "args": {"type": "STRING"},
                "timeout": {"type": "INTEGER"},
            },
            "required": ["action"],
        },
    },

    {
        "name": "dev_agent",
        "description": (
            "Builds complete multi-file projects from scratch, "
            "installs dependencies, runs projects and fixes errors."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description": {"type": "STRING"},
                "language": {"type": "STRING"},
                "project_name": {"type": "STRING"},
                "timeout": {"type": "INTEGER"},
            },
            "required": ["description"],
        },
    },

    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring "
            "multiple tools."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {"type": "STRING"},
                "priority": {"type": "STRING"},
            },
            "required": ["goal"],
        },
    },

    {
        "name": "computer_control",
        "description": (
            "Direct computer control: type, click, hotkeys, "
            "scroll, move mouse, screenshots and screen finding."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "text": {"type": "STRING"},
                "x": {"type": "INTEGER"},
                "y": {"type": "INTEGER"},
                "keys": {"type": "STRING"},
                "key": {"type": "STRING"},
                "direction": {"type": "STRING"},
                "amount": {"type": "INTEGER"},
                "seconds": {"type": "NUMBER"},
                "title": {"type": "STRING"},
                "description": {"type": "STRING"},
                "type": {"type": "STRING"},
                "field": {"type": "STRING"},
                "clear_first": {"type": "BOOLEAN"},
                "path": {"type": "STRING"},
            },
            "required": ["action"],
        },
    },

    {
        "name": "game_updater",
        "description": (
            "The ONLY tool for Steam or Epic Games requests. "
            "Use for installing, updating, downloading, listing "
            "games and checking download status."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "platform": {"type": "STRING"},
                "game_name": {"type": "STRING"},
                "app_id": {"type": "STRING"},
                "hour": {"type": "INTEGER"},
                "minute": {"type": "INTEGER"},
                "shutdown_when_done": {"type": "BOOLEAN"},
            },
            "required": [],
        },
    },

    {
        "name": "flight_finder",
        "description": (
            "Searches Google Flights and speaks the best options."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin": {"type": "STRING"},
                "destination": {"type": "STRING"},
                "date": {"type": "STRING"},
                "return_date": {"type": "STRING"},
                "passengers": {"type": "INTEGER"},
                "cabin": {"type": "STRING"},
                "save": {"type": "BOOLEAN"},
            },
            "required": [
                "origin",
                "destination",
                "date",
            ],
        },
    },

    {
        "name": "file_processor",
        "description": (
            "Processes uploaded files including images, PDFs, "
            "Word documents, spreadsheets, JSON, XML, code, "
            "audio, video, archives and presentations."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {"type": "STRING"},
                "action": {"type": "STRING"},
                "instruction": {"type": "STRING"},
                "format": {"type": "STRING"},
                "width": {"type": "INTEGER"},
                "height": {"type": "INTEGER"},
                "scale": {"type": "NUMBER"},
                "quality": {"type": "INTEGER"},
                "start": {"type": "STRING"},
                "end": {"type": "STRING"},
                "timestamp": {"type": "STRING"},
                "column": {"type": "STRING"},
                "value": {"type": "STRING"},
                "condition": {"type": "STRING"},
                "ascending": {"type": "BOOLEAN"},
                "save": {"type": "BOOLEAN"},
                "destination": {"type": "STRING"},
            },
            "required": [],
        },
    },

    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down JEEV completely. "
            "THIS IS A HIGH-RISK TOOL. "
            "ONLY call this when the user's latest command "
            "clearly and explicitly tells JEEV itself to "
            "shut down, exit, quit, or turn off. "
            "Do NOT call this for laptop shutdown, computer "
            "shutdown, Windows shutdown, restarting Windows, "
            "closing applications, or unrelated conversation."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },

    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user "
            "to long-term memory."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity, preferences, projects, "
                        "relationships, wishes or notes"
                    ),
                },
                "key": {
                    "type": "STRING",
                    "description": "Short snake_case key",
                },
                "value": {
                    "type": "STRING",
                    "description": "Concise English value",
                },
            },
            "required": [
                "category",
                "key",
                "value",
            ],
        },
    },

    {
        "name": "media_control",
        "description": (
            "Controls system-wide Windows media playback. "
            "Use for play, pause, next, previous, stop, "
            "volume and mute."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "play, pause, play_pause, next, previous, "
                        "prev, stop, volume_up, volume_down, mute"
                    ),
                }
            },
            "required": ["action"],
        },
    },
]


# ============================================================
# JARVIS LIVE ENGINE
# ============================================================

class JeevLive:

    def __init__(
        self,
        ui: JarvisUI,
    ):

        self.ui = ui

        self.session = None

        self.audio_in_queue = None

        self.out_queue = None

        self._loop = None

        self._is_speaking = False

        self._speaking_lock = threading.Lock()

        self._audio_stream = None

        # ----------------------------------------------------
        # AUDIO STATE
        # ----------------------------------------------------

        self._audio_playing = False

        self._audio_state_lock = threading.Lock()

        self._audio_turn_active = False

        self._audio_turn_lock = asyncio.Lock()

        self._drain_task = None

        self._turn_counter = 0

        self._active_turn_id = 0

        # ----------------------------------------------------
        # CONTROL
        # ----------------------------------------------------

        self._shutdown_requested = False

        self._last_user_text = ""

        self._text_lock = threading.Lock()

        self._online_logged = False

        self._session_error = False

        # ----------------------------------------------------
        # UI
        # ----------------------------------------------------

        self.ui.on_text_command = (
            self._on_text_command
        )


    # ========================================================
    # TEXT COMMAND
    # ========================================================

    def _on_text_command(
        self,
        text: str,
    ):

        text = (
            text or ""
        ).strip()

        if not text:
            return

        if not self._loop:

            print(
                "[JEEV] ⚠️ "
                "Event loop not ready."
            )

            return

        if not self.session:

            print(
                "[JEEV] ⚠️ "
                "Gemini session not ready."
            )

            return

        print(
            f"[JEEV] 📝 Sending text: {text}"
        )

        with self._text_lock:
            self._last_user_text = text

        async def send_text():

            try:

                await self.session.send_realtime_input(
                    text=text
                )

            except Exception as e:

                print(
                    "[JEEV] Text command error: "
                    f"{e}"
                )

        try:

            asyncio.run_coroutine_threadsafe(
                send_text(),
                self._loop,
            )

        except Exception as e:

            print(
                "[JEEV] Text command error: "
                f"{e}"
            )


    # ========================================================
    # SPEAKING STATE
    # ========================================================

    def set_speaking(
        self,
        value: bool,
    ):

        with self._speaking_lock:

            self._is_speaking = value

        try:

            if value:

                self.ui.set_state(
                    "SPEAKING"
                )

            elif not self.ui.muted:

                self.ui.set_state(
                    "LISTENING"
                )

        except Exception:
            pass


    # ========================================================
    # SPEAK
    # ========================================================

    def speak(
        self,
        text: str,
    ):

        text = (
            text or ""
        ).strip()

        if not text:
            return

        if not self._loop:
            return

        if not self.session:
            return

        async def send_text():

            try:

                await self.session.send_realtime_input(
                    text=text
                )

            except Exception as e:

                print(
                    "[JEEV] Speak error: "
                    f"{e}"
                )

        try:

            asyncio.run_coroutine_threadsafe(
                send_text(),
                self._loop,
            )

        except Exception as e:

            print(
                "[JEEV] Speak error: "
                f"{e}"
            )


    # ========================================================
    # TOOL ERROR
    # ========================================================

    def speak_error(
        self,
        tool_name: str,
        error: str,
    ):

        short = str(error)[:160]

        try:

            self.ui.write_log(
                f"ERR: {tool_name} — {short}"
            )

        except Exception:
            pass

        self.speak(
            f"Sir, {tool_name} encountered "
            f"an error. {short}"
        )


    # ========================================================
    # SAFE SHUTDOWN CHECK
    # ========================================================

    def _shutdown_was_explicitly_requested(
        self,
    ) -> bool:

        with self._text_lock:

            text = (
                self._last_user_text
                or ""
            ).strip().lower()

        if not text:
            return False

        normalized = re.sub(
            r"[^a-z0-9\s]",
            " ",
            text,
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        ).strip()

        negative_phrases = [
            "do not shut down jeev",
            "dont shut down jeev",
            "don't shut down jeev",
            "do not turn off jeev",
            "dont turn off jeev",
            "don't turn off jeev",
            "do not exit jeev",
            "dont exit jeev",
            "don't exit jeev",
            "do not quit jeev",
            "dont quit jeev",
            "don't quit jeev",
        ]

        for phrase in negative_phrases:

            if phrase in normalized:
                return False

        explicit_phrases = [
            "shut down jeev",
            "shutdown jeev",
            "turn off jeev",
            "turn jeev off",
            "exit jeev",
            "quit jeev",
            "close jeev",
            "stop jeev",
            "terminate jeev",
            "end jeev",
        ]

        for phrase in explicit_phrases:

            if phrase in normalized:
                return True

        words = normalized.split()

        if "jeev" in words:

            shutdown_words = {
                "exit",
                "quit",
                "shutdown",
                "shut",
                "stop",
                "terminate",
            }

            if any(
                word in words
                for word in shutdown_words
            ):

                return True

            if (
                "turn" in words
                and
                "off" in words
            ):

                return True

        return False


    # ========================================================
    # BUILD GEMINI CONFIG
    # ========================================================

    def _build_config(
        self,
    ) -> types.LiveConnectConfig:

        memory = load_memory()

        mem_str = (
            format_memory_for_prompt(
                memory
            )
        )

        sys_prompt = (
            _load_system_prompt()
        )

        now = datetime.now()

        time_str = now.strftime(
            "%A, %B %d, %Y — %I:%M %p"
        )

        time_ctx = (
            "[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            "Use this to calculate exact times "
            "for reminders.\n\n"
        )

        parts = [
            time_ctx
        ]

        if mem_str:
            parts.append(mem_str)

        parts.append(sys_prompt)

        return types.LiveConnectConfig(

            response_modalities=[
                "AUDIO"
            ],

            output_audio_transcription={},

            input_audio_transcription={},

            system_instruction="\n".join(
                parts
            ),

            tools=[
                {
                    "function_declarations":
                        TOOL_DECLARATIONS
                }
            ],

            session_resumption=(
                types.SessionResumptionConfig()
            ),

            speech_config=types.SpeechConfig(

                voice_config=(
                    types.VoiceConfig(

                        prebuilt_voice_config=(
                            types.PrebuiltVoiceConfig(
                                voice_name="Charon"
                            )
                        )
                    )
                )
            ),
        )


    # ========================================================
    # EXECUTE TOOL
    # ========================================================

    async def _execute_tool(
        self,
        fc,
    ):

        name = fc.name

        args = dict(
            fc.args or {}
        )

        print(
            f"[JEEV] 📞 {name}"
        )

        print(
            f"[JEEV] 🔧 {name} {args}"
        )

        try:

            self.ui.set_state(
                "THINKING"
            )

        except Exception:
            pass


        # ====================================================
        # SAVE MEMORY
        # ====================================================

        if name == "save_memory":

            category = args.get(
                "category",
                "notes",
            )

            key = args.get(
                "key",
                "",
            )

            value = args.get(
                "value",
                "",
            )

            if key and value:

                update_memory(
                    {
                        category: {
                            key: {
                                "value": value
                            }
                        }
                    }
                )

                print(
                    "[Memory] 💾 "
                    f"{category}/{key} = {value}"
                )

            try:

                if not self.ui.muted:

                    self.ui.set_state(
                        "LISTENING"
                    )

            except Exception:
                pass

            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={
                    "result": "ok",
                    "silent": True,
                },
            )


        # ====================================================
        # SHUTDOWN JARVIS
        # ====================================================

        if name == "shutdown_jarvis":

            if not self._shutdown_was_explicitly_requested():

                print(
                    "[JEEV] 🛡️ "
                    "Blocked unauthorized shutdown."
                )

                try:

                    self.ui.write_log(
                        "SECURITY: Unauthorized "
                        "shutdown blocked."
                    )

                except Exception:
                    pass

                try:

                    if not self.ui.muted:

                        self.ui.set_state(
                            "LISTENING"
                        )

                except Exception:
                    pass

                return types.FunctionResponse(
                    id=fc.id,
                    name=name,
                    response={
                        "result": (
                            "Shutdown blocked. "
                            "The user did not explicitly "
                            "request JEEV shutdown."
                        ),
                        "blocked": True,
                    },
                )

            self._shutdown_requested = True

            try:

                self.ui.write_log(
                    "SYS: JEEV shutdown requested."
                )

            except Exception:
                pass

            print(
                "[JEEV] 🔴 "
                "Explicit JEEV shutdown confirmed."
            )

            self.speak(
                "Goodbye, sir."
            )

            def shutdown():

                time.sleep(1)

                os._exit(0)

            threading.Thread(
                target=shutdown,
                daemon=True,
            ).start()

            return types.FunctionResponse(
                id=fc.id,
                name=name,
                response={
                    "result": "Shutting down JEEV."
                },
            )


        loop = asyncio.get_running_loop()

        result = "Done."


        try:

            # =================================================
            # OPEN APP
            # =================================================

            if name == "open_app":

                r = await loop.run_in_executor(
                    None,
                    lambda: open_app(
                        parameters=args,
                        response=None,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    f"Opened {args.get('app_name')}."
                )


            # =================================================
            # WEATHER
            # =================================================

            elif name == "weather_report":

                r = await loop.run_in_executor(
                    None,
                    lambda: weather_action(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Weather delivered."
                )


            # =================================================
            # BROWSER
            # =================================================

            elif name == "browser_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: browser_control(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # FILE CONTROLLER
            # =================================================

            elif name == "file_controller":

                r = await loop.run_in_executor(
                    None,
                    lambda: file_controller(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # SEND MESSAGE
            # =================================================

            elif name == "send_message":

                r = await loop.run_in_executor(
                    None,
                    lambda: send_message(
                        parameters=args,
                        response=None,
                        player=self.ui,
                        session_memory=None,
                    ),
                )

                result = (
                    r
                    or
                    f"Message sent to "
                    f"{args.get('receiver')}."
                )

            # =================================================
            # WHATSAPP CONTROL
            # =================================================

            elif name == "whatsapp_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: whatsapp_control(
                        parameters=args,
                        response=None,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "WhatsApp action completed."
                )
            # =================================================
            # REMINDER
            # =================================================

            elif name == "reminder":

                r = await loop.run_in_executor(
                    None,
                    lambda: reminder(
                        parameters=args,
                        response=None,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Reminder set."
                )


            # =================================================
            # YOUTUBE
            # =================================================

            elif name == "youtube_video":

                r = await loop.run_in_executor(
                    None,
                    lambda: youtube_video(
                        parameters=args,
                        response=None,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # FILE PROCESSOR
            # =================================================

            elif name == "file_processor":

                if (
                    not args.get("file_path")
                    and
                    getattr(
                        self.ui,
                        "current_file",
                        None,
                    )
                ):

                    args["file_path"] = (
                        self.ui.current_file
                    )

                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(
                        parameters=args,
                        player=self.ui,
                        speak=self.speak,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # SCREEN PROCESSOR
            # =================================================

            elif name == "screen_process":

                threading.Thread(
                    target=screen_process,
                    kwargs={
                        "parameters": args,
                        "response": None,
                        "player": self.ui,
                        "session_memory": None,
                    },
                    daemon=True,
                ).start()

                result = (
                    "Vision module activated. "
                    "Stay completely silent."
                )


            # =================================================
            # COMPUTER SETTINGS
            # =================================================

            elif name == "computer_settings":

                r = await loop.run_in_executor(
                    None,
                    lambda: computer_settings(
                        parameters=args,
                        response=None,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # DESKTOP
            # =================================================

            elif name == "desktop_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: desktop_control(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # CODE HELPER
            # =================================================

            elif name == "code_helper":

                r = await loop.run_in_executor(
                    None,
                    lambda: code_helper(
                        parameters=args,
                        player=self.ui,
                        speak=self.speak,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # DEV AGENT
            # =================================================

            elif name == "dev_agent":

                r = await loop.run_in_executor(
                    None,
                    lambda: dev_agent(
                        parameters=args,
                        player=self.ui,
                        speak=self.speak,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # AGENT TASK
            # =================================================

            elif name == "agent_task":

                from agent.task_queue import (
                    get_queue,
                    TaskPriority,
                )

                priority_map = {
                    "low": TaskPriority.LOW,
                    "normal": TaskPriority.NORMAL,
                    "high": TaskPriority.HIGH,
                }

                priority = priority_map.get(
                    str(
                        args.get(
                            "priority",
                            "normal",
                        )
                    ).lower(),
                    TaskPriority.NORMAL,
                )

                task_id = get_queue().submit(
                    goal=args.get(
                        "goal",
                        "",
                    ),
                    priority=priority,
                    speak=self.speak,
                )

                result = (
                    f"Task started "
                    f"(ID: {task_id})."
                )


            # =================================================
            # WEB SEARCH
            # =================================================

            elif name == "web_search":

                r = await loop.run_in_executor(
                    None,
                    lambda: web_search_action(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # COMPUTER CONTROL
            # =================================================

            elif name == "computer_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: computer_control(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # MEDIA CONTROL
            # =================================================

            elif name == "media_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: media_control(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # GAME UPDATER
            # =================================================

            elif name == "game_updater":

                if game_updater is None:

                    result = (
                        "Game updater module is not installed "
                        "or actions/game_updater.py is missing."
                    )

                else:

                    r = await loop.run_in_executor(
                        None,
                        lambda: game_updater(
                            parameters=args,
                            player=self.ui,
                            speak=self.speak,
                        ),
                    )

                    result = (
                        r
                        or
                        "Done."
                    )


            # =================================================
            # FLIGHT FINDER
            # =================================================

            elif name == "flight_finder":

                r = await loop.run_in_executor(
                    None,
                    lambda: flight_finder(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = (
                    r
                    or
                    "Done."
                )


            # =================================================
            # UNKNOWN TOOL
            # =================================================

            else:

                result = (
                    f"Unknown tool: {name}"
                )


        except Exception as e:

            result = (
                f"Tool '{name}' failed: {e}"
            )

            traceback.print_exc()

            self.speak_error(
                name,
                e,
            )


        try:

            if not self.ui.muted:

                self.ui.set_state(
                    "LISTENING"
                )

        except Exception:
            pass


        print(
            f"[JEEV] 📤 "
            f"{name} → "
            f"{str(result)[:120]}"
        )

        return types.FunctionResponse(
            id=fc.id,
            name=name,
            response={
                "result": result
            },
        )


    # ========================================================
    # SEND MICROPHONE DATA TO GEMINI
    # ========================================================

    async def _send_realtime_audio(
        self,
    ):

        print(
            "[JEEV] 🎤 Audio sender started"
        )

        while not self._shutdown_requested:

            try:

                audio_bytes = (
                    await self.out_queue.get()
                )

                if audio_bytes is None:
                    break

                if not audio_bytes:
                    continue

                if self.session is None:

                    await asyncio.sleep(
                        0.05
                    )

                    continue

                try:

                    await self.session.send_realtime_input(
                        audio=types.Blob(
                            data=audio_bytes,
                            mime_type="audio/pcm;rate=16000",
                        )
                    )

                except asyncio.CancelledError:

                    raise

                except Exception as e:

                    print(
                        "[JEEV] ⚠️ "
                        f"Audio send error: {e}"
                    )

                    await asyncio.sleep(
                        0.1
                    )

            except asyncio.CancelledError:

                break

            except Exception as e:

                print(
                    "[JEEV] ⚠️ "
                    f"Audio sender error: {e}"
                )

                await asyncio.sleep(
                    0.1
                )

        print(
            "[JEEV] 🎤 "
            "Audio sender stopped"
        )


    # ========================================================
    # LISTEN TO MICROPHONE
    # ========================================================

    async def _listen_audio(
        self,
    ):

        print(
            "[JEEV] 🎤 "
            "Starting microphone..."
        )

        loop = asyncio.get_running_loop()

        def microphone_callback(
            indata,
            frames,
            time_info,
            status,
        ):

            if status:

                print(
                    "[JEEV] 🎤 "
                    f"Mic status: {status}"
                )

            with self._speaking_lock:

                jarvis_speaking = (
                    self._is_speaking
                )

            # ------------------------------------------------
            # Prevent JARVIS from hearing its own voice.
            # ------------------------------------------------

            if jarvis_speaking:
                return

            try:

                if self.ui.muted:
                    return

            except Exception:

                return

            try:

                audio_bytes = (
                    indata
                    .copy()
                    .tobytes()
                )

                loop.call_soon_threadsafe(
                    self._queue_microphone_audio,
                    audio_bytes,
                )

            except Exception as e:

                print(
                    "[JEEV] ❌ "
                    f"Mic callback error: {e}"
                )

        def open_microphone():

            return sd.InputStream(

                samplerate=SEND_SAMPLE_RATE,

                channels=CHANNELS,

                dtype="int16",

                blocksize=CHUNK_SIZE,

                callback=microphone_callback,
            )

        try:

            with open_microphone() as stream:

                print(
                    "[JEEV] 🎤 "
                    "Microphone is LIVE"
                )

                while not self._shutdown_requested:

                    await asyncio.sleep(
                        0.05
                    )

        except asyncio.CancelledError:

            raise

        except Exception as e:

            print(
                "[JEEV] ❌ "
                f"Microphone error: {e}"
            )

            traceback.print_exc()

            raise

        finally:

            print(
                "[JEEV] 🎤 "
                "Microphone stopped"
            )


    # ========================================================
    # QUEUE MICROPHONE AUDIO
    # ========================================================

    def _queue_microphone_audio(
        self,
        audio_bytes,
    ):

        if not self.out_queue:
            return

        if not audio_bytes:
            return

        try:

            if self.out_queue.full():
                return

            self.out_queue.put_nowait(
                audio_bytes
            )

        except asyncio.QueueFull:

            pass

        except Exception as e:

            print(
                "[JEEV] "
                f"Microphone queue error: {e}"
            )


    # ========================================================
    # CLEAR AUDIO QUEUE
    # ========================================================

    def _clear_audio_queue(
        self,
    ):

        if not self.audio_in_queue:
            return

        cleared = 0

        while True:

            try:

                self.audio_in_queue.get_nowait()

                cleared += 1

            except asyncio.QueueEmpty:

                break

            except Exception:

                break

        if cleared:

            print(
                "[JEEV] 🧹 "
                f"Cleared {cleared} queued audio chunks."
            )


    # ========================================================
    # AUDIO DRAIN
    # ========================================================

    async def _drain_audio_after_turn(
        self,
        turn_id: int,
    ):

        try:

            # ------------------------------------------------
            # Wait for all final audio packets to arrive.
            # ------------------------------------------------

            await asyncio.sleep(
                0.08
            )

            stable_empty_count = 0

            while not self._shutdown_requested:

                if turn_id != self._active_turn_id:

                    return

                queue_empty = (
                    self.audio_in_queue is None
                    or self.audio_in_queue.empty()
                )

                with self._audio_state_lock:

                    still_playing = (
                        self._audio_playing
                    )

                if (
                    queue_empty
                    and
                    not still_playing
                ):

                    stable_empty_count += 1

                    if stable_empty_count >= 6:

                        break

                else:

                    stable_empty_count = 0

                await asyncio.sleep(
                    0.03
                )

            # ------------------------------------------------
            # Give PortAudio a little time to finish the
            # final hardware buffer.
            # ------------------------------------------------

            await asyncio.sleep(
                0.15
            )

            if turn_id == self._active_turn_id:

                with self._audio_state_lock:

                    still_playing = (
                        self._audio_playing
                    )

                if not still_playing:

                    self._audio_turn_active = False

                    self.set_speaking(
                        False
                    )

                    print(
                        "[JEEV] 🔊 "
                        "Audio completely drained."
                    )

        except asyncio.CancelledError:

            raise

        except Exception as e:

            print(
                "[JEEV] ⚠️ "
                f"Audio drain error: {e}"
            )


    # ========================================================
    # START AUDIO DRAIN
    # ========================================================

    def _start_audio_drain(
        self,
    ):

        self._turn_counter += 1

        self._active_turn_id = (
            self._turn_counter
        )

        turn_id = (
            self._active_turn_id
        )

        self._audio_turn_active = True

        if (
            self._drain_task
            and
            not self._drain_task.done()
        ):

            self._drain_task.cancel()

        self._drain_task = asyncio.create_task(
            self._drain_audio_after_turn(
                turn_id
            )
        )


    # ========================================================
    # RECEIVE GEMINI AUDIO / EVENTS
    # ========================================================

    async def _receive_audio(
        self,
    ):

        print(
            "[JEEV] 👂 "
            "Gemini receiver started"
        )

        input_text_buffer = []

        output_text_buffer = []

        try:

            while not self._shutdown_requested:

                try:

                    print(
                        "[JEEV] 👂 "
                        "Waiting for next turn..."
                    )

                    async for response in (
                        self.session.receive()
                    ):

                        server_content = (
                            response.server_content
                        )

                        if server_content:

                            # =================================
                            # INTERRUPTION
                            # =================================

                            if (
                                getattr(
                                    server_content,
                                    "interrupted",
                                    False,
                                )
                            ):

                                print(
                                    "[JEEV] 🛑 "
                                    "Gemini response interrupted."
                                )

                                self._turn_counter += 1

                                self._active_turn_id = (
                                    self._turn_counter
                                )

                                self._audio_turn_active = False

                                self._clear_audio_queue()

                                with self._audio_state_lock:

                                    self._audio_playing = False

                                self.set_speaking(
                                    False
                                )

                                continue


                            # =================================
                            # MODEL AUDIO
                            # =================================

                            if server_content.model_turn:

                                for part in (
                                    server_content
                                    .model_turn
                                    .parts
                                ):

                                    if (
                                        part.inline_data
                                        and
                                        part.inline_data.data
                                    ):

                                        audio_data = (
                                            part
                                            .inline_data
                                            .data
                                        )

                                        if self.audio_in_queue:

                                            try:

                                                # ------------------------------------------------
                                                # IMPORTANT:
                                                # Don't drop audio response chunks.
                                                # ------------------------------------------------

                                                await (
                                                    self
                                                    .audio_in_queue
                                                    .put(
                                                        audio_data
                                                    )
                                                )

                                                self._audio_turn_active = True

                                                self.set_speaking(
                                                    True
                                                )

                                            except Exception as e:

                                                print(
                                                    "[JEEV] "
                                                    "Audio queue error: "
                                                    f"{e}"
                                                )


                            # =================================
                            # JARVIS OUTPUT TRANSCRIPTION
                            # =================================

                            if (
                                server_content
                                .output_transcription
                                and
                                server_content
                                .output_transcription
                                .text
                            ):

                                text = (
                                    server_content
                                    .output_transcription
                                    .text
                                    .strip()
                                )

                                if text:

                                    output_text_buffer.append(
                                        text
                                    )

                                    self.set_speaking(
                                        True
                                    )


                            # =================================
                            # USER INPUT TRANSCRIPTION
                            # =================================

                            if (
                                server_content
                                .input_transcription
                                and
                                server_content
                                .input_transcription
                                .text
                            ):

                                text = (
                                    server_content
                                    .input_transcription
                                    .text
                                    .strip()
                                )

                                if text:

                                    input_text_buffer.append(
                                        text
                                    )

                                    with self._text_lock:

                                        self._last_user_text = (
                                            text
                                        )

                                    print(
                                        "[JEEV] 👤 Heard: "
                                        f"{text}"
                                    )


                            # =================================
                            # GENERATION COMPLETE
                            # =================================

                            if getattr(
                                server_content,
                                "generation_complete",
                                False,
                            ):

                                print(
                                    "[JEEV] 🧠 "
                                    "Generation complete."
                                )


                            # =================================
                            # TURN COMPLETE
                            # =================================

                            if server_content.turn_complete:

                                full_input = (
                                    " ".join(
                                        input_text_buffer
                                    ).strip()
                                )

                                full_output = (
                                    " ".join(
                                        output_text_buffer
                                    ).strip()
                                )

                                if full_input:

                                    with self._text_lock:

                                        self._last_user_text = (
                                            full_input
                                        )

                                    try:

                                        self.ui.write_log(
                                            f"You: {full_input}"
                                        )

                                    except Exception:
                                        pass

                                if full_output:

                                    try:

                                        self.ui.write_log(
                                            f"Jeev: {full_output}"
                                        )

                                    except Exception:
                                        pass

                                if (
                                    full_input
                                    and
                                    len(full_input) > 5
                                ):

                                    threading.Thread(

                                        target=_update_memory_async,

                                        args=(
                                            full_input,
                                            full_output,
                                        ),

                                        daemon=True,

                                    ).start()

                                input_text_buffer.clear()

                                output_text_buffer.clear()

                                print(
                                    "[JEEV] 🔄 "
                                    "Turn complete — "
                                    "draining audio..."
                                )

                                # ------------------------------------------------
                                # IMPORTANT:
                                #
                                # Do NOT set SPEAKING false here.
                                #
                                # Gemini may have finished generating while
                                # audio packets are still waiting to play.
                                # ------------------------------------------------

                                self._start_audio_drain()


                        # =========================================
                        # TOOL CALL
                        # =========================================

                        if response.tool_call:

                            function_responses = []

                            for function_call in (
                                response
                                .tool_call
                                .function_calls
                            ):

                                function_response = (
                                    await self._execute_tool(
                                        function_call
                                    )
                                )

                                function_responses.append(
                                    function_response
                                )

                            if function_responses:

                                try:

                                    await (
                                        self.session
                                        .send_tool_response(
                                            function_responses=(
                                                function_responses
                                            )
                                        )
                                    )

                                    print(
                                        "[JEEV] 📤 "
                                        "Tool response sent."
                                    )

                                except Exception as e:

                                    print(
                                        "[JEEV] ❌ "
                                        "Tool response error: "
                                        f"{e}"
                                    )

                                    raise


                    # =================================================
                    # RECEIVE ITERATOR ENDED
                    # =================================================

                    if not self._shutdown_requested:

                        await asyncio.sleep(
                            0.05
                        )

                        continue


                except asyncio.CancelledError:

                    raise


                except Exception as e:

                    print(
                        "[JEEV] ⚠️ "
                        f"Receiver turn error: {e}"
                    )

                    error_text = str(e)

                    if (
                        "1011" in error_text
                        or
                        "Internal error" in error_text
                        or
                        "ConnectionClosedError" in error_text
                    ):

                        print(
                            "[JEEV] 🔄 "
                            "Gemini connection appears closed. "
                            "Reconnecting..."
                        )

                        self._session_error = True

                        break

                    traceback.print_exc()

                    await asyncio.sleep(
                        0.5
                    )

                    continue


        except asyncio.CancelledError:

            raise

        except Exception as e:

            print(
                "[JEEV] ❌ "
                f"Receiver error: {e}"
            )

            traceback.print_exc()

            raise

        finally:

            # ------------------------------------------------
            # Do not force SPEAKING false if audio is still
            # being played. The audio player controls that.
            # ------------------------------------------------

            with self._audio_state_lock:

                still_playing = (
                    self._audio_playing
                )

            if not still_playing:

                self._audio_turn_active = False

                self.set_speaking(
                    False
                )

            print(
                "[JEEV] 👂 "
                "Gemini receiver stopped"
            )


    # ========================================================
    # PLAY GEMINI AUDIO
    # ========================================================

    async def _play_audio(
        self,
    ):

        print(
            "[JEEV] 🔊 "
            "Starting audio output..."
        )

        stream = None

        try:

            output_device = OUTPUT_DEVICE

            if output_device is None:

                print(
                    "[JEEV] 🔊 "
                    "Output device: DEFAULT"
                )

            else:

                print(
                    "[JEEV] 🔊 "
                    f"Output device: {output_device}"
                )


            # =================================================
            # ALWAYS USE GEMINI'S NATIVE 24 KHZ
            # =================================================

            output_sample_rate = (
                RECEIVE_SAMPLE_RATE
            )

            try:

                stream = sd.RawOutputStream(

                    device=output_device,

                    samplerate=output_sample_rate,

                    channels=OUTPUT_CHANNELS,

                    dtype="int16",

                    blocksize=CHUNK_SIZE,

                    latency="low",
                )

                stream.start()

                print(
                    "[JEEV] 🔊 "
                    f"Output sample rate: "
                    f"{output_sample_rate} Hz"
                )

            except Exception as e:

                print(
                    "[JEEV] ❌ "
                    "24 kHz output could not be opened: "
                    f"{e}"
                )

                raise


            self._audio_stream = stream

            print(
                "[JEEV] 🔊 "
                "Audio output is LIVE"
            )


            # =================================================
            # AUDIO PLAYBACK LOOP
            # =================================================

            while not self._shutdown_requested:

                try:

                    audio_chunk = (
                        await self.audio_in_queue.get()
                    )

                except asyncio.CancelledError:

                    raise

                if audio_chunk is None:
                    break

                if not audio_chunk:
                    continue


                # ------------------------------------------------
                # Mark playback active BEFORE writing.
                # ------------------------------------------------

                with self._audio_state_lock:

                    self._audio_playing = True

                self.set_speaking(
                    True
                )


                try:

                    # Gemini sends signed 16-bit PCM.
                    # No resampling is necessary because
                    # output is natively 24 kHz.

                    audio_output = (
                        bytes(audio_chunk)
                    )

                    if not audio_output:
                        continue


                    # ------------------------------------------------
                    # ACTUAL AUDIO WRITE
                    # ------------------------------------------------

                    await asyncio.to_thread(
                        stream.write,
                        audio_output
                    )


                except asyncio.CancelledError:

                    raise

                except Exception as e:

                    print(
                        "[JEEV] ⚠️ "
                        f"Playback error: {e}"
                    )

                    traceback.print_exc()

                finally:

                    with self._audio_state_lock:

                        self._audio_playing = False


        except asyncio.CancelledError:

            raise

        except Exception as e:

            print(
                "[JEEV] ❌ "
                f"Audio output error: {e}"
            )

            traceback.print_exc()

        finally:

            with self._audio_state_lock:

                self._audio_playing = False

            self._audio_stream = None

            if stream:

                try:

                    # ------------------------------------------------
                    # Wait for PortAudio's final buffered samples
                    # before closing the stream.
                    # ------------------------------------------------

                    await asyncio.sleep(
                        0.15
                    )

                except Exception:
                    pass

                try:

                    stream.stop()

                except Exception:
                    pass

                try:

                    stream.close()

                except Exception:
                    pass

            print(
                "[JEEV] 🔊 "
                "Audio output stopped."
            )


    # ========================================================
    # RUN JEEV
    # ========================================================

    async def run(
        self,
    ):

        api_key = _get_api_key()

        print(
            "[JEEV] 🔑 "
            "Gemini API key loaded."
        )

        client = genai.Client(
            api_key=api_key,
            http_options={
                "api_version": "v1beta"
            },
        )


        while not self._shutdown_requested:

            try:

                print(
                    "[JEEV] 🔌 "
                    "Connecting to Gemini..."
                )

                try:

                    self.ui.set_state(
                        "THINKING"
                    )

                except Exception:
                    pass

                config = self._build_config()


                # =================================================
                # GEMINI LIVE SESSION
                # =================================================

                async with client.aio.live.connect(
                    model=LIVE_MODEL,
                    config=config,
                ) as session:

                    self.session = session

                    self._loop = (
                        asyncio.get_running_loop()
                    )

                    # ------------------------------------------------
                    # Larger response queue prevents audio starvation.
                    # ------------------------------------------------

                    self.audio_in_queue = (
                        asyncio.Queue(
                            maxsize=300
                        )
                    )

                    self.out_queue = (
                        asyncio.Queue(
                            maxsize=50
                        )
                    )

                    self._session_error = False

                    self._audio_turn_active = False

                    self._turn_counter = 0

                    self._active_turn_id = 0


                    print(
                        "[JEEV] ✅ "
                        "Gemini Live connected."
                    )

                    try:

                        self.ui.set_state(
                            "LISTENING"
                        )

                    except Exception:
                        pass


                    if not self._online_logged:

                        try:

                            self.ui.write_log(
                                "SYS: JEEV online."
                            )

                        except Exception:
                            pass

                        self._online_logged = True


                    print(
                        "[JEEV] 🎤 "
                        "Ready for commands."
                    )


                    # =================================================
                    # START LONG-LIVED TASKS
                    # =================================================

                    audio_sender_task = asyncio.create_task(
                        self._send_realtime_audio()
                    )

                    microphone_task = asyncio.create_task(
                        self._listen_audio()
                    )

                    receiver_task = asyncio.create_task(
                        self._receive_audio()
                    )

                    audio_player_task = asyncio.create_task(
                        self._play_audio()
                    )


                    tasks = [
                        audio_sender_task,
                        microphone_task,
                        receiver_task,
                        audio_player_task,
                    ]


                    try:

                        # =================================================
                        # MONITOR TASKS
                        # =================================================

                        while (
                            not self._shutdown_requested
                            and
                            not self._session_error
                        ):

                            await asyncio.sleep(
                                0.25
                            )

                            for task in tasks:

                                if not task.done():
                                    continue

                                try:

                                    exc = (
                                        task.exception()
                                    )

                                except asyncio.CancelledError:

                                    exc = None

                                if exc:

                                    print(
                                        "[JEEV] ⚠️ "
                                        "Core task failed: "
                                        f"{exc}"
                                    )

                                    traceback.print_exception(
                                        type(exc),
                                        exc,
                                        exc.__traceback__,
                                    )

                                    self._session_error = True

                                    break


                                if not self._shutdown_requested:

                                    print(
                                        "[JEEV] ⚠️ "
                                        "A core task ended. "
                                        "Restarting session."
                                    )

                                    self._session_error = True

                                    break


                    finally:

                        # ------------------------------------------------
                        # Cancel audio drain task too.
                        # ------------------------------------------------

                        if (
                            self._drain_task
                            and
                            not self._drain_task.done()
                        ):

                            self._drain_task.cancel()

                        for task in tasks:

                            if not task.done():

                                task.cancel()

                        await asyncio.gather(
                            *tasks,
                            return_exceptions=True,
                        )

                        if self._drain_task:

                            await asyncio.gather(
                                self._drain_task,
                                return_exceptions=True,
                            )


            except asyncio.CancelledError:

                raise


            except Exception as e:

                print(
                    "[JEEV] ⚠️ "
                    f"Connection error: {e}"
                )

                traceback.print_exc()

                self._session_error = True


            finally:

                self.session = None

                self._loop = None

                self.audio_in_queue = None

                self.out_queue = None

                self._audio_turn_active = False

                with self._audio_state_lock:

                    self._audio_playing = False

                self.set_speaking(
                    False
                )

                self._session_error = False


            if self._shutdown_requested:

                break


            try:

                self.ui.set_state(
                    "THINKING"
                )

            except Exception:
                pass


            print(
                "[JEEV] 🔄 "
                "Gemini session ended. "
                "Reconnecting in 3 seconds..."
            )

            await asyncio.sleep(
                3
            )

            self._online_logged = True


        print(
            "[JEEV] 🔴 "
            "JEEV stopped."
        )


# ============================================================
# MAIN
# ============================================================

def main():

    ui = JarvisUI(
        "face.png"
    )


    def runner():

        try:

            ui.wait_for_api_key()

            jeev = JeevLive(
                ui
            )

            asyncio.run(
                jeev.run()
            )

        except KeyboardInterrupt:

            print(
                "\n🔴 Shutting down..."
            )

        except Exception as e:

            print(
                "[JEEV] ❌ "
                f"Fatal error: {e}"
            )

            traceback.print_exc()


    threading.Thread(
        target=runner,
        daemon=True,
    ).start()

    ui.root.mainloop()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
