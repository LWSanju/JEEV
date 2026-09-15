from __future__ import annotations

import atexit
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


"""
JEEV GMAIL CONTROL
==================

Persistent browser-based Gmail controller.

Browser policy:
    1. Brave
    2. Chrome
    3. Firefox
    4. Opera

IMPORTANT:
    - Edge is NEVER used.
    - No Gmail OAuth token.
    - No Gmail API.
    - No credentials.json.
    - No Gmail password storage.
    - User signs into Gmail normally.
    - Dedicated JEEV browser profile.
    - Browser is launched as an independent Windows process.
    - Playwright connects to the running browser.
    - Python process exiting does NOT close Brave/Chrome/Opera.
    - close action explicitly closes the JEEV browser.
    - Does NOT import main.py.
    - Does NOT touch Spotify.
    - Does NOT touch WhatsApp.
    - Does NOT touch microphone/audio.
    - Does NOT create a background loop.

Supported actions:
    setup
    open
    latest
    read_latest
    search
    read_search
    select
    current
    generate_reply
    reply
    send
    close
"""


# ============================================================
# PATHS
# ============================================================

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _THIS_DIR.parent

_GMAIL_DATA_DIR = _PROJECT_DIR / ".jeev_gmail"
_PROFILE_DIR = _GMAIL_DATA_DIR / "browser_profile"
_CONFIG_FILE = _GMAIL_DATA_DIR / "gmail_config.json"

_GMAIL_DATA_DIR.mkdir(parents=True, exist_ok=True)
_PROFILE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# PERSISTENT BROWSER SETTINGS
# ============================================================

# Dedicated port so JEEV does not interfere with normal Brave.
_REMOTE_DEBUG_PORT = 9227

_GMAIL_URL = "https://mail.google.com/mail/u/0/#inbox"

# Browser process handle is intentionally NOT used as ownership.
# The browser is an independent Windows process.
_BROWSER_PROCESS: Optional[subprocess.Popen] = None

# Playwright only connects to the independent browser.
_PLAYWRIGHT = None
_CONNECTION = None
_CONTEXT = None
_PAGE = None

_CURRENT_EMAIL: Dict[str, Any] = {}
_SEARCH_RESULTS: List[Dict[str, Any]] = []
_PENDING_REPLY = ""


# ============================================================
# LOGGING
# ============================================================

def _log(*args: Any) -> None:
    print("[JEEV][Gmail]", *args)


# ============================================================
# CONFIG
# ============================================================

def _load_config() -> Dict[str, Any]:
    try:
        if _CONFIG_FILE.exists():
            with _CONFIG_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                return data

    except Exception as exc:
        _log("Could not load Gmail config:", repr(exc))

    return {}


def _save_config(data: Dict[str, Any]) -> bool:
    try:
        _GMAIL_DATA_DIR.mkdir(parents=True, exist_ok=True)

        temporary = _CONFIG_FILE.with_suffix(".tmp")

        with temporary.open("w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False,
            )

        temporary.replace(_CONFIG_FILE)
        return True

    except Exception as exc:
        _log("Could not save Gmail config:", repr(exc))
        return False


def _get_email_id() -> str:
    config = _load_config()

    return str(
        config.get("email", "") or ""
    ).strip()


def _setup_email_id() -> str:
    """
    Ask for Gmail address only if it has not already been saved.

    The address is only an identifier.
    It is NOT used for authentication.
    """

    existing = _get_email_id()

    if existing:
        return existing

    print()
    print("=" * 60)
    print(" JEEV GMAIL SETUP")
    print("=" * 60)
    print()
    print("Enter the Gmail address this JEEV installation will use.")
    print()
    print("This address is stored locally only as an identifier.")
    print("JEEV will NOT ask for your Gmail password.")
    print()

    try:
        email = input("Gmail address: ").strip()

    except (EOFError, KeyboardInterrupt):
        return ""

    if not email:
        return ""

    if not re.match(
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        email,
    ):
        print("That does not look like a valid email address.")
        return ""

    config = _load_config()
    config["email"] = email

    if not _save_config(config):
        return ""

    _log("Gmail address saved locally:", email)

    return email


# ============================================================
# WINDOWS BROWSER DETECTION
# ============================================================

def _browser_candidates() -> List[Dict[str, Any]]:
    """
    Return supported browsers in JEEV priority order.

    EDGE IS INTENTIONALLY ABSENT.
    """

    local_app_data = os.environ.get(
        "LOCALAPPDATA",
        "",
    )

    program_files = os.environ.get(
        "PROGRAMFILES",
        r"C:\Program Files",
    )

    program_files_x86 = os.environ.get(
        "PROGRAMFILES(X86)",
        r"C:\Program Files (x86)",
    )

    program_files_list = [
        Path(program_files),
        Path(program_files_x86),
    ]

    candidates: List[Dict[str, Any]] = []

    # --------------------------------------------------------
    # BRAVE
    # --------------------------------------------------------

    brave_paths = [
        Path(local_app_data)
        / "BraveSoftware"
        / "Brave-Browser"
        / "Application"
        / "brave.exe",

        *[
            base
            / "BraveSoftware"
            / "Brave-Browser"
            / "Application"
            / "brave.exe"
            for base in program_files_list
        ],
    ]

    candidates.append(
        {
            "name": "Brave",
            "engine": "chromium",
            "executables": brave_paths,
        }
    )

    # --------------------------------------------------------
    # CHROME
    # --------------------------------------------------------

    chrome_paths = [
        Path(local_app_data)
        / "Google"
        / "Chrome"
        / "Application"
        / "chrome.exe",

        *[
            base
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe"
            for base in program_files_list
        ],
    ]

    candidates.append(
        {
            "name": "Chrome",
            "engine": "chromium",
            "executables": chrome_paths,
        }
    )

    # --------------------------------------------------------
    # FIREFOX
    # --------------------------------------------------------

    firefox_paths = [
        Path(program_files)
        / "Mozilla Firefox"
        / "firefox.exe",

        Path(program_files_x86)
        / "Mozilla Firefox"
        / "firefox.exe",

        Path(local_app_data)
        / "Mozilla Firefox"
        / "firefox.exe",
    ]

    candidates.append(
        {
            "name": "Firefox",
            "engine": "firefox",
            "executables": firefox_paths,
        }
    )

    # --------------------------------------------------------
    # OPERA
    # --------------------------------------------------------

    opera_paths = [
        Path(local_app_data)
        / "Programs"
        / "Opera"
        / "opera.exe",

        Path(local_app_data)
        / "Programs"
        / "Opera GX"
        / "opera.exe",

        Path(program_files)
        / "Opera"
        / "opera.exe",

        Path(program_files_x86)
        / "Opera"
        / "opera.exe",

        Path(program_files)
        / "Opera GX"
        / "opera.exe",

        Path(program_files_x86)
        / "Opera GX"
        / "opera.exe",
    ]

    candidates.append(
        {
            "name": "Opera",
            "engine": "chromium",
            "executables": opera_paths,
        }
    )

    return candidates


def _find_installed_browser() -> Dict[str, str]:
    """
    Find an installed supported browser.

    Priority:
        Brave
        Chrome
        Firefox
        Opera

    Edge is never returned.
    """

    if os.name != "nt":
        return {
            "name": "",
            "engine": "",
            "exe": "",
        }

    for browser in _browser_candidates():

        name = browser["name"]
        engine = browser["engine"]

        for executable in browser["executables"]:

            try:
                if executable.is_file():

                    _log(
                        "Browser detected:",
                        name,
                    )

                    _log(
                        "Using browser executable:",
                        str(executable),
                    )

                    return {
                        "name": name,
                        "engine": engine,
                        "exe": str(executable),
                    }

            except Exception:
                pass

    _log(
        "No supported browser found.",
        "Brave/Chrome/Firefox/Opera were checked.",
    )

    return {
        "name": "",
        "engine": "",
        "exe": "",
    }


# ============================================================
# PORT CHECK
# ============================================================

def _port_is_open(
    host: str = "127.0.0.1",
    port: int = _REMOTE_DEBUG_PORT,
) -> bool:

    try:
        with socket.create_connection(
            (host, port),
            timeout=0.4,
        ):
            return True

    except OSError:
        return False


# ============================================================
# PLAYWRIGHT
# ============================================================

def _require_playwright():
    """Load Playwright lazily with an actionable JEEV-venv error."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError as exc:
        venv_python = _PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
        command = (
            f'"{venv_python}" -m pip install playwright'
            if venv_python.exists()
            else r'.\\.venv\\Scripts\\python.exe -m pip install playwright'
        )
        raise RuntimeError(
            "Gmail control needs Playwright.\n\n"
            "Install it in JEEV's active virtual environment with:\n" + command
        ) from exc


# ============================================================
# LAUNCH INDEPENDENT CHROMIUM BROWSER
# ============================================================

def _launch_independent_chromium(
    browser_exe: str,
    browser_name: str,
) -> bool:
    """
    Launch Brave/Chrome/Opera as an independent process.

    IMPORTANT:
        Playwright does NOT own this process.

    Therefore:
        python -c "...gmail_control..." exits
        ->
        browser remains open.
    """

    global _BROWSER_PROCESS

    if _port_is_open():
        _log(
            "Existing JEEV browser detected on port",
            _REMOTE_DEBUG_PORT,
        )
        return True

    _PROFILE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    args = [
        browser_exe,

        f"--remote-debugging-port={_REMOTE_DEBUG_PORT}",

        f"--user-data-dir={str(_PROFILE_DIR)}",

        "--no-first-run",

        "--no-default-browser-check",

        "--disable-background-networking",

        "--disable-breakpad",

        "--disable-session-crashed-bubble",

        "--disable-features=Translate",

        _GMAIL_URL,
    ]

    _log(
        "Launching independent browser:",
        browser_name,
    )

    _log(
        "Browser profile:",
        str(_PROFILE_DIR),
    )

    _log(
        "Remote debugging port:",
        _REMOTE_DEBUG_PORT,
    )

    try:

        creation_flags = 0

        if os.name == "nt":

            creation_flags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
            )

        _BROWSER_PROCESS = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
            close_fds=True,
        )

    except Exception as exc:

        _log(
            "Could not launch browser:",
            repr(exc),
        )

        _BROWSER_PROCESS = None

        return False

    # --------------------------------------------------------
    # Wait for remote debugging endpoint
    # --------------------------------------------------------

    deadline = time.time() + 15.0

    while time.time() < deadline:

        if _port_is_open():
            _log(
                browser_name,
                "is running independently.",
            )
            return True

        time.sleep(0.25)

    _log(
        "Browser launched but remote debugging port",
        "did not become available.",
    )

    return False


# ============================================================
# CONNECT TO INDEPENDENT CHROMIUM
# ============================================================

def _connect_chromium() -> bool:
    global _PLAYWRIGHT
    global _CONNECTION
    global _CONTEXT
    global _PAGE

    sync_playwright = _require_playwright()

    try:

        if _PLAYWRIGHT is None:
            _PLAYWRIGHT = sync_playwright().start()

        # ----------------------------------------------------
        # Already connected
        # ----------------------------------------------------

        if _CONNECTION is not None:

            try:

                if _CONNECTION.contexts:

                    _CONTEXT = _CONNECTION.contexts[0]

                    pages = _CONTEXT.pages

                    if pages:
                        _PAGE = pages[0]

                    else:
                        _PAGE = _CONTEXT.new_page()

                    return True

            except Exception:
                pass

        # ----------------------------------------------------
        # Connect to running browser
        # ----------------------------------------------------

        _log(
            "Connecting Playwright to independent browser..."
        )

        _CONNECTION = _PLAYWRIGHT.chromium.connect_over_cdp(
            f"http://127.0.0.1:{_REMOTE_DEBUG_PORT}"
        )

        contexts = _CONNECTION.contexts

        if contexts:

            _CONTEXT = contexts[0]

        else:

            _log(
                "Browser connected but no browser context exists."
            )

            return False

        pages = _CONTEXT.pages

        if pages:

            _PAGE = pages[0]

        else:

            _PAGE = _CONTEXT.new_page()

        _log(
            "Playwright connected to persistent browser."
        )

        return True

    except Exception as exc:

        _log(
            "Could not connect to browser:",
            repr(exc),
        )

        return False


# ============================================================
# START BROWSER
# ============================================================

def _start_browser() -> bool:

    global _PAGE
    global _CONTEXT

    # --------------------------------------------------------
    # Existing connection
    # --------------------------------------------------------

    if _PAGE is not None:

        try:

            if not _PAGE.is_closed():

                return True

        except Exception:

            pass

    browser_info = _find_installed_browser()

    browser_name = browser_info.get(
        "name",
        "",
    )

    browser_engine = browser_info.get(
        "engine",
        "",
    )

    browser_exe = browser_info.get(
        "exe",
        "",
    )

    if not browser_name or not browser_exe:

        return False

    # --------------------------------------------------------
    # Chromium browsers
    # --------------------------------------------------------

    if browser_engine == "chromium":

        # First launch an independent process.
        if not _port_is_open():

            if not _launch_independent_chromium(
                browser_exe,
                browser_name,
            ):
                return False

        # Then connect Playwright.
        if not _connect_chromium():

            return False

        _log(
            "Gmail browser started using:",
            browser_name,
        )

        return True

    # --------------------------------------------------------
    # Firefox
    #
    # Firefox cannot use the same Chromium CDP architecture.
    # It is launched independently as a fallback.
    # --------------------------------------------------------

    if browser_engine == "firefox":

        try:

            _log(
                "Firefox detected."
            )

            args = [
                browser_exe,
                "-profile",
                str(_PROFILE_DIR),
                _GMAIL_URL,
            ]

            creation_flags = 0

            if os.name == "nt":

                creation_flags = (
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.DETACHED_PROCESS
                )

            subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                close_fds=True,
            )

            _log(
                "Firefox Gmail browser started."
            )

            # Firefox is independent.
            # Gmail actions requiring DOM automation are not
            # connected through CDP.
            _PAGE = None
            _CONTEXT = None

            return True

        except Exception as exc:

            _log(
                "Firefox startup failed:",
                repr(exc),
            )

            return False

    return False


# ============================================================
# PAGE
# ============================================================

def _page():

    if not _start_browser():
        return None

    return _PAGE


# ============================================================
# OPEN GMAIL
# ============================================================

def _ensure_gmail() -> bool:

    page = _page()

    if page is None:

        # Firefox fallback can still open Gmail manually.
        browser_info = _find_installed_browser()

        if browser_info.get("engine") == "firefox":

            return True

        return False

    try:

        current = page.url or ""

        if "mail.google.com" not in current:

            page.goto(
                _GMAIL_URL,
                wait_until="domcontentloaded",
                timeout=30000,
            )

        time.sleep(2.0)

        return True

    except Exception as exc:

        _log(
            "Could not open Gmail:",
            repr(exc),
        )

        return False


# ============================================================
# LOGIN DETECTION
# ============================================================

def _gmail_logged_in() -> bool:

    page = _page()

    if page is None:
        return False

    try:

        url = page.url or ""

        if "accounts.google.com" in url:
            return False

        if "mail.google.com" not in url:
            return False

        selectors = [
            '[role="main"]',
            'input[placeholder*="Search mail"]',
            'input[aria-label="Search mail"]',
            'div[role="navigation"]',
            'div[aria-label="Inbox"]',
        ]

        for selector in selectors:

            try:

                loc = page.locator(
                    selector
                ).first

                if loc.is_visible(
                    timeout=1000
                ):

                    return True

            except Exception:

                pass

        return False

    except Exception:

        return False


# ============================================================
# OPEN / SETUP
# ============================================================

def _open_gmail() -> str:

    email = _setup_email_id()

    if not email:

        return "I could not save the Gmail address."

    if not _ensure_gmail():

        return "I could not open Gmail."

    # --------------------------------------------------------
    # If Playwright can see Gmail, check login.
    # --------------------------------------------------------

    if _PAGE is not None:

        if not _gmail_logged_in():

            _log(
                "Gmail is not signed in."
            )

            _log(
                "Please sign into:",
                email,
            )

            return (
                f"Gmail is open for {email}. "
                "Please sign into that Gmail account in the browser. "
                "You only need to do this once for this JEEV Gmail profile."
            )

        return f"Gmail is open for {email}."

    # --------------------------------------------------------
    # Browser opened but no automation connection.
    # --------------------------------------------------------

    return (
        f"Gmail is open for {email}. "
        "Please sign into Gmail if required."
    )


# ============================================================
# TEXT HELPERS
# ============================================================

def _clean_text(text: Any) -> str:

    if text is None:
        return ""

    text = str(text)

    text = text.replace(
        "\xa0",
        " ",
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _visible_text(locator) -> str:

    try:

        return _clean_text(
            locator.inner_text(
                timeout=1500
            )
        )

    except Exception:

        return ""


# ============================================================
# SEARCH BOX
# ============================================================

def _find_search_box():

    page = _page()

    if page is None:
        return None

    selectors = [
        'input[aria-label="Search mail"]',
        'input[placeholder="Search mail"]',
        'input[placeholder*="Search mail"]',
        'input[name="q"]',
    ]

    for selector in selectors:

        try:

            loc = page.locator(
                selector
            ).first

            if loc.is_visible(
                timeout=1000
            ):

                return loc

        except Exception:

            pass

    return None


# ============================================================
# MESSAGE ROWS
# ============================================================

def _collect_message_rows() -> List[Dict[str, Any]]:

    page = _page()

    if page is None:
        return []

    selectors = [
        "tr.zA",
        '[role="main"] tr',
    ]

    rows = None

    for selector in selectors:

        try:

            candidate = page.locator(
                selector
            )

            if candidate.count():

                rows = candidate
                break

        except Exception:

            pass

    if rows is None:
        return []

    try:

        count = min(
            rows.count(),
            100,
        )

    except Exception:

        return []

    results = []

    for index in range(count):

        row = rows.nth(index)

        try:

            if not row.is_visible(
                timeout=300
            ):
                continue

        except Exception:

            continue

        text = _visible_text(row)

        if not text:
            continue

        sender = ""

        for selector in [
            ".yW",
            ".yX",
            "span[email]",
        ]:

            try:

                loc = row.locator(
                    selector
                ).first

                if loc.count():

                    sender = _visible_text(loc)

                    if not sender:

                        sender = _clean_text(
                            loc.get_attribute("email")
                            or ""
                        )

                    if sender:
                        break

            except Exception:

                pass

        subject = ""

        for selector in [
            ".bog",
            ".y6",
        ]:

            try:

                loc = row.locator(
                    selector
                ).first

                if loc.count():

                    subject = _visible_text(loc)

                    if subject:
                        break

            except Exception:

                pass

        if not sender:
            sender = text[:120]

        if not subject:
            subject = text

        results.append(
            {
                "index": len(results) + 1,
                "sender": sender,
                "subject": subject,
                "snippet": text,
                "_locator_index": index,
            }
        )

    return results


# ============================================================
# OPEN EMAIL RESULT
# ============================================================

def _open_result(index: int) -> str:

    global _CURRENT_EMAIL

    if not _SEARCH_RESULTS:

        return (
            "There are no pending Gmail search results."
        )

    try:

        index = int(index)

    except Exception:

        return (
            "Please provide a valid email number."
        )

    if index < 1 or index > len(_SEARCH_RESULTS):

        return (
            f"I found {len(_SEARCH_RESULTS)} emails. "
            f"Please choose a number from 1 to "
            f"{len(_SEARCH_RESULTS)}."
        )

    item = _SEARCH_RESULTS[index - 1]

    page = _page()

    if page is None:

        return "Gmail automation is not available."

    try:

        row = None

        selectors = [
            "tr.zA",
            '[role="main"] tr',
        ]

        for selector in selectors:

            try:

                candidate_rows = page.locator(
                    selector
                )

                locator_index = item[
                    "_locator_index"
                ]

                if (
                    candidate_rows.count()
                    > locator_index
                ):

                    row = candidate_rows.nth(
                        locator_index
                    )

                    break

            except Exception:

                pass

        if row is None:

            return (
                "I could not locate that email in Gmail."
            )

        row.scroll_into_view_if_needed(
            timeout=2000
        )

        row.click(
            timeout=5000
        )

        time.sleep(2.0)

        return _capture_current_email()

    except Exception as exc:

        return (
            f"I could not open that email: {exc}"
        )


# ============================================================
# CAPTURE CURRENT EMAIL
# ============================================================

def _capture_current_email() -> str:

    global _CURRENT_EMAIL

    page = _page()

    if page is None:

        return "Gmail automation is not available."

    try:

        body = page.locator(
            "body"
        ).inner_text(
            timeout=5000
        )

    except Exception:

        body = ""

    body = _clean_text(body)

    if not body:

        return (
            "I opened the email, but I could not "
            "read its contents."
        )

    subject = ""

    for selector in [
        "h2.hP",
        'h2[role="heading"]',
        '[role="main"] h2',
    ]:

        try:

            loc = page.locator(
                selector
            ).first

            if loc.count():

                subject = _visible_text(loc)

                if subject:
                    break

        except Exception:

            pass

    sender = ""

    for selector in [
        ".gD",
        "span[email]",
        "[email]",
    ]:

        try:

            loc = page.locator(
                selector
            ).first

            if loc.count():

                sender = _clean_text(
                    loc.get_attribute("email")
                    or _visible_text(loc)
                )

                if sender:
                    break

        except Exception:

            pass

    message_text = ""

    for selector in [
        "div.a3s.aiL",
        "div.a3s",
    ]:

        try:

            loc = page.locator(
                selector
            ).last

            if loc.count():

                candidate = _visible_text(loc)

                if len(candidate) > len(message_text):

                    message_text = candidate

        except Exception:

            pass

    if not message_text:

        message_text = body

    _CURRENT_EMAIL = {
        "sender": sender,
        "subject": subject,
        "body": message_text,
        "opened_at": time.time(),
    }

    spoken = message_text

    if len(spoken) > 12000:

        spoken = spoken[:12000] + " ..."

    title = subject or "this email"

    sender_part = (
        f" from {sender}"
        if sender
        else ""
    )

    return (
        f"Email: {title}{sender_part}.\n\n"
        f"{spoken}"
    )


# ============================================================
# READ LATEST
# ============================================================

def _read_latest() -> str:

    if not _ensure_gmail():

        return "I could not open Gmail."

    if not _gmail_logged_in():

        return (
            "Gmail is not signed in. "
            "Please sign into Gmail first."
        )

    page = _page()

    if page is None:

        return "Gmail automation is not available."

    try:

        page.goto(
            _GMAIL_URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        time.sleep(2.5)

    except Exception:

        pass

    global _SEARCH_RESULTS

    _SEARCH_RESULTS = _collect_message_rows()

    if not _SEARCH_RESULTS:

        return (
            "I could not find any visible "
            "emails in Gmail."
        )

    return _open_result(1)


# ============================================================
# SEARCH
# ============================================================

def _search_gmail(query: str) -> str:

    global _SEARCH_RESULTS

    query = _clean_text(query)

    if not query:

        return "No Gmail search query was provided."

    if not _ensure_gmail():

        return "I could not open Gmail."

    if not _gmail_logged_in():

        return (
            "Gmail is not signed in. "
            "Please sign into Gmail first."
        )

    page = _page()

    if page is None:

        return "Gmail automation is not available."

    box = _find_search_box()

    if box is None:

        return (
            "I could not find Gmail's search box."
        )

    try:

        box.click()

        box.fill(query)

        box.press("Enter")

        time.sleep(2.5)

    except Exception as exc:

        return (
            f"Gmail search failed: {exc}"
        )

    _SEARCH_RESULTS = _collect_message_rows()

    if not _SEARCH_RESULTS:

        return (
            f"I could not find visible Gmail "
            f"results for '{query}'."
        )

    lines = []

    for i, item in enumerate(
        _SEARCH_RESULTS,
        1,
    ):

        sender = item.get(
            "sender",
            "Unknown sender",
        )

        subject = item.get(
            "subject",
            "(no subject)",
        )

        snippet = item.get(
            "snippet",
            "",
        )

        if snippet:

            lines.append(
                f"{i}. {sender} — "
                f"{subject}. {snippet}"
            )

        else:

            lines.append(
                f"{i}. {sender} — {subject}"
            )

    return (
        f"I found {len(_SEARCH_RESULTS)} "
        "matching emails.\n"
        + "\n".join(lines)
        + "\nTell me the number of the email "
        "you want."
    )


# ============================================================
# SEARCH + READ
# ============================================================

def _read_search(query: str) -> str:

    result = _search_gmail(query)

    if not _SEARCH_RESULTS:

        return result

    if len(_SEARCH_RESULTS) > 1:

        return result

    return _open_result(1)


# ============================================================
# CURRENT EMAIL
# ============================================================

def _current_email() -> str:

    if not _CURRENT_EMAIL:

        return (
            "There is no selected email yet."
        )

    subject = (
        _CURRENT_EMAIL.get("subject")
        or "(no subject)"
    )

    sender = (
        _CURRENT_EMAIL.get("sender")
        or "unknown sender"
    )

    body = (
        _CURRENT_EMAIL.get("body")
        or ""
    )

    if len(body) > 12000:

        body = body[:12000] + " ..."

    return (
        f"Selected email: {subject}, "
        f"from {sender}.\n\n"
        f"{body}"
    )


# ============================================================
# REPLY BUTTON
# ============================================================

def _find_reply_button():

    page = _page()

    if page is None:
        return None

    selectors = [
        'div[role="button"][aria-label^="Reply"]',
        'button[aria-label^="Reply"]',
        '[role="button"][data-tooltip^="Reply"]',
        '[aria-label="Reply"]',
    ]

    for selector in selectors:

        try:

            loc = page.locator(
                selector
            ).last

            if (
                loc.count()
                and loc.is_visible(timeout=1000)
            ):

                return loc

        except Exception:

            pass

    return None


# ============================================================
# REPLY EDITOR
# ============================================================

def _find_reply_editor():

    page = _page()

    if page is None:
        return None

    selectors = [
        'div[contenteditable="true"][aria-label*="Message Body"]',
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
        "textarea",
    ]

    for selector in selectors:

        try:

            loc = page.locator(
                selector
            ).last

            if (
                loc.count()
                and loc.is_visible(timeout=1000)
            ):

                return loc

        except Exception:

            pass

    return None


# ============================================================
# GENERATE REPLY
# ============================================================

def _generate_reply_text() -> str:

    global _PENDING_REPLY

    if not _CURRENT_EMAIL:

        return (
            "There is no selected email "
            "to reply to."
        )

    body = str(
        _CURRENT_EMAIL.get(
            "body",
            "",
        )
        or ""
    ).strip()

    subject = str(
        _CURRENT_EMAIL.get(
            "subject",
            "",
        )
        or ""
    ).strip()

    sender = str(
        _CURRENT_EMAIL.get(
            "sender",
            "",
        )
        or ""
    ).strip()

    if not body:

        return (
            "The selected email has no "
            "readable content."
        )

    api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )

    if not api_key:

        return (
            "I cannot generate the reply "
            "because GEMINI_API_KEY is not "
            "available in this environment."
        )

    try:

        from google import genai

        client = genai.Client(
            api_key=api_key
        )

        prompt = f"""
You are JEEV, a personal voice assistant.

Generate a natural reply to this email.

Rules:

- Do not invent facts.
- Do not claim the user completed something
  unless the email clearly establishes it.
- Keep the reply concise unless detail is needed.
- Do not include a subject line.
- Return only the reply text.

Sender:
{sender}

Subject:
{subject}

Email:
{body}
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

        reply = str(
            getattr(
                response,
                "text",
                "",
            )
            or ""
        ).strip()

        if not reply:

            return (
                "Gemini did not generate "
                "a reply."
            )

        _PENDING_REPLY = reply

        return (
            "Generated reply:\n\n"
            + reply
            + "\n\nSay 'send it' when you "
            "want me to send it."
        )

    except Exception as exc:

        _log(
            "Reply generation failed:",
            repr(exc),
        )

        return (
            f"I could not generate "
            f"the reply: {exc}"
        )


# ============================================================
# PUT REPLY INTO GMAIL
# ============================================================

def _reply_to_current_email() -> str:

    if not _CURRENT_EMAIL:

        return (
            "There is no selected email "
            "to reply to."
        )

    page = _page()

    if page is None:

        return "Gmail automation is not available."

    if not _PENDING_REPLY:

        return (
            "No generated reply is waiting. "
            "Say generate a reply first."
        )

    button = _find_reply_button()

    if button is None:

        return (
            "I could not find Gmail's "
            "Reply button."
        )

    try:

        button.scroll_into_view_if_needed(
            timeout=2000
        )

        button.click(
            timeout=5000
        )

        time.sleep(1.2)

    except Exception as exc:

        return (
            f"I could not open the Gmail "
            f"reply box: {exc}"
        )

    editor = _find_reply_editor()

    if editor is None:

        return (
            "I could not find Gmail's "
            "reply editor."
        )

    try:

        editor.click()

        editor.fill(
            _PENDING_REPLY
        )

        return (
            "The generated reply is in Gmail. "
            "Say 'send it' if you want me to "
            "send it."
        )

    except Exception as exc:

        return (
            f"I could not enter the "
            f"generated reply: {exc}"
        )


# ============================================================
# SEND
# ============================================================

def _send_current_reply() -> str:

    global _PENDING_REPLY

    page = _page()

    if page is None:

        return "Gmail automation is not available."

    selectors = [
        'div[role="button"][aria-label^="Send"]',
        'div[role="button"][data-tooltip^="Send"]',
        'button[aria-label^="Send"]',
        '[role="button"][command="Send"]',
    ]

    button = None

    for selector in selectors:

        try:

            loc = page.locator(
                selector
            ).last

            if (
                loc.count()
                and loc.is_visible(timeout=1000)
            ):

                button = loc
                break

        except Exception:

            pass

    if button is None:

        return (
            "I could not find Gmail's "
            "Send button."
        )

    try:

        button.scroll_into_view_if_needed(
            timeout=2000
        )

        button.click(
            timeout=5000
        )

        time.sleep(1.5)

        _PENDING_REPLY = ""

        return (
            "The Gmail reply was sent."
        )

    except Exception as exc:

        return (
            f"I could not send the "
            f"Gmail reply: {exc}"
        )


# ============================================================
# CLOSE
# ============================================================

def _close() -> str:

    global _PAGE
    global _CONTEXT
    global _CONNECTION
    global _PLAYWRIGHT
    global _BROWSER_PROCESS
    global _CURRENT_EMAIL
    global _SEARCH_RESULTS
    global _PENDING_REPLY

    # --------------------------------------------------------
    # Close Playwright connection first.
    # --------------------------------------------------------

    try:

        if _CONNECTION is not None:

            _CONNECTION.close()

    except Exception as exc:

        _log(
            "Browser connection close warning:",
            repr(exc),
        )

    # --------------------------------------------------------
    # Explicitly terminate the independent browser.
    #
    # This ONLY happens for the "close" action.
    # --------------------------------------------------------

    try:

        if (
            _BROWSER_PROCESS is not None
            and _BROWSER_PROCESS.poll() is None
        ):

            _BROWSER_PROCESS.terminate()

            try:

                _BROWSER_PROCESS.wait(
                    timeout=5
                )

            except subprocess.TimeoutExpired:

                _BROWSER_PROCESS.kill()

    except Exception as exc:

        _log(
            "Browser process close warning:",
            repr(exc),
        )

    # --------------------------------------------------------
    # Fallback: close by remote debugging is intentionally
    # avoided because it can interfere with the user's browser.
    #
    # JEEV uses its dedicated profile, so the process handle
    # belongs to the JEEV browser.
    # --------------------------------------------------------

    _PAGE = None
    _CONTEXT = None
    _CONNECTION = None
    _PLAYWRIGHT = None
    _BROWSER_PROCESS = None

    _CURRENT_EMAIL = {}
    _SEARCH_RESULTS = []
    _PENDING_REPLY = ""

    return "Gmail browser closed."


# ============================================================
# CLEAN SHUTDOWN
# ============================================================

def _shutdown_gmail_playwright() -> None:
    """
    IMPORTANT:

    This function intentionally DOES NOT close the browser.

    The browser is independent from Python.

    This prevents:

        python -c "gmail_control(...setup...)"

    from immediately closing Brave when Python exits.
    """

    global _PAGE
    global _CONTEXT
    global _CONNECTION
    global _PLAYWRIGHT

    try:

        if _CONNECTION is not None:

            _CONNECTION.close()

    except Exception:

        pass

    try:

        if _PLAYWRIGHT is not None:

            _PLAYWRIGHT.stop()

    except Exception:

        pass

    _PAGE = None
    _CONTEXT = None
    _CONNECTION = None
    _PLAYWRIGHT = None

    # DO NOT terminate _BROWSER_PROCESS here.


atexit.register(
    _shutdown_gmail_playwright
)


# ============================================================
# MAIN CONTROLLER
# ============================================================

def gmail_control(
    command: Dict[str, Any]
) -> str:

    if not isinstance(command, dict):

        return "Invalid Gmail command."

    action = str(
        command.get("action", "")
        or command.get("command", "")
        or ""
    ).strip().lower()

    _log(
        "action=",
        repr(action),
        "query=",
        repr(command.get("query", "")),
        "receiver=",
        repr(command.get("receiver", "")),
    )

    try:

        # ----------------------------------------------------
        # SETUP
        # ----------------------------------------------------

        if action in (
            "setup",
            "connect",
            "setup_gmail",
        ):

            return _open_gmail()

        # ----------------------------------------------------
        # OPEN
        # ----------------------------------------------------

        if action in (
            "open",
            "open_gmail",
            "start",
        ):

            return _open_gmail()

        # ----------------------------------------------------
        # LATEST
        # ----------------------------------------------------

        if action in (
            "latest",
            "latest_mail",
            "read_latest",
            "read_mail",
            "read_email",
        ):

            return _read_latest()

        # ----------------------------------------------------
        # SEARCH
        # ----------------------------------------------------

        if action in (
            "search",
            "search_mail",
            "find",
            "find_email",
        ):

            query = (
                command.get("query")
                or command.get("search")
                or command.get("text")
                or ""
            )

            return _search_gmail(query)

        # ----------------------------------------------------
        # SEARCH + READ
        # ----------------------------------------------------

        if action in (
            "read_search",
            "search_and_read",
        ):

            query = (
                command.get("query")
                or command.get("search")
                or ""
            )

            return _read_search(query)

        # ----------------------------------------------------
        # SELECT EMAIL
        # ----------------------------------------------------

        if action in (
            "select",
            "select_email",
            "open_email",
        ):

            index = (
                command.get("index")
                or command.get("email_index")
                or command.get("contact_index")
            )

            if index is None:

                return (
                    "Please tell me which "
                    "email number to select."
                )

            return _open_result(index)

        # ----------------------------------------------------
        # CURRENT EMAIL
        # ----------------------------------------------------

        if action in (
            "current",
            "current_email",
            "selected",
            "that_one",
        ):

            return _current_email()

        # ----------------------------------------------------
        # GENERATE REPLY
        # ----------------------------------------------------

        if action in (
            "generate_reply",
            "draft_reply",
            "reply_generate",
        ):

            return _generate_reply_text()

        # ----------------------------------------------------
        # PUT GENERATED REPLY INTO GMAIL
        # ----------------------------------------------------

        if action in (
            "reply",
            "write_reply",
            "compose_reply",
        ):

            return _reply_to_current_email()

        # ----------------------------------------------------
        # AUTONOMOUS REPLY / COMPOSE
        # ----------------------------------------------------
        #
        # This action lets JEEV complete the reply workflow itself:
        # open Gmail -> obtain the latest/current email -> generate a reply
        # -> place the reply into Gmail.
        #
        # IMPORTANT: this action is compose-only. It NEVER sends the email.
        # Sending remains a separate explicit action.
        if action in (
            "auto_reply",
            "autonomous_reply",
            "compose_auto_reply",
            "reply_on_its_own",
        ):
            if not _CURRENT_EMAIL:
                opened = _open_gmail()
                if isinstance(opened, str) and any(
                    word in opened.lower()
                    for word in ("failed", "error")
                ):
                    return opened

                latest = _read_latest()
                if isinstance(latest, str) and any(
                    word in latest.lower()
                    for word in ("failed", "error", "no email")
                ):
                    return latest

            generated = _generate_reply_text()
            if not _PENDING_REPLY:
                return generated

            composed = _reply_to_current_email()
            return (
                f"{composed}\n"
                "Reply composed in Gmail. It has NOT been sent."
            )

        # ----------------------------------------------------
        # SEND
        # ----------------------------------------------------

        if action in (
            "send",
            "send_reply",
            "send_email",
        ):

            return _send_current_reply()

        # ----------------------------------------------------
        # CLOSE
        # ----------------------------------------------------

        if action in (
            "close",
            "close_gmail",
            "stop",
        ):

            return _close()

        return (
            f"Unknown Gmail action: {action}. "
            "Supported actions are setup, open, latest, "
            "search, read_search, select, current, "
            "generate_reply, reply, auto_reply, send, and close."
        )

    except KeyboardInterrupt:

        raise

    except Exception as exc:

        _log(
            "Gmail controller error:",
            repr(exc),
        )

        return (
            f"Gmail control failed: {exc}"
        )


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    print(
        gmail_control(
            {
                "action": "setup"
            }
        )
    )