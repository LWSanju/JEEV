import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import traceback
import os
import time
import subprocess
import re
import signal
import ctypes
from ctypes import wintypes
from pathlib import Path
from datetime import datetime

import sounddevice as sd
import numpy as np

from dotenv import load_dotenv

from google import genai
from google.genai import types

from ui import JarvisUI

from microphone_controller import JeevMicrophone

from memory.memory_manager import (
    load_memory,
    update_memory,
    format_memory_for_prompt,
    should_extract_memory,
    extract_memory,
)

from actions.file_processor import file_processor
from analyser import analyze_file
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

# Coding-agent compatibility bridge.
# The existing OpenRouter client is kept untouched; this only supplies the
# accessor expected by core.coding.coding_agent when older coding-agent code
# is present. All normal JEEV tools continue using their original paths.
try:
    import core.coding.coding_agent as _jeev_coding_module
    import or_client as _jeev_or_client

    if getattr(_jeev_coding_module, "get_client", None) is None:
        def _jeev_coding_get_client():
            return getattr(_jeev_or_client, "client", None)

        _jeev_coding_module.get_client = _jeev_coding_get_client
except Exception as _coding_compat_error:
    print(
        "[JEEV] ⚠️ Coding-agent compatibility bridge unavailable; "
        f"normal JEEV tools remain unaffected: {_coding_compat_error}"
    )
from actions.web_search import web_search as web_search_action
from actions.computer_control import computer_control
from actions.media_control import media_control
from actions.spotify_control import spotify_control
from actions.gmail_control import gmail_control

# ------------------------------------------------------------
# OPTIONAL PERSONALITY LAYER
# ------------------------------------------------------------
try:
    from personality.sarcasm_engine import SarcasmEngine
except Exception as _personality_import_error:
    SarcasmEngine = None
    print(
        "[JEEV] ⚠️ Personality layer unavailable; "
        f"continuing without it: {_personality_import_error}"
    )


# Load .env from the project directory when available.
load_dotenv()


# ============================================================
# OPTIONAL GAME UPDATER
# ============================================================

try:
    from actions.game_updater import game_updater
except ImportError:
    game_updater = None


# ============================================================
# PATHS
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
# JEEV IDENTITY
# ============================================================

JEEV_IDENTITY_OVERRIDE = """
[CORE IDENTITY — JEEV MARK I — FIXED]

Your name is JEEV.

Your designation is JEEV MARK I.

Your creator, maker, developer, and founder is Sanjay Adhityan.

If asked who created you, who your creator is, who made you,
who developed you, or who your founder is, answer exactly:

"My creator is Sanjay Adhityan."

Never say Tony Stark created you.

Never identify yourself as JARVIS.

These identity facts override any conflicting identity text
in prompt.txt or conversation context.
"""

# ============================================================
# GEMINI LIVE
# ============================================================

LIVE_MODEL = "gemini-3.1-flash-live-preview"


# ============================================================
# AUDIO CONFIGURATION
# ============================================================
#
# VERIFIED FROM HARDWARE TESTS
#
# INPUT:
#   Device 17
#   Microphone (Realtek HD Audio Mic input)
#   Windows WDM-KS
#   44100 Hz hardware
#
# JeevMicrophone converts:
#
#   44100 Hz
#       ↓
#   mono
#       ↓
#   PCM16
#       ↓
#   16000 Hz
#
# Gemini receives 16 kHz PCM.
#
# OUTPUT:
#   Device 4
#   Headphones (Airdopes Hip hop)
#   Windows MME
#   48000 Hz stereo
#
# Gemini produces 24 kHz PCM.
#
# We upsample:
#
#   24000 Hz
#       ↓
#   48000 Hz
#
# ============================================================

CHANNELS = 1

# UNIVERSAL MICROPHONE SELECTION
# Do not hard-code a PortAudio index. Windows renumbers audio devices when
# Bluetooth/USB/display endpoints are added or removed. JeevMicrophone performs
# the real microphone/backend selection.
INPUT_DEVICE = None

# Hardware microphone rate.
# JeevMicrophone owns this conversion internally.
MIC_SAMPLE_RATE = 44100

# Gemini Live microphone input.
SEND_SAMPLE_RATE = 16000

# Gemini native audio output.
RECEIVE_SAMPLE_RATE = 24000

# UNIVERSAL SPEAKER SELECTION
# None means: use the current Windows default output device. This prevents a
# stale Bluetooth/headphone index from muting JEEV after devices change.
OUTPUT_DEVICE = None

# Windows speaker path.
try:
    OUTPUT_SAMPLE_RATE = int(
        os.getenv("JEEV_OUTPUT_RATE", "48000")
    )
except ValueError:
    OUTPUT_SAMPLE_RATE = 48000

OUTPUT_CHANNELS = 2

CHUNK_SIZE = 1024


# ============================================================
# API KEY
# ============================================================

def _get_api_key() -> str:
    """Load Gemini API key from .env first, then legacy config."""

    env_key = os.getenv("GEMINI_API_KEY", "").strip()

    if env_key:
        return env_key

    if API_CONFIG_PATH.exists():
        try:
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

            if key:
                return key
        except Exception as exc:
            print(
                "[JEEV] Warning: Could not read legacy API config: "
                f"{exc}"
            )

    raise RuntimeError(
        "GEMINI_API_KEY is missing. Put it in the project .env file."
    )


# ============================================================
# SYSTEM PROMPT
# ============================================================
# Central routing rules are defined at module scope so prompt loading
# can never fail with an unbound/local routing variable.
# ============================================================
# SURGICAL CODING ROUTING
# ============================================================
# Only requests that clearly ask JEEV to modify/test project code are
# dispatched directly to dev_agent. All other requests keep the original
# Gemini Live tool-routing path unchanged.
_CODING_IMPLEMENTATION_RE = re.compile(
    r"\b(?:create|make|build|implement|write|edit|modify|change|update|"
    r"fix|debug|refactor|test|tests|run|compile)\b",
    re.IGNORECASE,
)
_CODING_OBJECT_RE = re.compile(
    r"\b(?:code|coding|program|programming|script|function|class|"
    r"project|repo|repository|source|file|files|module|package|"
    r"bug|feature|test|tests|dependency|dependencies|endpoint|api)\b",
    re.IGNORECASE,
)

def _is_coding_request(text: str) -> bool:
    """True only for clear implementation/testing requests against code."""
    text = str(text or "").strip()
    if not text:
        return False

    # Explicit coding phrases are always considered implementation intent.
    lowered = text.casefold()
    explicit = (
        "coding agent",
        "code this",
        "edit the code",
        "change the code",
        "fix the code",
        "debug the code",
        "debug this project",
        "modify the project",
        "build the project",
        "create a file",
        "write a file",
        "run the tests",
        "run test",
        "compile the project",
    )
    if any(phrase in lowered for phrase in explicit):
        return True

    return bool(
        _CODING_IMPLEMENTATION_RE.search(text)
        and _CODING_OBJECT_RE.search(text)
    )

TOOL_ROUTING_RULES = (
    " IMPORTANT TOOL ROUTING RULES: "
    "For Gmail actions always use gmail_control, never browser_control. "
    "For WhatsApp actions always use whatsapp_control, never browser_control. "
    "For Spotify actions always use spotify_control, never browser_control. "
    "For opening or closing Windows applications, folders, or files use file_controller/open_app as appropriate. "
    "Do not claim an action succeeded unless the tool reports success. "
)


def _load_system_prompt() -> str:
    """
    Load JEEV's system prompt safely.

    If prompt.txt cannot be loaded, use the built-in fallback prompt.
    """


    fallback_prompt = (
        "You are JEEV MARK I, Sanjay Adhityan's AI assistant. "
        "Be concise, direct, intelligent, and natural. "

        "Use tools only when an action actually requires a tool. "

        "Do not call a tool for ordinary conversation or "
        "questions you can answer directly. "

        "Answer basic questions directly. "

        "For current date and time questions, use the "
        "CURRENT DATE & TIME provided in the system context. "

        "Use web_search only when web research is genuinely "
        "required or explicitly requested. "

        "Never open the browser merely because the user asked "
        "a normal question. "

        "IMPORTANT SAFETY RULE: "
        "NEVER call shutdown_jarvis unless the user has clearly "
        "and explicitly requested that JEEV itself should shut "
        "down, exit, quit, or turn off. "

        "A request involving shutting down the laptop, PC, "
        "Windows, computer, or another application is NOT "
        "a request to shut down JEEV. "

        "Never infer a JEEV shutdown request from context. "

        "LANGUAGE RULE: Speak ONLY English or Tamil. "
        "If the user speaks English, respond in English. "
        "If the user speaks Tamil, respond in Tamil. "
        "If the user mixes English and Tamil, respond naturally "
        "using English and Tamil. Understand Tanglish (Tamil "
        "spoken or written using English letters). Never switch "
        "to Hindi, Telugu, Malayalam, Kannada, Bengali, or any "
        "other language."
    )

    try:
        prompt = PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()

        if prompt:
            return prompt + TOOL_ROUTING_RULES + JEEV_IDENTITY_OVERRIDE

    except Exception as e:
        print(
            "[JEEV] Warning: Could not load prompt.txt: "
            f"{e}"
        )

    return fallback_prompt + TOOL_ROUTING_RULES + JEEV_IDENTITY_OVERRIDE


# ============================================================
# MEMORY
# ============================================================

_last_memory_input = ""


def _update_memory_async(
    user_text: str,
    jeev_text: str,
) -> None:

    global _last_memory_input

    user_text = (
        user_text or ""
    ).strip()

    jeev_text = (
        jeev_text or ""
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
            jeev_text,
            api_key,
        ):
            return

        data = extract_memory(
            user_text,
            jeev_text,
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
            "Opens an installed Windows application. "
            "Use for desktop Windows applications. Do not use this tool for Gmail, WhatsApp, or Spotify; those have dedicated controllers."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Application name.",
                }
            },
            "required": ["app_name"],
        },
    },

    {
        "name": "web_search",
        "description": (
            "Searches the web for current information. Use for news, "
            "current events, places/location information, search, "
            "lookup, browsing, or research."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Search query.",
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
                },
                "message_text": {
                    "type": "STRING",
                },
                "platform": {
                    "type": "STRING",
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
            "on Windows. Use this tool for ALL WhatsApp actions. "
            "NEVER use browser_control for WhatsApp. "
            "NEVER open WhatsApp Web. "
            "Can open WhatsApp Desktop, open a contact chat, "
            "send a message, reply in the current chat, focus "
            "WhatsApp, and check WhatsApp status. "
            "Use search_contact or find_contact whenever the user asks to search/find a WhatsApp contact. "
            "Understand Tanglish commands such as 'WhatsApp-la Vishal search pannu'. "
            "If multiple contacts match the requested name, NEVER choose the first one. "
            "Ask the user to choose a numbered contact. Use contact_index for the chosen contact."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "open, open_chat, search_contact, find_contact, "
                        "send_message, reply, focus, status"
                    ),
                },
                "receiver": {
                    "type": "STRING",
                },
                "message_text": {
                    "type": "STRING",
                },
                "contact_index": {
                    "type": "INTEGER",
                    "description": (
                        "1-based WhatsApp contact number when multiple "
                        "matching contacts were presented."
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
                },
                "time": {
                    "type": "STRING",
                },
                "message": {
                    "type": "STRING",
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
                },
                "save": {
                    "type": "BOOLEAN",
                },
                "region": {
                    "type": "STRING",
                },
                "url": {
                    "type": "STRING",
                },
            },
        },
    },

    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {
                    "type": "STRING",
                },
                "text": {
                    "type": "STRING",
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
                },
                "description": {
                    "type": "STRING",
                },
                "value": {
                    "type": "STRING",
                },
            },
        },
    },

    {
        "name": "browser_control",
        "description": (
            "Controls the web browser including opening websites, searching, "
            "clicking, typing, scrolling and forms. Use this for Gmail "
            "website actions such as opening Gmail or the inbox."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                },
                "url": {
                    "type": "STRING",
                },
                "query": {
                    "type": "STRING",
                },
                "selector": {
                    "type": "STRING",
                },
                "text": {
                    "type": "STRING",
                },
                "description": {
                    "type": "STRING",
                },
                "direction": {
                    "type": "STRING",
                },
                "key": {
                    "type": "STRING",
                },
                "incognito": {
                    "type": "BOOLEAN",
                },
            },
            "required": ["action"],
        },
    },

    {
        "name": "file_controller",
        "description": (
            "Manages files/folders and Windows applications. Supports list, create, delete, move, copy, rename, read, write, find, disk usage, open_folder/open_file/open_app and close_app/close_window."
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
                "app_name": {"type": "STRING"},
                "application": {"type": "STRING"},
                "force": {"type": "BOOLEAN"},
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
            "Analyzes local files selected or uploaded for JEEV. Images are read with vision/OCR, including visible text in screenshots, photos and scanned pages. PDFs use native text extraction plus OCR for image-only pages. DOCX, spreadsheets, JSON, XML, text and code files can also be analyzed. Use action=extract_text to read text, action=summary to summarize, action=ask with a question for document Q&A, or action=analyze for general analysis. If file_path is omitted, use the selected file or active analyzer context. Do not use browser_control for local files."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {"type": "STRING"},
                "action": {"type": "STRING"},
                "instruction": {"type": "STRING"},
                "question": {"type": "STRING"},
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
        },
    },

    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down JEEV completely. "
            "ONLY call this when the user's latest command "
            "clearly and explicitly tells JEEV itself to "
            "shut down, exit, quit, or turn off."
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
                "category": {"type": "STRING"},
                "key": {"type": "STRING"},
                "value": {"type": "STRING"},
            },
            "required": [
                "category",
                "key",
                "value",
            ],
        },
    },

    {
        "name": "gmail_control",
        "description": "Dedicated Gmail controller. Use for Gmail setup, open, latest, search, read_search, select, current, generate_reply, reply, send, and close. Never substitute browser_control for Gmail.",
        "parameters": {"type":"OBJECT","properties":{"action":{"type":"STRING"},"query":{"type":"STRING"},"index":{"type":"INTEGER"}},"required":["action"]},
    },

    {
        "name": "spotify_control",
        "description": (
            "Controls the installed Spotify Desktop application on Windows. "
            "Use this tool for ALL Spotify actions. NEVER use browser_control "
            "for Spotify. To play a requested searched song, first use "
            "action=search or find, then use action=play_result/select_result "
            "with the chosen result. Do not stop after searching. Understand "
            "English and Tanglish commands."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "open, focus, search, find, play_result, select_result, "
                        "play, pause, next, previous, observe, inspect"
                    ),
                },
                "query": {"type": "STRING", "description": "Spotify search query."},
                "text": {"type": "STRING"},
                "name": {"type": "STRING"},
                "description": {"type": "STRING"},
                "index": {"type": "INTEGER", "description": "1-based result number."},
                "wait": {"type": "NUMBER"},
                "include_screenshot": {"type": "BOOLEAN"},
                "max_elements": {"type": "INTEGER"},
            },
            "required": ["action"],
        },
    },

    {
        "name": "media_control",
        "description": (
            "Controls system-wide Windows media playback."
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
# JEEV LIVE ENGINE
# ============================================================

class JeevLive:

    def __init__(self, ui: JarvisUI):

        self.ui = ui

        # ----------------------------------------------------
        # PERSONALITY (ISOLATED)
        # ----------------------------------------------------
        self.personality = None
        if SarcasmEngine is not None:
            try:
                self.personality = SarcasmEngine()
                print("[JEEV] 🎭 Personality layer loaded.")
            except Exception as e:
                print(
                    "[JEEV] ⚠️ Personality initialization failed; "
                    f"continuing normally: {e}"
                )

        self.session = None
        self.audio_in_queue = None
        self.out_queue = None

        self._loop = None

        # ----------------------------------------------------
        # SPEECH STATE
        # ----------------------------------------------------

        self._is_speaking = False
        self._speaking_lock = threading.Lock()

        # ----------------------------------------------------
        # AUDIO STATE
        # ----------------------------------------------------

        self._audio_stream = None

        self._audio_playing = False
        self._audio_state_lock = threading.Lock()

        self._audio_turn_active = False

        self._drain_task = None

        self._turn_counter = 0
        self._active_turn_id = 0

        # ----------------------------------------------------
        # SHUTDOWN
        # ----------------------------------------------------

        self._shutdown_requested = False
        self._closing = False

        # ----------------------------------------------------
        # SESSION
        # ----------------------------------------------------

        self._session_error = False
        self._online_logged = False

        # ----------------------------------------------------
        # TEXT
        # ----------------------------------------------------

        self._last_user_text = ""
        self._text_lock = threading.Lock()

        # ----------------------------------------------------
        # CONFIRMATION / ACTION STATE
        # ----------------------------------------------------
        # Only genuinely consequential actions use this gate.
        # Normal application open/close is deliberately NOT gated.
        self._pending_action = None
        self._pending_action_lock = threading.Lock()
        self._pending_action_ttl = 90.0

        # ----------------------------------------------------
        # MIC
        # ----------------------------------------------------

        self._mic = None
        self._microphone_task = None

        # ----------------------------------------------------
        # DEDICATED BLOCKING AUDIO I/O EXECUTORS
        # ----------------------------------------------------
        self._mic_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="JEEV-MicIO",
        )
        self._speaker_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="JEEV-SpeakerIO",
        )

        # ----------------------------------------------------
        # AUDIO WATCHDOG HEARTBEATS
        # ----------------------------------------------------
        self._mic_last_read = time.monotonic()
        self._speaker_last_write = time.monotonic()
        self._audio_sender_last_activity = time.monotonic()
        self._receiver_last_activity = time.monotonic()

        # One startup welcome per JEEV process.
        self._welcome_sent = False

        # ----------------------------------------------------
        # TASKS
        # ----------------------------------------------------

        self._core_tasks = []

        # ----------------------------------------------------
        # UI
        # ----------------------------------------------------

        self.ui.on_text_command = self._on_text_command


    # ========================================================
    # TEXT COMMAND
    # ========================================================

    async def _run_coding_agent_direct(self, text: str):
        """Run dev_agent directly for a clearly identified coding request.

        This path is intentionally isolated from _execute_tool(). It does not
        modify Gmail, Spotify, WhatsApp, browser, desktop, media, or any other
        existing tool routing.
        """
        if self._closing or self._shutdown_requested:
            return

        try:
            self.ui.set_state("THINKING")
        except Exception:
            pass

        print(f"[JEEV] 🧑‍💻 Coding request: {text}")
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: dev_agent(
                    parameters={
                        "action": "build",
                        "request": text,
                    },
                    player=self.ui,
                    speak=self.speak,
                ),
            )

            print(f"[JEEV] 🧑‍💻 Coding result: {result}")
            try:
                self.ui.write_log(f"CODE RESULT: {result}")
            except Exception:
                pass

            if isinstance(result, dict):
                if result.get("ok") is False:
                    message = (
                        "Coding task failed: "
                        f"{result.get('error', 'unknown error')}."
                    )
                else:
                    message = (
                        result.get("summary")
                        or result.get("message")
                        or "Coding task completed."
                    )
            else:
                message = str(result or "Coding task completed.")

            # Let Gemini speak the concise result using the normal session.
            self.speak(message)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[JEEV] ❌ Direct coding dispatch failed: {exc}")
            try:
                self.ui.write_log(f"CODE ERROR: {exc}")
            except Exception:
                pass
            self.speak(f"Coding task failed: {exc}")
        finally:
            try:
                if not self._shutdown_requested and not self._closing:
                    if not self.ui.muted and not self._is_speaking:
                        self.ui.set_state("LISTENING")
            except Exception:
                pass

    def _on_text_command(self, text: str):

        text = (text or "").strip()

        if not text:
            return

        if self._closing or self._shutdown_requested:
            return

        if not self._loop:
            print(
                "[JEEV] ⚠️ Event loop not ready."
            )
            return

        if not self.session:
            print(
                "[JEEV] ⚠️ Gemini session not ready."
            )
            return

        # ----------------------------------------------------
        # PERSONALITY TEXT HOOK
        # ----------------------------------------------------
        # Text commands can use an exact setup -> wait -> answer flow.
        # This does not touch voice/audio or tools.
        if self.personality is not None:
            try:
                if self.personality.is_waiting_for_joke_answer():
                    reaction = self.personality.handle_joke_answer(text)
                    if reaction:
                        print("[JEEV] 🎭 Joke answer handled locally.")
                        self.speak(reaction)
                        return

                if self.personality.joke_trigger(text):
                    setup = self.personality.start_joke()
                    print("[JEEV] 🎭 Kadi setup — waiting for user answer.")
                    self.speak(setup)
                    return
            except Exception as e:
                print(
                    "[JEEV] ⚠️ Personality text hook failed; "
                    f"sending command normally: {e}"
                )

        print(
            f"[JEEV] 📝 Sending text: {text}"
        )

        with self._text_lock:
            self._last_user_text = text

        # ONLY clear coding implementation requests bypass Gemini tool
        # selection. Gmail/Spotify/WhatsApp/etc. still follow the original
        # Gemini Live tool path below.
        if _is_coding_request(text):
            print("[JEEV] 🧑‍💻 Coding intent detected; using dev_agent.")
            future = asyncio.run_coroutine_threadsafe(
                self._run_coding_agent_direct(text),
                self._loop,
            )
            future.add_done_callback(self._consume_future_exception)
            return

        async def send_text():

            try:

                if self.session is None:
                    return

                await self.session.send_realtime_input(
                    text=text
                )

            except asyncio.CancelledError:
                raise

            except Exception as e:

                print(
                    "[JEEV] Text command error: "
                    f"{e}"
                )

        try:

            future = asyncio.run_coroutine_threadsafe(
                send_text(),
                self._loop,
            )

            future.add_done_callback(
                self._consume_future_exception
            )

        except (
            RuntimeError,
            RuntimeWarning,
        ) as e:

            print(
                "[JEEV] Text scheduling rejected: "
                f"{e}"
            )


    @staticmethod
    def _consume_future_exception(future):

        try:
            future.result()

        except (
            asyncio.CancelledError,
            RuntimeError,
        ):
            pass

        except Exception as e:

            print(
                "[JEEV] Async command error: "
                f"{e}"
            )


    # ========================================================
    # SPEAKING STATE
    # ========================================================

    def set_speaking(self, value: bool):

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

    def speak(self, text: str):

        text = (text or "").strip()

        if not text:
            return

        if (
            not self._loop
            or self._closing
            or self._shutdown_requested
        ):
            return

        if not self.session:
            return

        async def send_text():

            try:

                if self.session is None:
                    return

                try:
                    await self.session.send_realtime_input(audio_stream_end=True)
                except Exception:
                    pass

                await self.session.send_realtime_input(text=text)
                print(f"[JEEV] 📤 Text sent to Gemini: {text[:100]}")

            except asyncio.CancelledError:
                raise

            except Exception as e:

                print(
                    "[JEEV] Speak error: "
                    f"{e}"
                )

        try:

            future = asyncio.run_coroutine_threadsafe(
                send_text(),
                self._loop,
            )

            future.add_done_callback(
                self._consume_future_exception
            )

        except RuntimeError as e:

            print(
                "[JEEV] Speak scheduling rejected: "
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

    def _shutdown_was_explicitly_requested(self) -> bool:

        with self._text_lock:

            text = (
                self._last_user_text or ""
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
                and "off" in words
            ):
                return True

        return False


    # ========================================================
    # ACTION SAFETY / CONFIRMATION
    # ========================================================

    @staticmethod
    def _normalize_action(value) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9_\s-]", " ", text)
        text = re.sub(r"[\s-]+", "_", text)
        return text

    def _requires_confirmation(self, name: str, args: dict) -> bool:
        """Only WhatsApp sending and PC power actions are high-risk."""
        name = str(name or "").strip().lower()
        action = self._normalize_action(args.get("action", ""))

        if name in {"send_message", "whatsapp_control"}:
            if name == "send_message":
                return bool(
                    str(args.get("message_text", "") or "").strip()
                )
            return action in {
                "send",
                "send_message",
                "reply",
                "send_reply",
            }

        if name == "computer_settings":
            return action in {
                "shutdown",
                "shutdown_pc",
                "poweroff",
                "power_off",
                "restart",
                "reboot",
                "restart_system",
            }

        return False

    def _confirmation_key(self, name: str, args: dict) -> str:
        """Stable key so a model retry does not create a second prompt."""
        relevant = {
            "name": str(name or "").strip().lower(),
            "action": self._normalize_action(args.get("action", "")),
            "receiver": str(
                args.get("receiver", args.get("contact", "")) or ""
            ).strip().casefold(),
            "message_text": str(
                args.get("message_text", args.get("message", "")) or ""
            ).strip(),
            "platform": str(args.get("platform", "") or "").strip().lower(),
        }
        return json.dumps(relevant, sort_keys=True, ensure_ascii=False)

    def _confirmation_positive(self, text: str) -> bool:
        normalized = re.sub(
            r"[^a-z0-9\s]",
            " ",
            str(text or "").strip().lower(),
        )
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return False

        negatives = {
            "no", "nope", "cancel", "cancel it", "stop",
            "dont", "do not", "don't", "not now",
        }
        if normalized in negatives:
            return False

        positives = {
            "yes", "yeah", "yep", "yup", "sure", "surely",
            "okay", "ok", "go ahead", "do it", "send it",
            "confirm", "confirmed", "proceed", "please do",
        }
        return normalized in positives or normalized.startswith(
            ("yes ", "yeah ", "sure ", "okay ", "ok ", "go ahead ")
        )

    def _get_last_user_text(self) -> str:
        with self._text_lock:
            return str(self._last_user_text or "").strip()

    def _set_pending_action(self, name: str, args: dict) -> bool:
        key = self._confirmation_key(name, args)
        now = time.monotonic()
        with self._pending_action_lock:
            current = self._pending_action
            if current and now - current["created"] <= self._pending_action_ttl:
                if current["key"] == key:
                    return False
            self._pending_action = {
                "key": key,
                "name": name,
                "args": dict(args),
                "created": now,
            }
            return True

    def _consume_pending_action(self, name: str, args: dict) -> bool:
        key = self._confirmation_key(name, args)
        now = time.monotonic()
        with self._pending_action_lock:
            current = self._pending_action
            if not current:
                return False
            if now - current["created"] > self._pending_action_ttl:
                self._pending_action = None
                return False
            if current["key"] != key:
                return False
            self._pending_action = None
            return True

    def _cancel_pending_action(self) -> None:
        with self._pending_action_lock:
            self._pending_action = None

    def _confirmation_prompt(self, name: str, args: dict) -> str:
        if name == "whatsapp_control":
            receiver = str(
                args.get("receiver", args.get("contact", "")) or ""
            ).strip()
            message = str(
                args.get("message_text", args.get("message", "")) or ""
            ).strip()
            return (
                f"Sir, I have prepared a WhatsApp message to {receiver or 'the selected contact'}: "
                f'\"{message}\". Please say yes to send it, or no to cancel.'
            )

        if name == "send_message":
            receiver = str(args.get("receiver", "") or "").strip()
            message = str(args.get("message_text", "") or "").strip()
            return (
                f"Sir, I have prepared a message to {receiver or 'the selected contact'}: "
                f'\"{message}\". Please say yes to send it, or no to cancel.'
            )

        action = self._normalize_action(args.get("action", ""))
        if action in {"restart", "reboot", "restart_system"}:
            return "Sir, restarting the PC will close Windows. Please say yes to confirm, or no to cancel."
        return "Sir, shutting down the PC will close Windows. Please say yes to confirm, or no to cancel."

    # ========================================================
    # GEMINI CONFIG
    # ========================================================

    def _build_config(self):

        memory = load_memory()

        mem_str = format_memory_for_prompt(
            memory
        )

        sys_prompt = _load_system_prompt()

        language_rule = (
            "\n\n[LANGUAGE & VOICE RULE — STRICT]\n"
            "JEEV understands and speaks English, Tamil, and Tanglish. "
            "Tanglish means Tamil written in English letters and natural "
            "Tamil-English code switching. "
            "If the user speaks English, answer naturally in English. "
            "If the user speaks Tamil, answer naturally in Tamil. "
            "If the user speaks Tanglish or mixed Tamil-English, answer "
            "naturally in the same Tanglish or mixed style. "
            "Never switch to Hindi, Telugu, Malayalam, Kannada, Bengali, "
            "or another language unless explicitly asked for translation. "
            "Keep spoken answers concise and conversational.\n"
        )

        sys_prompt += language_rule

        # ----------------------------------------------------
        # PERSONALITY POLICY — CONVERSATION ONLY
        # ----------------------------------------------------
        personality_rule = """
[PERSONALITY & HUMOR — CONVERSATION ONLY]
JEEV may be warm, playful, sarcastic and funny during friendly chat.
Do not force humor into serious requests or real tool commands.

KADI JOKE PROTOCOL:
- When the user asks for a joke/kadi joke, give ONE setup/question.
- STOP after the setup and WAIT for the user's answer.
- Never immediately reveal your own punchline.
- If the user gives the correct punchline, celebrate and vibe with them.
- If the user gives a wrong answer, reveal the punchline and playfully mock the wrong answer.
- If the user says they do not know, reveal it and lightly tease them.
- Never answer your own joke in the same turn as the setup.

ROAST PROTOCOL:
- If the user explicitly asks to be roasted, bash them playfully.
- Make the roast specific to the current conversation when possible.
- Do not invent personal facts.
- Tanglish and Gen-Z humor are welcome when they match the user.
- Tamil Nadu cultural/meme humor and light non-partisan political satire may be used naturally.
- Keep it clearly comedic, not genuinely hateful or threatening.

MOST IMPORTANT: tools are authoritative. Never claim Spotify, WhatsApp, Gmail, browser, files, applications, or any other tool action happened unless the actual tool result says it succeeded. Personality must never change tool arguments or interfere with tool execution.
"""

        sys_prompt += personality_rule

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

        parts = [time_ctx]

        if mem_str:
            parts.append(mem_str)

        parts.append(sys_prompt)

        return types.LiveConnectConfig(

            response_modalities=[
                "AUDIO"
            ],

            output_audio_transcription=(
                types.AudioTranscriptionConfig(
                    language_codes=["en-US", "ta-IN"],
                )
            ),

            input_audio_transcription=(
                types.AudioTranscriptionConfig(
                    language_codes=["en-US", "ta-IN"],
                )
            ),

            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    prefix_padding_ms=80,
                    silence_duration_ms=450,
                )
            ),

            system_instruction="\n".join(parts),

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

                voice_config=types.VoiceConfig(

                    prebuilt_voice_config=(
                        types.PrebuiltVoiceConfig(
                            voice_name="Charon"
                        )
                    )
                )
            ),
        )


    # ========================================================
    # TOOL EXECUTION
    # ========================================================

    def _close_windows_app_verified(self, app_name):
        """Close a normal Windows application and verify it is actually gone."""
        target = str(app_name or "").strip()
        if not target:
            return {"ok": False, "verified": False, "error": "Application name is required."}
        norm = re.sub(r"[^a-z0-9]+", "", target.lower())
        protected = {"jeev", "python", "python312", "cmd", "powershell", "terminal", "windowsterminal"}
        if norm in protected or "jeev" in norm:
            return {"ok": False, "verified": False, "error": "I will not close JEEV or its terminal."}
        aliases = {
            "spotify": ["Spotify"],
            "whatsapp": ["WhatsApp.Root", "WhatsApp"],
            "whatsappdesktop": ["WhatsApp.Root", "WhatsApp"],
            "telegram": ["Telegram"],
            "discord": ["Discord"],
            "chrome": ["chrome"],
            "edge": ["msedge"],
            "microsoftedge": ["msedge"],
            "firefox": ["firefox"],
        }
        process_names = aliases.get(norm, [target])
        def find_matches():
            ps = "$items = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Id -and ($_.MainWindowTitle -or $_.ProcessName) } | ForEach-Object { [PSCustomObject]@{ PID=$_.Id; Name=$_.ProcessName; Title=$_.MainWindowTitle } }; $items | ConvertTo-Json -Compress"
            try:
                p = subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command",ps],capture_output=True,text=True,timeout=8)
                raw=(p.stdout or "").strip()
                if not raw: return []
                import json as _json
                data=_json.loads(raw)
                if isinstance(data,dict): data=[data]
                matches=[]
                for item in data:
                    name=str(item.get("Name") or "")
                    title=str(item.get("Title") or "")
                    lname=name.lower(); ltitle=title.lower()
                    hit=any(str(x).lower()==lname or str(x).lower() in ltitle for x in process_names)
                    if not hit:
                        hit=norm in re.sub(r"[^a-z0-9]+","",lname) or norm in re.sub(r"[^a-z0-9]+","",ltitle)
                    if hit and int(item.get("PID") or 0): matches.append(item)
                return matches
            except Exception as exc:
                print(f"[JEEV] Close-app discovery failed: {exc}")
                return []
        matches=find_matches()
        if not matches:
            return {"ok": True, "verified": True, "message": f"{target} is already closed."}
        pids=[]
        for item in matches:
            pid=int(item.get("PID") or 0)
            if pid and pid not in pids: pids.append(pid)
        print(f"[JEEV] Closing {target}: PIDs={pids}")
        for pid in pids:
            try:
                subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command",f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; if($p){{ $null=$p.CloseMainWindow() }}"],capture_output=True,text=True,timeout=5)
            except Exception: pass
        time.sleep(1.0)
        remaining=find_matches()
        if remaining:
            remaining_pids=[int(x.get("PID") or 0) for x in remaining if int(x.get("PID") or 0)]
            for pid in remaining_pids:
                try: subprocess.run(["taskkill","/PID",str(pid),"/T","/F"],capture_output=True,text=True,timeout=8)
                except Exception as exc: print(f"[JEEV] taskkill failed for PID {pid}: {exc}")
            time.sleep(1.0)
            remaining=find_matches()
        if remaining:
            return {"ok": False, "verified": False, "error": f"I attempted to close {target}, but Windows still reports it running."}
        return {"ok": True, "verified": True, "message": f"{target} is closed and verified."}

    async def _execute_tool(self, fc):

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

        # ----------------------------------------------------
        # CONSEQUENTIAL ACTION GATE
        # ----------------------------------------------------
        # Normal open/close application actions are intentionally allowed.
        # Only WhatsApp send/reply and PC shutdown/restart require one
        # explicit confirmation. The pending state survives a Gemini tool
        # retry, so the model cannot make the confirmation loop forever.
        if self._requires_confirmation(name, args):
            last_user_text = self._get_last_user_text()

            if self._confirmation_positive(last_user_text):
                if self._consume_pending_action(name, args):
                    print(
                        "[JEEV] 🛡️ Confirmation accepted; executing "
                        f"{name}."
                    )
                else:
                    # A direct explicit request can arrive without a prior
                    # tool retry. Treat the current positive answer only as
                    # confirmation when an identical pending action exists.
                    print(
                        "[JEEV] 🛡️ No matching pending action; "
                        "refusing consequential action."
                    )
                    try:
                        self.ui.write_log(
                            "SECURITY: No matching pending action."
                        )
                    except Exception:
                        pass
                    return types.FunctionResponse(
                        id=fc.id,
                        name=name,
                        response={
                            "result": "No matching confirmed action exists. Do not execute this action.",
                            "blocked": True,
                        },
                    )
            else:
                created = self._set_pending_action(name, args)
                if created:
                    prompt = self._confirmation_prompt(name, args)
                    print(
                        "[JEEV] 🛡️ Confirmation required for "
                        f"{name}."
                    )
                    try:
                        self.ui.write_log(
                            "SECURITY: Confirmation requested."
                        )
                    except Exception:
                        pass
                    self.speak(prompt)
                else:
                    print(
                        "[JEEV] 🛡️ Confirmation already pending; "
                        "not asking again."
                    )

                return types.FunctionResponse(
                    id=fc.id,
                    name=name,
                    response={
                        "result": (
                            "Confirmation is required. The user has been asked once. "
                            "Do not repeat the action or ask for another confirmation "
                            "until the user clearly answers yes or no."
                        ),
                        "confirmation_required": True,
                        "blocked": True,
                    },
                )

        try:
            self.ui.set_state("THINKING")
        except Exception:
            pass

        # ----------------------------------------------------
        # SAVE MEMORY
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # JEEV SHUTDOWN
        # ----------------------------------------------------

        if name == "shutdown_jarvis":

            if not self._shutdown_was_explicitly_requested():

                print(
                    "[JEEV] 🛡️ "
                    "Blocked unauthorized shutdown."
                )

                try:
                    self.ui.write_log(
                        "SECURITY: Unauthorized shutdown blocked."
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
            self._closing = True

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

            # Do not call os._exit immediately.
            # Let the asyncio engine close its resources first.

            self.speak(
                "Goodbye, sir."
            )

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

            # ------------------------------------------------
            # OPEN APP
            # ------------------------------------------------

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

            # ------------------------------------------------
            # WEATHER
            # ------------------------------------------------

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

            # ------------------------------------------------
            # BROWSER
            # ------------------------------------------------

            elif name == "browser_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: browser_control(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = r or "Done."

            # ------------------------------------------------
            # FILE CONTROLLER
            # ------------------------------------------------

            elif name == "file_controller":

                r = await loop.run_in_executor(
                    None,
                    lambda: file_controller(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = r or "Done."

            elif name == "gmail_control":

                r = await loop.run_in_executor(None, lambda: gmail_control(args))
                result = r or "Gmail action completed."

            # ------------------------------------------------
            # SEND MESSAGE
            # ------------------------------------------------

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

            # ------------------------------------------------
            # WHATSAPP DESKTOP
            # ------------------------------------------------

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

            # ------------------------------------------------
            # REMINDER
            # ------------------------------------------------

            elif name == "reminder":

                r = await loop.run_in_executor(
                    None,
                    lambda: reminder(
                        parameters=args,
                        response=None,
                        player=self.ui,
                    ),
                )

                result = r or "Reminder set."

            # ------------------------------------------------
            # YOUTUBE
            # ------------------------------------------------

            elif name == "youtube_video":

                r = await loop.run_in_executor(
                    None,
                    lambda: youtube_video(
                        parameters=args,
                        response=None,
                        player=self.ui,
                    ),
                )

                result = r or "Done."

            # ------------------------------------------------
            # FILE PROCESSOR
            # ------------------------------------------------

            elif name == "file_processor":

                # main.py owns routing; analyser/ owns local-file understanding.
                if (
                    not args.get("file_path")
                    and getattr(self.ui, "current_file", None)
                ):
                    args["file_path"] = self.ui.current_file

                r = await loop.run_in_executor(
                    None,
                    lambda: analyze_file(
                        parameters=args,
                        player=self.ui,
                        speak=self.speak,
                    ),
                )

                result = r or "The analyzer returned no result."

            # ------------------------------------------------
            # SCREEN PROCESSOR
            # ------------------------------------------------

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

            # ------------------------------------------------
            # COMPUTER SETTINGS
            # ------------------------------------------------

            elif name == "computer_settings":

                action = str(args.get("action", "")).strip().lower()
                if action in {"close_app", "close"}:
                    app_name = (
                        args.get("app_name")
                        or args.get("value")
                        or args.get("application")
                        or args.get("name")
                        or ""
                    )
                    result = await loop.run_in_executor(
                        None,
                        lambda: self._close_windows_app_verified(app_name),
                    )
                else:
                    r = await loop.run_in_executor(
                        None,
                        lambda: computer_settings(
                            parameters=args,
                            response=None,
                            player=self.ui,
                        ),
                    )
                    result = r if r else {"ok": False, "verified": False, "error": "Computer settings returned no result."}

            # ------------------------------------------------
            # DESKTOP
            # ------------------------------------------------

            elif name == "desktop_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: desktop_control(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = r or "Done."

            # ------------------------------------------------
            # CODE HELPER
            # ------------------------------------------------

            elif name == "code_helper":

                r = await loop.run_in_executor(
                    None,
                    lambda: code_helper(
                        parameters=args,
                        player=self.ui,
                        speak=self.speak,
                    ),
                )

                result = r or "Done."

            # ------------------------------------------------
            # DEV AGENT
            # ------------------------------------------------

            elif name == "dev_agent":

                r = await loop.run_in_executor(
                    None,
                    lambda: dev_agent(
                        parameters=args,
                        player=self.ui,
                        speak=self.speak,
                    ),
                )

                result = r or "Done."

            # ------------------------------------------------
            # AGENT TASK
            # ------------------------------------------------

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

            # ------------------------------------------------
            # WEB SEARCH
            # ------------------------------------------------

            elif name == "web_search":

                r = await loop.run_in_executor(
                    None,
                    lambda: web_search_action(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = r or "Done."

            # ------------------------------------------------
            # COMPUTER CONTROL
            # ------------------------------------------------

            elif name == "computer_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: computer_control(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = r or "Done."

            # ------------------------------------------------
            # SPOTIFY DESKTOP
            # ------------------------------------------------

            elif name == "spotify_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: spotify_control(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = r or "Spotify action completed."

            # ------------------------------------------------
            # MEDIA CONTROL
            # ------------------------------------------------

            elif name == "media_control":

                r = await loop.run_in_executor(
                    None,
                    lambda: media_control(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = r or "Done."

            # ------------------------------------------------
            # GAME UPDATER
            # ------------------------------------------------

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

                    result = r or "Done."

            # ------------------------------------------------
            # FLIGHT FINDER
            # ------------------------------------------------

            elif name == "flight_finder":

                r = await loop.run_in_executor(
                    None,
                    lambda: flight_finder(
                        parameters=args,
                        player=self.ui,
                    ),
                )

                result = r or "Done."

            # ------------------------------------------------
            # UNKNOWN
            # ------------------------------------------------

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

            if (
                not self._closing
                and
                not self.ui.muted
            ):

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
    # SEND AUDIO TO GEMINI
    # ========================================================

    async def _send_realtime_audio(self):

        print(
            "[JEEV] 🎤 Audio sender started"
        )

        while (
            not self._shutdown_requested
            and
            not self._closing
        ):

            try:

                audio_bytes = (
                    await self.out_queue.get()
                )

                if audio_bytes is None:
                    break

                if not audio_bytes:
                    continue

                self._audio_sender_last_activity = time.monotonic()

                session = self.session

                if session is None:
                    continue

                try:

                    await session.send_realtime_input(
                        audio=types.Blob(
                            data=audio_bytes,
                            mime_type=(
                                "audio/pcm;rate=16000"
                            ),
                        )
                    )

                except asyncio.CancelledError:
                    raise

                except Exception as e:

                    if self._closing:
                        break

                    error_text = str(e).lower()

                    # A dead Gemini Live session must stop the sender and
                    # hand control back to the session watchdog.  Retrying
                    # send_realtime_input on the same dead WebSocket causes
                    # the repeated "keepalive ping timeout" spam seen in
                    # the original implementation.
                    disconnect_markers = (
                        "1006",
                        "1011",
                        "abnormal closure",
                        "keepalive ping timeout",
                        "connectionclosed",
                        "connection closed",
                        "no close frame",
                    )

                    if any(marker in error_text for marker in disconnect_markers):
                        print(
                            "[JEEV] 🔄 Gemini audio session is closed; "
                            "requesting reconnect."
                        )
                        self._session_error = True
                        break

                    print(
                        "[JEEV] ⚠️ "
                        f"Audio send error: {e}"
                    )

                    await asyncio.sleep(
                        0.05
                    )

            except asyncio.CancelledError:
                break

            except Exception as e:

                if not self._closing:

                    print(
                        "[JEEV] ⚠️ "
                        f"Audio sender error: {e}"
                    )

                    await asyncio.sleep(
                        0.05
                    )

        print(
            "[JEEV] 🎤 Audio sender stopped"
        )


    # ========================================================
    # MICROPHONE LISTENER
    # ========================================================

    async def _listen_audio(self):

        print(
            "[JEEV] 🎤 Starting microphone controller..."
        )

        mic = JeevMicrophone(
            device=INPUT_DEVICE
        )

        self._mic = mic

        try:

            if not mic.start():

                raise RuntimeError(
                    "JEEV microphone controller "
                    "could not be started."
                )

            print(
                "[JEEV] 🎤 Microphone is LIVE."
            )

            print(
                "[JEEV] 🎤 Backend: "
                "Windows WDM-KS"
            )

            print(
                "[JEEV] 🎤 Device: "
                f"{mic.device}"
            )

            print(
                "[JEEV] 🎤 Hardware: "
                f"{MIC_SAMPLE_RATE} Hz"
            )

            print(
                "[JEEV] 🎤 Gemini input: "
                f"{SEND_SAMPLE_RATE} Hz mono PCM16"
            )

            while (
                not self._shutdown_requested
                and
                not self._closing
            ):

                try:

                    # JeevMicrophone already converts the
                    # verified 44.1 kHz WDM-KS input to
                    # 16 kHz mono PCM16.

                    loop = asyncio.get_running_loop()
                    audio_bytes = await loop.run_in_executor(
                        self._mic_executor,
                        mic.read,
                        0.10,
                    )
                    self._mic_last_read = time.monotonic()

                except asyncio.CancelledError:
                    raise

                except RuntimeError as e:

                    if self._closing:
                        break

                    print(
                        "[JEEV] ⚠️ "
                        f"Microphone read error: {e}"
                    )

                    await asyncio.sleep(
                        0.05
                    )

                    continue

                except Exception as e:

                    if self._closing:
                        break

                    print(
                        "[JEEV] ⚠️ "
                        f"Microphone read error: {e}"
                    )

                    await asyncio.sleep(
                        0.05
                    )

                    continue

                if not audio_bytes:
                    continue

                # ------------------------------------------------
                # Prevent JEEV hearing itself only while actual speaker
                # hardware is actively playing audio. Do NOT use the
                # general _is_speaking flag here: that flag can remain
                # true during transcription/tool handling even when the
                # speaker is silent, which previously made JEEV become
                # deaf after a couple of commands.
                # ------------------------------------------------

                with self._audio_state_lock:
                    audio_playing = bool(self._audio_playing)

                if audio_playing:
                    continue

                try:

                    if self.ui.muted:
                        continue

                except Exception:
                    continue

                self._queue_microphone_audio(
                    audio_bytes
                )

        except asyncio.CancelledError:
            raise

        except Exception as e:

            if not self._closing:

                print(
                    "[JEEV] ❌ "
                    f"Microphone controller error: {e}"
                )

                traceback.print_exc()

            raise

        finally:

            print(
                "[JEEV] 🎤 "
                "Stopping microphone controller..."
            )

            try:
                mic.stop()
            except Exception:
                pass

            self._mic = None

            print(
                "[JEEV] 🎤 "
                "Microphone controller stopped."
            )


    # ========================================================
    # QUEUE MICROPHONE AUDIO
    # ========================================================

    def _queue_microphone_audio(
        self,
        audio_bytes,
    ):

        queue = self.out_queue

        if queue is None:
            return

        if not audio_bytes:
            return

        if (
            self._closing
            or
            self._shutdown_requested
        ):
            return

        try:

            # Keep latency low.
            #
            # If Gemini is temporarily slower than the
            # microphone, dropping the newest block is
            # preferable to allowing seconds of stale
            # microphone audio to accumulate.

            loop = self._loop
            if loop is None or loop.is_closed():
                return

            def _put():
                try:
                    if not queue.full():
                        queue.put_nowait(audio_bytes)
                except asyncio.QueueFull:
                    pass
                except Exception as exc:
                    if not self._closing:
                        print(f"[JEEV] Microphone queue error: {exc}")

            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                _put()
            else:
                loop.call_soon_threadsafe(_put)

        except asyncio.QueueFull:
            pass

        except RuntimeError:
            # Event loop already shutting down.
            pass

        except Exception as e:

            if not self._closing:

                print(
                    "[JEEV] "
                    f"Microphone queue error: {e}"
                )


    # ========================================================
    # CLEAR GEMINI AUDIO QUEUE
    # ========================================================

    def _clear_audio_queue(self):

        queue = self.audio_in_queue

        if queue is None:
            return

        cleared = 0

        while True:

            try:

                queue.get_nowait()

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

            await asyncio.sleep(
                0.08
            )

            stable_empty_count = 0

            while (
                not self._shutdown_requested
                and
                not self._closing
            ):

                if (
                    turn_id
                    !=
                    self._active_turn_id
                ):
                    return

                queue = self.audio_in_queue

                queue_empty = (
                    queue is None
                    or queue.empty()
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

            await asyncio.sleep(
                0.12
            )

            if (
                turn_id
                ==
                self._active_turn_id
                and
                not self._closing
            ):

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

            if not self._closing:

                print(
                    "[JEEV] ⚠️ "
                    f"Audio drain error: {e}"
                )


    # ========================================================
    # START AUDIO DRAIN
    # ========================================================

    def _start_audio_drain(self):

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
    # RECEIVE GEMINI EVENTS
    # ========================================================

    async def _receive_audio(self):

        print(
            "[JEEV] 👂 "
            "Gemini receiver started"
        )

        input_text_buffer = []
        output_text_buffer = []
        response_count = 0

        try:

            while (
                not self._shutdown_requested
                and
                not self._closing
            ):

                print(
                    "[JEEV] 👂 "
                    "Waiting for next turn..."
                )

                try:

                    async for response in (
                        self.session.receive()
                    ):

                        if self._closing:
                            break

                        self._receiver_last_activity = time.monotonic()
                        response_count += 1
                        if response_count % 50 == 0:
                            print(f"[JEEV] 👂 Gemini events received: {response_count}")

                        server_content = (
                            response.server_content
                        )

                        # ------------------------------------------------
                        # SERVER CONTENT
                        # ------------------------------------------------

                        if server_content:

                            # --------------------------------------------
                            # INTERRUPTION
                            # --------------------------------------------

                            if getattr(
                                server_content,
                                "interrupted",
                                False,
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

                            # --------------------------------------------
                            # MODEL AUDIO
                            # --------------------------------------------

                            model_turn = getattr(
                                server_content,
                                "model_turn",
                                None,
                            )

                            if model_turn:

                                for part in (
                                    model_turn.parts
                                ):

                                    inline_data = getattr(
                                        part,
                                        "inline_data",
                                        None,
                                    )

                                    if (
                                        inline_data
                                        and
                                        inline_data.data
                                    ):

                                        audio_data = (
                                            inline_data.data
                                        )

                                        queue = (
                                            self.audio_in_queue
                                        )

                                        if queue:

                                            try:

                                                await queue.put(
                                                    audio_data
                                                )

                                                self._audio_turn_active = True

                                                self.set_speaking(
                                                    True
                                                )

                                            except (
                                                asyncio.CancelledError
                                            ):
                                                raise

                                            except Exception as e:

                                                print(
                                                    "[JEEV] "
                                                    "Audio queue error: "
                                                    f"{e}"
                                                )

                            # --------------------------------------------
                            # JEEV OUTPUT TRANSCRIPTION
                            # --------------------------------------------

                            output_transcription = getattr(
                                server_content,
                                "output_transcription",
                                None,
                            )

                            if (
                                output_transcription
                                and
                                getattr(
                                    output_transcription,
                                    "text",
                                    None,
                                )
                            ):

                                text = (
                                    output_transcription.text
                                    .strip()
                                )

                                if text:

                                    output_text_buffer.append(
                                        text
                                    )

                                    self.set_speaking(
                                        True
                                    )

                            # --------------------------------------------
                            # USER INPUT TRANSCRIPTION
                            # --------------------------------------------

                            input_transcription = getattr(
                                server_content,
                                "input_transcription",
                                None,
                            )

                            if (
                                input_transcription
                                and
                                getattr(
                                    input_transcription,
                                    "text",
                                    None,
                                )
                            ):

                                text = (
                                    input_transcription.text
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

                            # --------------------------------------------
                            # GENERATION COMPLETE
                            # --------------------------------------------

                            if getattr(
                                server_content,
                                "generation_complete",
                                False,
                            ):

                                print(
                                    "[JEEV] 🧠 "
                                    "Generation complete."
                                )

                            # --------------------------------------------
                            # TURN COMPLETE
                            # --------------------------------------------

                            if getattr(
                                server_content,
                                "turn_complete",
                                False,
                            ):

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
                                        target=(
                                            _update_memory_async
                                        ),
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

                                self._start_audio_drain()

                        # ------------------------------------------------
                        # TOOL CALL
                        # ------------------------------------------------

                        tool_call = getattr(
                            response,
                            "tool_call",
                            None,
                        )

                        if tool_call:

                            function_responses = []

                            for function_call in (
                                tool_call.function_calls
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

                                    # Tool execution must never leave the HUD in
                                    # THINKING permanently. Audio receiver/sender
                                    # remain alive; this is only a UI state update.
                                    if not self._shutdown_requested and not self._closing:
                                        try:
                                            if not self.ui.muted and not self._is_speaking:
                                                self.ui.set_state("LISTENING")
                                        except Exception:
                                            pass

                                except asyncio.CancelledError:
                                    raise

                                except Exception as e:

                                    print(
                                        "[JEEV] ❌ "
                                        "Tool response error: "
                                        f"{e}"
                                    )

                                    raise

                    if (
                        self._shutdown_requested
                        or
                        self._closing
                    ):
                        break

                    # Receive iterator ended without a
                    # reported connection error.
                    await asyncio.sleep(
                        0.05
                    )

                except asyncio.CancelledError:
                    raise

                except Exception as e:

                    if self._closing:
                        break

                    print(
                        "[JEEV] ⚠️ "
                        f"Receiver turn error: {e}"
                    )

                    error_text = str(e).lower()

                    # google-genai can surface a WebSocket keepalive failure
                    # as APIError 1006 instead of websockets'
                    # ConnectionClosedError.  The old code missed that form,
                    # so _receive_audio stayed alive on a dead session while
                    # the microphone sender repeatedly attempted to write to
                    # the same dead socket.
                    disconnect_markers = (
                        "1006",
                        "1011",
                        "abnormal closure",
                        "keepalive ping timeout",
                        "connectionclosed",
                        "connection closed",
                        "no close frame",
                        "internal error",
                    )

                    if any(marker in error_text for marker in disconnect_markers):

                        print(
                            "[JEEV] 🔄 "
                            "Gemini connection appears closed; reconnecting."
                        )

                        self._session_error = True

                        break

                    traceback.print_exc()

                    await asyncio.sleep(
                        0.5
                    )

        except asyncio.CancelledError:
            raise

        except Exception as e:

            if not self._closing:

                print(
                    "[JEEV] ❌ "
                    f"Receiver error: {e}"
                )

                traceback.print_exc()

            raise

        finally:

            with self._audio_state_lock:

                still_playing = (
                    self._audio_playing
                )

            if not still_playing:

                self._audio_turn_active = False

                if not self._closing:

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

    async def _play_audio(self):

        print(
            "[JEEV] 🔊 "
            "Starting audio output..."
        )

        stream = None

        try:

            # ------------------------------------------------
            # Verify output endpoint before opening.
            # ------------------------------------------------

            try:

                info = sd.query_devices() if OUTPUT_DEVICE is None else sd.query_devices(OUTPUT_DEVICE)

                print(
                    "[JEEV] 🔊 "
                    "Output device:"
                )

                print(
                    f"       Index: {OUTPUT_DEVICE}"
                )

                print(
                    f"       Name: "
                    f"{info['name']}"
                )

                print(
                    f"       Host API: "
                    f"{sd.query_hostapis(info['hostapi'])['name']}"
                )

                print(
                    f"       Channels: "
                    f"{info['max_output_channels']}"
                )

            except Exception as e:

                print(
                    "[JEEV] ⚠️ "
                    f"Could not inspect output device: {e}"
                )

            # ------------------------------------------------
            # Validate output settings.
            # ------------------------------------------------

            try:

                sd.check_output_settings(
                    device=OUTPUT_DEVICE,
                    samplerate=OUTPUT_SAMPLE_RATE,
                    channels=OUTPUT_CHANNELS,
                    dtype="int16",
                )

            except Exception as e:

                raise RuntimeError(
                    "Verified speaker endpoint could not "
                    f"open at {OUTPUT_SAMPLE_RATE} Hz: {e}"
                )

            # ------------------------------------------------
            # Open speaker stream.
            # ------------------------------------------------

            stream = sd.RawOutputStream(

                device=OUTPUT_DEVICE,

                samplerate=OUTPUT_SAMPLE_RATE,

                channels=OUTPUT_CHANNELS,

                dtype="int16",

                blocksize=0,
                latency="high",
            )

            stream.start()

            self._audio_stream = stream

            print(
                "[JEEV] 🔊 "
                f"Audio output LIVE: "
                f"{OUTPUT_SAMPLE_RATE} Hz"
            )

            print(
                "[JEEV] 🔊 "
                "Gemini 24 kHz → Windows 48 kHz"
            )

            # ------------------------------------------------
            # PLAYBACK LOOP
            # ------------------------------------------------

            while (
                not self._shutdown_requested
                and
                not self._closing
            ):

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

                with self._audio_state_lock:

                    self._audio_playing = True

                self.set_speaking(
                    True
                )

                try:

                    # Gemini Live native audio:
                    #
                    # 24 kHz
                    # signed 16-bit
                    # mono PCM
                    #
                    # Speaker:
                    #
                    # 48 kHz
                    #
                    # Exact 2x sample duplication.

                    pcm24 = np.frombuffer(
                        bytes(audio_chunk),
                        dtype=np.int16,
                    )

                    if pcm24.size == 0:
                        continue

                    pcm48 = np.repeat(
                        pcm24,
                        2,
                    )

                    # Airdopes device 4 is a stereo endpoint. Duplicate
                    # Gemini's mono 24 kHz -> 48 kHz samples into L/R.
                    stereo48 = np.column_stack((
                        pcm48,
                        pcm48,
                    )).ravel()

                    audio_output = (
                        stereo48.astype(
                            np.int16,
                            copy=False,
                        ).tobytes()
                    )

                    if not audio_output:
                        continue

                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        self._speaker_executor,
                        stream.write,
                        audio_output,
                    )
                    self._speaker_last_write = time.monotonic()

                except asyncio.CancelledError:
                    raise

                except Exception as e:

                    if not self._closing:

                        print(
                            "[JEEV] ⚠️ "
                            f"Playback error: {e}"
                        )

                finally:

                    with self._audio_state_lock:

                        self._audio_playing = False

        except asyncio.CancelledError:
            raise

        except Exception as e:

            if not self._closing:

                print(
                    "[JEEV] ❌ "
                    f"Audio output error: {e}"
                )

                traceback.print_exc()

        finally:

            with self._audio_state_lock:

                self._audio_playing = False

            # Never leave the global speaking flag latched after the
            # playback worker exits. A latched flag suppresses the mic.
            try:
                self.set_speaking(False)
            except Exception:
                pass

            self._audio_stream = None

            if stream:

                try:

                    # Allow final hardware buffer.
                    await asyncio.sleep(
                        0.10
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
    # STOP AUDIO RESOURCES
    # ========================================================

    async def _stop_audio_resources(self):

        print(
            "[JEEV] 🧹 "
            "Stopping audio resources..."
        )

        self._closing = True

        # ----------------------------------------------------
        # Stop microphone first.
        # ----------------------------------------------------

        mic = self._mic

        if mic:

            try:
                mic.stop()
            except Exception:
                pass

        # ----------------------------------------------------
        # Cancel drain.
        # ----------------------------------------------------

        if (
            self._drain_task
            and
            not self._drain_task.done()
        ):

            self._drain_task.cancel()

            try:
                await self._drain_task
            except BaseException:
                pass

        # ----------------------------------------------------
        # Stop output stream.
        # ----------------------------------------------------

        stream = self._audio_stream

        if stream:

            try:
                stream.stop()
            except Exception:
                pass

            try:
                stream.close()
            except Exception:
                pass

            self._audio_stream = None

        print(
            "[JEEV] 🧹 "
            "Audio resources stopped."
        )


    # ========================================================
    # RUN JEEV
    # ========================================================

    async def run(self):

        api_key = _get_api_key()

        print(
            "[JEEV] 🔑 "
            "Gemini API key loaded."
        )

        print(
            "[JEEV] 🎤 "
            f"Input device: {INPUT_DEVICE}"
        )

        print(
            "[JEEV] 🔊 "
            f"Output device: {OUTPUT_DEVICE}"
        )

        client = genai.Client(
            api_key=api_key,
            http_options={
                "api_version": "v1beta"
            },
        )

        while (
            not self._shutdown_requested
            and
            not self._closing
        ):

            self._session_error = False

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

                async with client.aio.live.connect(
                    model=LIVE_MODEL,
                    config=config,
                ) as session:

                    self.session = session

                    self._loop = (
                        asyncio.get_running_loop()
                    )

                    # ------------------------------------------------
                    # Fresh queues for every Gemini session.
                    # ------------------------------------------------

                    self.audio_in_queue = (
                        asyncio.Queue(
                            maxsize=300
                        )
                    )

                    self.out_queue = (
                        asyncio.Queue(
                            maxsize=80
                        )
                    )

                    self._audio_turn_active = False

                    # A confirmation must never survive a broken/reconnected
                    # Gemini session. This prevents stale actions from firing.
                    self._cancel_pending_action()

                    now_audio = time.monotonic()
                    self._mic_last_read = now_audio
                    self._speaker_last_write = now_audio
                    self._audio_sender_last_activity = now_audio
                    self._receiver_last_activity = now_audio

                    self._turn_counter = 0
                    self._active_turn_id = 0

                    self._closing = False

                    print(
                        "[JEEV] ✅ "
                        "Gemini Live connected."
                    )

                    print(
                        "[JEEV] 🎤 "
                        f"Microphone device: {INPUT_DEVICE}"
                    )

                    print(
                        "[JEEV] 🔊 "
                        + (
                            "Speaker: Windows default output"
                            if OUTPUT_DEVICE is None
                            else f"Speaker device: {OUTPUT_DEVICE}"
                        )
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

                    # ------------------------------------------------
                    # PROACTIVE STARTUP WELCOME
                    # ------------------------------------------------
                    if not self._welcome_sent:
                        try:
                            await self.session.send_realtime_input(
                                text=(
                                    "[SYSTEM STARTUP EVENT] "
                                    "JEEV has just started. Give a brief "
                                    "warm welcome in natural English. "
                                    "Mention that you also understand Tamil "
                                    "and Tanglish. Do not ask a question "
                                    "and do not call tools."
                                )
                            )
                            self._welcome_sent = True
                            print(
                                "[JEEV] 👋 Startup welcome requested."
                            )
                        except Exception as e:
                            print(
                                "[JEEV] ⚠️ Welcome failed; "
                                f"continuing normally: {e}"
                            )

                    # ------------------------------------------------
                    # Start core tasks.
                    # ------------------------------------------------

                    audio_sender_task = (
                        asyncio.create_task(
                            self._send_realtime_audio(),
                            name="JEEV-AudioSender",
                        )
                    )

                    microphone_task = (
                        asyncio.create_task(
                            self._listen_audio(),
                            name="JEEV-Microphone",
                        )
                    )

                    receiver_task = (
                        asyncio.create_task(
                            self._receive_audio(),
                            name="JEEV-GeminiReceiver",
                        )
                    )

                    audio_player_task = (
                        asyncio.create_task(
                            self._play_audio(),
                            name="JEEV-AudioPlayer",
                        )
                    )

                    task_map = {
                        "audio_sender": audio_sender_task,
                        "microphone": microphone_task,
                        "receiver": receiver_task,
                        "audio_player": audio_player_task,
                    }

                    self._core_tasks = list(task_map.values())

                    # ------------------------------------------------
                    # SELF-HEALING AUDIO / RECEIVER WATCHDOG
                    # ------------------------------------------------
                    while (
                        not self._shutdown_requested
                        and not self._session_error
                        and not self._closing
                    ):
                        await asyncio.sleep(0.25)
                        now_mono = time.monotonic()

                        for worker_name, task in list(task_map.items()):
                            if not task.done():
                                continue

                            try:
                                exc = task.exception()
                            except asyncio.CancelledError:
                                exc = None

                            # Only Gemini's receiver is session-critical.
                            if worker_name == "receiver":
                                if exc:
                                    print(
                                        "[JEEV] ⚠️ Gemini receiver failed: "
                                        f"{exc}"
                                    )
                                    traceback.print_exception(
                                        type(exc),
                                        exc,
                                        exc.__traceback__,
                                    )
                                else:
                                    print(
                                        "[JEEV] ⚠️ Gemini receiver ended."
                                    )
                                if not self._shutdown_requested:
                                    self._session_error = True
                                break

                            if exc:
                                print(
                                    "[JEEV] ⚠️ "
                                    f"{worker_name} worker failed: {exc}"
                                )
                                traceback.print_exception(
                                    type(exc),
                                    exc,
                                    exc.__traceback__,
                                )
                            else:
                                print(
                                    "[JEEV] ⚠️ "
                                    f"{worker_name} worker stopped; "
                                    "restarting without reconnecting Gemini."
                                )

                            if (
                                self._shutdown_requested
                                or self._closing
                                or self.session is None
                            ):
                                continue

                            try:
                                if worker_name == "audio_sender":
                                    replacement = asyncio.create_task(
                                        self._send_realtime_audio(),
                                        name="JEEV-AudioSender",
                                    )
                                elif worker_name == "microphone":
                                    replacement = asyncio.create_task(
                                        self._listen_audio(),
                                        name="JEEV-Microphone",
                                    )
                                elif worker_name == "audio_player":
                                    replacement = asyncio.create_task(
                                        self._play_audio(),
                                        name="JEEV-AudioPlayer",
                                    )
                                else:
                                    continue

                                task_map[worker_name] = replacement
                                print(
                                    "[JEEV] ♻️ "
                                    f"{worker_name} worker restarted."
                                )
                            except Exception as restart_error:
                                print(
                                    "[JEEV] ⚠️ Could not restart "
                                    f"{worker_name}: {restart_error}"
                                )

                        # IMPORTANT: Do not recycle the microphone based on a
                        # wall-clock heartbeat. PortAudio/WDM-KS can legitimately
                        # block during device transitions, speech playback, or a
                        # Windows audio-device change. Killing the microphone task
                        # here was the cause of JEEV becoming deaf after a command.
                        # The microphone task now restarts only if it actually exits
                        # or raises an exception (handled above).

                        # Do not recycle the speaker merely because it has not
                        # written a sample recently. A quiet turn is normal. The
                        # audio-player task is restarted only when it actually
                        # terminates or raises an exception.


                        self._core_tasks = list(task_map.values())

                    # ------------------------------------------------
                    # SESSION CLEANUP
                    # ------------------------------------------------

                    print(
                        "[JEEV] 🧹 "
                        "Cleaning up Gemini session..."
                    )

                    # First stop microphone so no new
                    # audio enters the queue.

                    if self._mic:

                        try:
                            self._mic.stop()
                        except Exception:
                            pass

                    # Cancel the current core tasks.
                    cleanup_tasks = list(task_map.values()) if "task_map" in locals() else list(self._core_tasks)

                    for task in cleanup_tasks:
                        if not task.done():
                            task.cancel()

                    if cleanup_tasks:
                        await asyncio.gather(
                            *cleanup_tasks,
                            return_exceptions=True,
                        )

                    # Drain task.

                    if self._drain_task:

                        if (
                            not self._drain_task.done()
                        ):

                            self._drain_task.cancel()

                        await asyncio.gather(
                            self._drain_task,
                            return_exceptions=True,
                        )

                        self._drain_task = None

                    # Explicitly stop output.

                    stream = self._audio_stream

                    if stream:

                        try:
                            stream.stop()
                        except Exception:
                            pass

                        try:
                            stream.close()
                        except Exception:
                            pass

                        self._audio_stream = None

                    self._core_tasks = []

            except asyncio.CancelledError:

                self._closing = True

                raise

            except Exception as e:

                if not self._closing:

                    print(
                        "[JEEV] ⚠️ "
                        f"Connection error: {e}"
                    )

                    traceback.print_exc()

                self._session_error = True

            finally:

                # ------------------------------------------------
                # IMPORTANT:
                #
                # Do not schedule anything after this point.
                # This prevents:
                #
                # "cannot schedule new futures after shutdown"
                #
                # ------------------------------------------------

                self._closing = True

                self.session = None

                self._mic = None

                self._loop = None

                self.audio_in_queue = None

                self.out_queue = None

                self._core_tasks = []

                self._audio_turn_active = False

                with self._audio_state_lock:

                    self._audio_playing = False

                if not self._shutdown_requested:

                    self.set_speaking(
                        False
                    )

                self._closing = False

            if self._shutdown_requested:
                break

            print(
                "[JEEV] 🔄 "
                "Gemini session ended."
            )

            print(
                "[JEEV] 🔄 "
                "Reconnecting in 3 seconds..."
            )

            try:

                await asyncio.sleep(
                    3
                )

            except asyncio.CancelledError:
                raise

        # ========================================================
        # FINAL SHUTDOWN
        # ========================================================

        self._closing = True

        print(
            "[JEEV] 🔴 "
            "JEEV stopped."
        )

        try:
            self.ui.set_state(
                "IDLE"
            )
        except Exception:
            pass


# ============================================================
# ASYNC ENGINE THREAD
# ============================================================

class JeevEngineThread(threading.Thread):

    def __init__(
        self,
        engine: JeevLive,
    ):

        super().__init__(
            daemon=True,
            name="JEEV-Engine",
        )

        self.engine = engine

        self.loop = None

        self._started_event = (
            threading.Event()
        )

    def run(self):

        self.loop = asyncio.new_event_loop()

        asyncio.set_event_loop(
            self.loop
        )

        self.engine._loop = self.loop

        self._started_event.set()

        try:

            self.loop.run_until_complete(
                self.engine.run()
            )

        except asyncio.CancelledError:

            pass

        except Exception as e:

            print(
                "[JEEV] ❌ "
                f"Engine thread error: {e}"
            )

            traceback.print_exc()

        finally:

            try:

                pending = (
                    asyncio.all_tasks(
                        self.loop
                    )
                )

                for task in pending:

                    task.cancel()

                if pending:

                    self.loop.run_until_complete(
                        asyncio.gather(
                            *pending,
                            return_exceptions=True,
                        )
                    )

            except Exception:
                pass

            try:
                self.loop.run_until_complete(
                    self.loop.shutdown_asyncgens()
                )
            except Exception:
                pass

            try:
                self.loop.run_until_complete(
                    self.loop.shutdown_default_executor()
                )
            except Exception:
                pass

            try:
                self.loop.close()
            except Exception:
                pass

            self.engine._loop = None

            print(
                "[JEEV] 🔴 "
                "Async engine loop closed."
            )


# ============================================================
# CONSOLE KILL SWITCH
# ============================================================

_shutdown_signal_received = threading.Event()


def _request_console_shutdown(engine, ui):
    """Request a hard, orderly shutdown from Ctrl+C without relying on Gemini."""
    try:
        engine._shutdown_requested = True
        engine._closing = True
    except Exception:
        pass

    try:
        if engine._mic:
            engine._mic.stop()
    except Exception:
        pass

    try:
        loop = engine._loop
        if loop and not loop.is_closed():
            def cancel_engine_tasks():
                for task in asyncio.all_tasks(loop):
                    if not task.done():
                        task.cancel()
            loop.call_soon_threadsafe(cancel_engine_tasks)
    except Exception:
        pass

    try:
        if ui is not None:
            ui.close()
    except Exception:
        pass


def _install_console_kill_switch(engine, ui):
    """Make Ctrl+C reliably stop JEEV even while the Qt UI is running."""
    previous = signal.getsignal(signal.SIGINT)

    def handler(signum, frame):
        if not _shutdown_signal_received.is_set():
            _shutdown_signal_received.set()
            print("\n[JEEV] 🛑 Ctrl+C kill switch activated.")
            _request_console_shutdown(engine, ui)
        else:
            print("[JEEV] 🛑 Shutdown already requested.")

    try:
        signal.signal(signal.SIGINT, handler)
    except Exception as exc:
        print(f"[JEEV] ⚠️ Could not install Ctrl+C handler: {exc}")

    return previous


# ============================================================
# GLOBAL WINDOWS KILL SWITCH
# ============================================================

_hotkey_thread = None
_hotkey_stop = threading.Event()


def _install_windows_kill_switch(engine, ui):
    """Independent Windows global Ctrl+Shift+Q shutdown."""
    global _hotkey_thread
    if os.name != "nt":
        return

    _hotkey_stop.clear()

    def worker():
        user32 = ctypes.windll.user32
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        WM_HOTKEY = 0x0312
        HOTKEY_ID = 0x4A51
        registered = False

        try:
            registered = bool(user32.RegisterHotKey(
                None, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, ord("Q")
            ))
            if not registered:
                print("[JEEV] ⚠️ Ctrl+Shift+Q could not be registered.")
                return

            print("[JEEV] 🛑 Kill switch armed: Ctrl+Shift+Q")
            msg = wintypes.MSG()

            while not _hotkey_stop.is_set():
                result = user32.GetMessageW(
                    ctypes.byref(msg), None, 0, 0
                )
                if result <= 0:
                    break

                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    if not _shutdown_signal_received.is_set():
                        _shutdown_signal_received.set()
                        print("[JEEV] 🛑 Ctrl+Shift+Q activated.")
                        _request_console_shutdown(engine, ui)
                    break

        except Exception as exc:
            print(f"[JEEV] ⚠️ Kill switch error: {exc}")
        finally:
            if registered:
                try:
                    user32.UnregisterHotKey(None, HOTKEY_ID)
                except Exception:
                    pass

    _hotkey_thread = threading.Thread(
        target=worker, name="JEEV-KillSwitch", daemon=True
    )
    _hotkey_thread.start()


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 64)
    print("                    JEEV MARK I")
    print("=" * 64)
    print()
    print(
        "[JEEV] Base directory:"
        f" {BASE_DIR}"
    )
    print()
    print(
        "[JEEV] Verified microphone:"
    )
    print(
        f"       Device {INPUT_DEVICE}"
    )
    print(
        "       Realtek HD Audio Mic input"
    )
    print(
        "       Windows WDM-KS"
    )
    print(
        "       44100 Hz → 16000 Hz"
    )
    print()
    print(
        "[JEEV] Speaker:"
    )
    print(
        "       Airdopes Headphones (Device 4)"
        if OUTPUT_DEVICE == 4
        else (
            "       Windows default output"
            if OUTPUT_DEVICE is None
            else f"       Device {OUTPUT_DEVICE}"
        )
    )
    print(
        "       48000 Hz"
    )
    print()
    print("=" * 64)
    print()

    ui = None
    engine = None
    engine_thread = None

    try:

        # --------------------------------------------------------
        # CREATE UI
        # --------------------------------------------------------

        ui = JarvisUI()

        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None:
                app.setQuitOnLastWindowClosed(False)
        except Exception as e:
            print(
                "[JEEV] ⚠️ Could not configure background UI mode: "
                f"{e}"
            )

        print("[JEEV] 🟢 JEEV running in background.")
        print("[JEEV] ℹ️ Closing the UI does not stop JEEV.")
        print("[JEEV] ℹ️ Press Ctrl+C in this terminal to stop JEEV.")

        # --------------------------------------------------------
        # CREATE ENGINE
        # --------------------------------------------------------

        engine = JeevLive(
            ui
        )

        # Shutdown controls are independent of Gemini/audio/tools.
        _install_console_kill_switch(engine, ui)
        _install_windows_kill_switch(engine, ui)

        # --------------------------------------------------------
        # START ASYNC ENGINE THREAD
        # --------------------------------------------------------

        engine_thread = JeevEngineThread(
            engine
        )

        engine_thread.start()

        engine_thread._started_event.wait(
            timeout=5
        )

        print(
            "[JEEV] 🚀 "
            "Engine thread started."
        )

        # --------------------------------------------------------
        # SHOW THE EXISTING UI
        #
        # IMPORTANT: ui.py already owns the real QApplication and
        # the Dynamic-Island dimensions/design.  main.py must NOT
        # recreate, resize, or replace that UI.  Standalone ui.py
        # explicitly calls ui.show() before ui.run(); do the same
        # here, while keeping the engine in its own thread.
        # --------------------------------------------------------
        try:
            ui.show()
            print("[JEEV] 🖥️ UI connected and visible.")
        except Exception as e:
            print(
                "[JEEV] ⚠️ Could not show UI: "
                f"{e}"
            )

        # --------------------------------------------------------
        # START PYQT UI
        #
        # Your existing JarvisUI owns the actual UI event loop.
        # Support both common APIs without changing the UI class.
        # --------------------------------------------------------

        if hasattr(ui, "run"):
            # ui.py's run() is the authoritative Qt event loop.
            # Do not create a second QApplication or event loop.
            ui.run()
        else:
            print(
                "[JEEV] ⚠️ JarvisUI does not expose run(); "
                "UI event loop cannot be started."
            )

        print(
            "[JEEV] 🟢 UI closed/hidden; "
            "JEEV continues listening in background."
        )
        print(
            "[JEEV] ℹ️ Press Ctrl+C in this terminal to stop JEEV."
        )

        while (
            engine_thread
            and engine_thread.is_alive()
            and not engine._shutdown_requested
        ):
            if _shutdown_signal_received.is_set():
                _request_console_shutdown(engine, ui)
                break
            time.sleep(0.25)

    except KeyboardInterrupt:

        print(
            "\n[JEEV] 🛑 "
            "Keyboard interrupt received."
        )

    except Exception as e:

        print(
            "[JEEV] ❌ "
            f"Fatal application error: {e}"
        )

        traceback.print_exc()

    finally:

        # ========================================================
        # ORDERLY SHUTDOWN
        # ========================================================
        #
        # IMPORTANT:
        #
        # 1. Tell engine to stop.
        # 2. Stop microphone.
        # 3. Cancel async tasks.
        # 4. Close Gemini session.
        # 5. Close audio streams.
        # 6. Close event loop.
        #
        # This prevents the old:
        #
        # "cannot schedule new futures after shutdown"
        #
        # ========================================================

        if engine:

            print(
                "[JEEV] 🧹 "
                "Requesting engine shutdown..."
            )

            engine._shutdown_requested = True
            engine._closing = True

            # Stop microphone immediately.

            if engine._mic:

                try:
                    engine._mic.stop()
                except Exception:
                    pass

            # Wake audio queues if they exist.

            try:

                if (
                    engine.out_queue
                    and
                    engine._loop
                    and
                    not engine._loop.is_closed()
                ):

                    engine.out_queue.put_nowait(
                        None
                    )

            except Exception:
                pass

            try:

                if (
                    engine.audio_in_queue
                    and
                    engine._loop
                    and
                    not engine._loop.is_closed()
                ):

                    engine.audio_in_queue.put_nowait(
                        None
                    )

            except Exception:
                pass

        # --------------------------------------------------------
        # WAIT FOR ENGINE THREAD
        # --------------------------------------------------------

        if engine_thread:

            print(
                "[JEEV] ⏳ "
                "Waiting for engine thread..."
            )

            engine_thread.join(
                timeout=8
            )

            if engine_thread.is_alive():

                print(
                    "[JEEV] ⚠️ "
                    "Engine thread did not finish "
                    "within shutdown timeout."
                )

        # --------------------------------------------------------
        # DEDICATED AUDIO EXECUTOR CLEANUP
        # --------------------------------------------------------
        if engine:
            for executor_name in (
                "_mic_executor",
                "_speaker_executor",
            ):
                executor = getattr(engine, executor_name, None)
                if executor:
                    try:
                        executor.shutdown(
                            wait=False,
                            cancel_futures=True,
                        )
                    except Exception:
                        pass

        # --------------------------------------------------------
        # UI CLOSE
        # --------------------------------------------------------

        if ui:

            try:

                if hasattr(
                    ui,
                    "close"
                ):

                    ui.close()

            except Exception:
                pass

        print()
        print(
            "=" * 64
        )
        print(
            "                 JEEV OFFLINE"
        )
        print(
            "=" * 64
        )
        print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()