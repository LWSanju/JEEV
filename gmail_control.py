
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
from urllib.parse import quote


"""
JEEV MARK I
GMAIL CONTROL
============

Persistent browser-based Gmail controller.

DESIGN
------
JEEV controls Gmail through a dedicated browser profile.

Browser priority:
    1. Brave
    2. Chrome
    3. Firefox
    4. Opera

Edge is intentionally not used.

Authentication:
    - User signs into Gmail normally.
    - No Gmail password is stored.
    - No Gmail OAuth token is stored.
    - No Gmail API credentials are required.

IMPORTANT
---------
The Gmail UI is dynamic. Gmail frequently re-renders search-result rows.

Therefore this controller does NOT rely only on a saved row index.

The workflow is:

    search
       |
       v
    collect visible result identity
       |
       v
    locate matching row again
       |
       v
    click the actual message row
       |
       v
    verify Gmail opened a conversation
       |
       v
    extract sender / subject / body
       |
       v
    store CURRENT_EMAIL

Supported actions:

    setup
    connect
    open
    latest
    read_latest

    search
    search_mail
    find
    find_email

    read_search
    search_and_read

    search_and_open
    open_by_query
    find_and_open

    select
    select_email
    open_email

    current
    current_email
    selected

    generate_reply
    draft_reply

    reply
    write_reply
    compose_reply

    auto_reply
    autonomous_reply

    send
    send_reply
    send_email

    close
    close_gmail
    stop
"""


# ============================================================================
# PATHS
# ============================================================================

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _THIS_DIR.parent

_GMAIL_DATA_DIR = _PROJECT_DIR / ".jeev_gmail"
_PROFILE_DIR = _GMAIL_DATA_DIR / "browser_profile"
_CONFIG_FILE = _GMAIL_DATA_DIR / "gmail_config.json"

_GMAIL_DATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

_PROFILE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================================
# BROWSER SETTINGS
# ============================================================================

_REMOTE_DEBUG_PORT = 9227

_GMAIL_URL = (
    "https://mail.google.com/mail/u/0/#inbox"
)

_SEARCH_WAIT_SECONDS = 8.0
_OPEN_WAIT_SECONDS = 8.0
_UI_RETRY_COUNT = 3

_BROWSER_PROCESS: Optional[subprocess.Popen] = None

_PLAYWRIGHT = None
_CONNECTION = None
_CONTEXT = None
_PAGE = None

_CURRENT_EMAIL: Dict[str, Any] = {}

_SEARCH_RESULTS: List[Dict[str, Any]] = []

_PENDING_REPLY = ""


# ============================================================================
# LOGGING
# ============================================================================

def _log(*args: Any) -> None:
    print(
        "[JEEV][Gmail]",
        *args,
    )


# ============================================================================
# CONFIG
# ============================================================================

def _load_config() -> Dict[str, Any]:

    try:

        if _CONFIG_FILE.exists():

            with _CONFIG_FILE.open(
                "r",
                encoding="utf-8",
            ) as file:

                data = json.load(file)

            if isinstance(data, dict):
                return data

    except Exception as exc:

        _log(
            "Could not load Gmail config:",
            repr(exc),
        )

    return {}


def _save_config(
    data: Dict[str, Any],
) -> bool:

    try:

        _GMAIL_DATA_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = _CONFIG_FILE.with_suffix(
            ".tmp"
        )

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False,
            )

        temporary.replace(
            _CONFIG_FILE
        )

        return True

    except Exception as exc:

        _log(
            "Could not save Gmail config:",
            repr(exc),
        )

        return False


def _get_email_id() -> str:

    config = _load_config()

    return str(
        config.get(
            "email",
            "",
        )
        or ""
    ).strip()


def _setup_email_id() -> str:

    existing = _get_email_id()

    if existing:
        return existing

    print()
    print("=" * 64)
    print(" JEEV GMAIL SETUP")
    print("=" * 64)
    print()
    print(
        "Enter the Gmail address this JEEV installation uses."
    )
    print(
        "This is only stored locally as an identifier."
    )
    print(
        "JEEV does not ask for or store your Gmail password."
    )
    print()

    try:

        email = input(
            "Gmail address: "
        ).strip()

    except (
        EOFError,
        KeyboardInterrupt,
    ):

        return ""

    if not email:
        return ""

    if not re.match(
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        email,
    ):

        print(
            "That does not look like a valid email address."
        )

        return ""

    config = _load_config()

    config["email"] = email

    if not _save_config(config):
        return ""

    _log(
        "Gmail address saved locally:",
        email,
    )

    return email


# ============================================================================
# BROWSER DETECTION
# ============================================================================

def _browser_candidates() -> List[Dict[str, Any]]:

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

    bases = [
        Path(program_files),
        Path(program_files_x86),
    ]

    candidates: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # BRAVE
    # ------------------------------------------------------------------

    brave_paths = [
        Path(local_app_data)
        / "BraveSoftware"
        / "Brave-Browser"
        / "Application"
        / "brave.exe",
    ]

    brave_paths.extend(
        base
        / "BraveSoftware"
        / "Brave-Browser"
        / "Application"
        / "brave.exe"
        for base in bases
    )

    candidates.append(
        {
            "name": "Brave",
            "engine": "chromium",
            "executables": brave_paths,
        }
    )

    # ------------------------------------------------------------------
    # CHROME
    # ------------------------------------------------------------------

    chrome_paths = [
        Path(local_app_data)
        / "Google"
        / "Chrome"
        / "Application"
        / "chrome.exe",
    ]

    chrome_paths.extend(
        base
        / "Google"
        / "Chrome"
        / "Application"
        / "chrome.exe"
        for base in bases
    )

    candidates.append(
        {
            "name": "Chrome",
            "engine": "chromium",
            "executables": chrome_paths,
        }
    )

    # ------------------------------------------------------------------
    # FIREFOX
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # OPERA
    # ------------------------------------------------------------------

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

    if os.name != "nt":

        return {
            "name": "",
            "engine": "",
            "exe": "",
        }

    for browser in _browser_candidates():

        for executable in browser["executables"]:

            try:

                if executable.is_file():

                    _log(
                        "Browser detected:",
                        browser["name"],
                    )

                    return {
                        "name": browser["name"],
                        "engine": browser["engine"],
                        "exe": str(executable),
                    }

            except Exception:

                pass

    return {
        "name": "",
        "engine": "",
        "exe": "",
    }


# ============================================================================
# PORT
# ============================================================================

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


# ============================================================================
# PLAYWRIGHT
# ============================================================================

def _require_playwright():

    try:

        from playwright.sync_api import sync_playwright

        return sync_playwright

    except ImportError as exc:

        venv_python = (
            _PROJECT_DIR
            / ".venv"
            / "Scripts"
            / "python.exe"
        )

        command = (
            f'"{venv_python}" -m pip install playwright'
            if venv_python.exists()
            else
            r'.\.venv\Scripts\python.exe -m pip install playwright'
        )

        raise RuntimeError(
            "Gmail control requires Playwright.\n\n"
            "Install it with:\n"
            + command
        ) from exc


# ============================================================================
# CHROMIUM LAUNCH
# ============================================================================

def _launch_independent_chromium(
    browser_exe: str,
    browser_name: str,
) -> bool:
    """Launch JEEV's own persistent Chromium context.

    This intentionally does NOT use CDP or port 9227.  The browser
    context is owned directly by Playwright and uses JEEV's dedicated
    profile, so normal Brave sessions are not touched.
    """
    global _PLAYWRIGHT
    global _CONTEXT
    global _PAGE
    global _BROWSER_PROCESS

    sync_playwright = _require_playwright()

    try:
        if _PLAYWRIGHT is None:
            _PLAYWRIGHT = sync_playwright().start()

        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        # If a previous JEEV context is still alive, reuse it.
        if _CONTEXT is not None:
            try:
                pages = _CONTEXT.pages
                _PAGE = pages[0] if pages else _CONTEXT.new_page()
                if _PAGE is not None and not _PAGE.is_closed():
                    return True
            except Exception:
                _CONTEXT = None
                _PAGE = None

        _log(
            "Starting JEEV Gmail browser directly with Playwright:",
            browser_name,
        )

        _CONTEXT = _PLAYWRIGHT.chromium.launch_persistent_context(
            user_data_dir=str(_PROFILE_DIR),
            executable_path=browser_exe,
            headless=False,
            viewport=None,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-session-crashed-bubble",
                "--disable-features=Translate",
            ],
        )

        pages = _CONTEXT.pages
        if pages:
            _PAGE = pages[0]
        else:
            _PAGE = _CONTEXT.new_page()

        _BROWSER_PROCESS = None
        _log("JEEV Gmail browser started without CDP.")
        return _PAGE is not None and not _PAGE.is_closed()

    except Exception as exc:
        _log(
            "Direct Playwright browser launch failed:",
            repr(exc),
        )
        _PAGE = None
        _CONTEXT = None
        return False


def _connect_chromium() -> bool:
    """Compatibility wrapper: direct launch replaces CDP connection."""
    if _PAGE is not None:
        try:
            if not _PAGE.is_closed():
                return True
        except Exception:
            pass

    browser = _find_installed_browser()
    if not browser.get("exe"):
        return False

    return _launch_independent_chromium(
        browser["exe"],
        browser.get("name", "Chromium"),
    )


def _start_browser() -> bool:
    global _PAGE

    if _PAGE is not None:
        try:
            if not _PAGE.is_closed():
                return True
        except Exception:
            _PAGE = None

    browser = _find_installed_browser()

    if not browser.get("name") or not browser.get("exe"):
        _log("No supported browser was found.")
        return False

    if browser.get("engine") == "chromium":
        return _launch_independent_chromium(
            browser["exe"],
            browser["name"],
        )

    if browser.get("engine") == "firefox":
        _log("Firefox was detected, but Gmail DOM automation requires Chromium.")
        return False

    return False


def _page():

    if not _start_browser():

        return None

    return _PAGE


# ============================================================================
# GMAIL
# ============================================================================

def _ensure_gmail() -> bool:

    page = _page()

    if page is None:

        return False

    try:

        if "mail.google.com" not in (
            page.url or ""
        ):

            page.goto(
                _GMAIL_URL,
                wait_until="domcontentloaded",
                timeout=30000,
            )

        time.sleep(1.5)

        return True

    except Exception as exc:

        _log(
            "Could not open Gmail:",
            repr(exc),
        )

        return False


def _gmail_logged_in() -> bool:
    """Return True only after Gmail has finished loading its authenticated UI.

    Gmail can take several seconds to restore the JEEV persistent profile.
    The old implementation checked too early and could report a false
    logout while Gmail was still loading.
    """
    page = _page()
    if page is None:
        return False

    deadline = time.time() + 12.0
    selectors = [
        'input[aria-label="Search mail"]',
        'input[placeholder*="Search mail"]',
        'input[name="q"]',
        '[role="main"]',
        'div[role="navigation"]',
        'tr.zA',
    ]

    while time.time() < deadline:
        try:
            url = page.url or ""
            if "accounts.google.com" in url:
                return False

            if "mail.google.com" not in url:
                time.sleep(0.35)
                continue

            for selector in selectors:
                try:
                    loc = page.locator(selector).first
                    if loc.is_visible(timeout=700):
                        return True
                except Exception:
                    pass

            # Gmail sometimes exposes its authenticated shell before the
            # search box has been painted. These markers are also useful
            # during the transition from the loading page to the inbox.
            try:
                body = _clean_text(page.locator("body").inner_text(timeout=700)).casefold()
                if "compose" in body or "inbox" in body or "sent" in body:
                    return True
                if "sign in" in body and "accounts.google.com" in (page.url or ""):
                    return False
            except Exception:
                pass

        except Exception:
            pass

        time.sleep(0.4)

    return False


# ============================================================================
# TEXT
# ============================================================================

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
                timeout=2000
            )
        )

    except Exception:

        return ""


# ============================================================================
# SEARCH BOX
# ============================================================================

def _find_search_box():

    page = _page()

    if page is None:

        return None

    selectors = [
        'input[aria-label="Search mail"]',
        'input[placeholder="Search mail"]',
        'input[placeholder*="Search mail"]',
        'input[name="q"]',
        'input[role="combobox"]',
    ]

    for selector in selectors:

        try:

            locator = (
                page
                .locator(selector)
                .first
            )

            if locator.is_visible(
                timeout=1200
            ):

                return locator

        except Exception:

            pass

    return None


# ============================================================================
# MESSAGE ROW DISCOVERY
# ============================================================================

def _message_rows():

    page = _page()

    if page is None:

        return None

    selectors = [
        "tr.zA",
        'tr[role="row"]',
        '[role="main"] tr',
    ]

    for selector in selectors:

        try:

            rows = page.locator(selector)

            if rows.count():

                return rows

        except Exception:

            pass

    return None


def _extract_sender(row) -> str:
    """Extract the real sender email/address from a Gmail result row."""
    selectors = [
        "span[email]",
        "[email]",
        ".yW",
        ".yX",
        ".zF",
    ]
    for selector in selectors:
        try:
            loc = row.locator(selector).first
            if not loc.count():
                continue
            email = (loc.get_attribute("email") or "").strip()
            text = _clean_text(email or _visible_text(loc))
            if text:
                # Prefer an actual address if Gmail exposes one.
                match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
                return match.group(0) if match else text
        except Exception:
            pass
    return ""


def _extract_subject(row) -> str:
    selectors = [
        ".bog",
        ".y6",
        "[data-thread-id]",
    ]
    for selector in selectors:
        try:
            loc = row.locator(selector).first
            if not loc.count():
                continue
            text = _visible_text(loc)
            if text:
                return text
        except Exception:
            pass
    return ""


def _result_identity(sender: str, subject: str, snippet: str) -> str:
    return "|".join([
        _clean_text(sender).casefold(),
        _clean_text(subject).casefold(),
        _clean_text(snippet).casefold()[:300],
    ])


def _row_metadata(row, text: str) -> Dict[str, str]:
    """Collect stable-ish attributes used for local Gmail operator filtering."""
    values = [text]
    for attr in ("aria-label", "data-tooltip", "title", "class"):
        try:
            value = row.get_attribute(attr)
            if value:
                values.append(value)
        except Exception:
            pass
    try:
        values.extend(row.locator("[aria-label]").evaluate_all(
            "els => els.map(e => e.getAttribute('aria-label') || '')"
        ))
    except Exception:
        pass
    try:
        values.extend(row.locator("[title]").evaluate_all(
            "els => els.map(e => e.getAttribute('title') || '')"
        ))
    except Exception:
        pass
    return {"text": _clean_text(" ".join(str(v) for v in values if v))}


def _collect_message_rows() -> List[Dict[str, Any]]:
    page = _page()
    if page is None:
        return []
    rows = _message_rows()
    if rows is None:
        return []
    try:
        count = min(rows.count(), 100)
    except Exception:
        return []

    results: List[Dict[str, Any]] = []
    for index in range(count):
        try:
            row = rows.nth(index)
            if not row.is_visible(timeout=500):
                continue
            text = _visible_text(row)
            if not text:
                continue
            sender = _extract_sender(row)
            subject = _extract_subject(row)
            if not sender:
                # Some Gmail variants expose the sender only in aria/title.
                meta = _row_metadata(row, text)["text"]
                match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", meta, re.I)
                sender = match.group(0) if match else ""
            if not subject:
                subject = text
            meta = _row_metadata(row, text)
            results.append({
                "index": len(results) + 1,
                "sender": sender,
                "subject": subject,
                "snippet": text,
                "metadata": meta["text"],
                "identity": _result_identity(sender, subject, text),
                "_locator_index": index,
            })
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# Gmail query parsing / local verification
# ---------------------------------------------------------------------------

_SEARCH_OPERATORS = {
    "from", "to", "cc", "bcc", "subject", "filename", "file", "in",
    "label", "is", "has", "after", "before", "older", "newer",
    "older_than", "newer_than",
}


def _tokenize_gmail_query(query: str) -> List[str]:
    # Gmail allows quoted phrases. Preserve them as one token while keeping
    # operator:value tokens intact.
    return re.findall(r'(?:(?:[^\s"]+):"[^"]*"|(?:[^\s"]+):[^\s]+|"[^"]*"|\S+)', query.strip())


def _parse_gmail_query(query: str) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {"positive": [], "negative": []}
    for raw in _tokenize_gmail_query(query):
        token = raw.strip()
        if not token:
            continue
        negative = token.startswith("-")
        if negative:
            token = token[1:]
        if ":" in token:
            key, value = token.split(":", 1)
            key = key.casefold().strip()
            value = value.strip().strip('"').strip()
            if key in _SEARCH_OPERATORS and value:
                parsed["negative" if negative else "positive"].append((key, value))
                continue
        phrase = token.strip('"')
        if phrase:
            parsed["negative" if negative else "positive"].append(("text", phrase))
    return parsed


def _contains(value: str, wanted: str) -> bool:
    return _clean_text(wanted).casefold() in _clean_text(value).casefold()


def _operator_matches(item: Dict[str, Any], key: str, wanted: str) -> bool:
    sender = str(item.get("sender", "") or "")
    subject = str(item.get("subject", "") or "")
    snippet = str(item.get("snippet", "") or "")
    metadata = str(item.get("metadata", "") or "")
    combined = " ".join((sender, subject, snippet, metadata))
    wanted_cf = wanted.casefold().strip()

    if key == "from":
        # Exact address matching is deliberate: from:x must not match a
        # different sender merely because x occurs in the row text.
        addresses = re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", sender, re.I)
        return any(a.casefold() == wanted_cf for a in addresses) or sender.casefold().strip() == wanted_cf
    if key in ("to", "cc", "bcc"):
        return _contains(combined, wanted)
    if key == "subject":
        return _contains(subject, wanted)
    if key in ("filename", "file"):
        return _contains(combined, wanted)
    if key == "label":
        return _contains(combined, wanted) or _contains(metadata, wanted)
    if key == "in":
        if wanted_cf in ("anywhere", "all"):
            return True
        return _contains(combined, wanted)
    if key == "is":
        # Gmail exposes unread/starred/etc. state through row classes and
        # aria labels. This is a best-effort local verification.
        if wanted_cf in ("unread", "read"):
            unread = "zE" in metadata or "unread" in metadata.casefold()
            return unread if wanted_cf == "unread" else not unread
        if wanted_cf in ("starred", "star"):
            return "starred" in metadata.casefold() or "star" in metadata.casefold()
        if wanted_cf in ("important",):
            return "important" in metadata.casefold()
        return _contains(combined, wanted)
    if key in ("after", "before", "older", "newer", "older_than", "newer_than"):
        # Date operators are already enforced by Gmail's server search. Do
        # not reject a row locally when Gmail has returned it.
        return True
    return True


def _apply_local_gmail_filters(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    parsed = _parse_gmail_query(query)
    positive = parsed["positive"]
    negative = parsed["negative"]
    filtered: List[Dict[str, Any]] = []

    for item in results:
        if any(not _operator_matches(item, k, v) for k, v in positive):
            continue
        if any(_operator_matches(item, k, v) for k, v in negative):
            continue
        filtered.append(item)

    # Plain text terms should all occur somewhere in the visible result.
    for item in filtered:
        pass
    return filtered


def _wait_for_filtered_search_results(query: str) -> List[Dict[str, Any]]:
    deadline = time.time() + _SEARCH_WAIT_SECONDS
    best: List[Dict[str, Any]] = []
    while time.time() < deadline:
        raw = _collect_message_rows()
        filtered = _apply_local_gmail_filters(raw, query)
        if filtered:
            best = filtered
            # Allow Gmail to finish rendering before returning.
            time.sleep(0.5)
            newer = _apply_local_gmail_filters(_collect_message_rows(), query)
            if newer:
                best = newer
            break
        time.sleep(0.35)
    for i, item in enumerate(best, 1):
        item["index"] = i
    return best


# ============================================================================
# WAIT FOR SEARCH RESULTS
# ============================================================================

def _wait_for_search_results(
    previous_url: str = "",
) -> List[Dict[str, Any]]:

    deadline = (
        time.time()
        + _SEARCH_WAIT_SECONDS
    )

    best: List[Dict[str, Any]] = []

    while time.time() < deadline:

        results = _collect_message_rows()

        if results:

            best = results

            # Gmail may initially render one partial row
            # and then populate the rest. Give it a little time.
            if len(results) >= 1:

                time.sleep(0.6)

                newer = _collect_message_rows()

                if newer:

                    best = newer

                return best

        time.sleep(0.35)

    return best


# ============================================================================
# RESULT MATCHING
# ============================================================================

def _score_result_match(
    wanted: Dict[str, Any],
    candidate: Dict[str, Any],
) -> int:

    score = 0

    wanted_sender = _clean_text(
        wanted.get("sender", "")
    ).casefold()

    wanted_subject = _clean_text(
        wanted.get("subject", "")
    ).casefold()

    wanted_snippet = _clean_text(
        wanted.get("snippet", "")
    ).casefold()

    candidate_sender = _clean_text(
        candidate.get("sender", "")
    ).casefold()

    candidate_subject = _clean_text(
        candidate.get("subject", "")
    ).casefold()

    candidate_snippet = _clean_text(
        candidate.get("snippet", "")
    ).casefold()

    if (
        wanted_sender
        and candidate_sender
    ):

        if wanted_sender == candidate_sender:

            score += 100

        elif (
            wanted_sender in candidate_sender
            or candidate_sender in wanted_sender
        ):

            score += 50

    if (
        wanted_subject
        and candidate_subject
    ):

        if wanted_subject == candidate_subject:

            score += 100

        elif (
            wanted_subject in candidate_subject
            or candidate_subject in wanted_subject
        ):

            score += 60

    if wanted_snippet:

        words = [
            word
            for word in wanted_snippet.split()
            if len(word) > 3
        ]

        for word in words[:15]:

            if word in candidate_snippet:

                score += 2

    return score


def _find_best_matching_result(
    wanted: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    if not results:

        return None

    wanted_identity = wanted.get(
        "identity",
        "",
    )

    # Exact identity first.
    for result in results:

        if (
            wanted_identity
            and result.get("identity")
            == wanted_identity
        ):

            return result

    scored = [
        (
            _score_result_match(
                wanted,
                result,
            ),
            result,
        )
        for result in results
    ]

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    if not scored:

        return None

    best_score, best_result = scored[0]

    if best_score <= 0:

        return None

    return best_result


# ============================================================================
# OPEN RESULT - ROBUST
# ============================================================================

def _click_row(row) -> bool:
    """Open a Gmail result without ever clicking its selection checkbox."""
    try:
        row.scroll_into_view_if_needed(timeout=2500)
    except Exception:
        pass

    # Gmail's subject span/cell is the safest target.  Never click the row
    # itself: its left edge is occupied by the selection checkbox.
    selectors = [
        '.bog',
        '.y6',
        'td.xY .bog',
        'td.xY .y6',
        'td.xY',
        'td.xW',
        'td.a4W',
        '[role="gridcell"] .bog',
        '[role="gridcell"] .y6',
    ]
    for selector in selectors:
        try:
            loc = row.locator(selector)
            for i in range(loc.count()):
                target = loc.nth(i)
                if not target.is_visible(timeout=500):
                    continue
                aria = (target.get_attribute("aria-label") or "").casefold()
                cls = (target.get_attribute("class") or "").casefold()
                if "checkbox" in aria or "select" in aria or "checkbox" in cls:
                    continue
                target.scroll_into_view_if_needed(timeout=1000)
                target.click(timeout=5000, force=True)
                return True
        except Exception:
            continue

    # If the subject is represented by an anchor, use it only when it is not
    # a checkbox/select control.
    try:
        links = row.locator('a, [role="link"]')
        for i in range(links.count()):
            link = links.nth(i)
            if not link.is_visible(timeout=500):
                continue
            aria = (link.get_attribute("aria-label") or "").casefold()
            if "checkbox" in aria or "select" in aria:
                continue
            text = _visible_text(link)
            href = (link.get_attribute("href") or "").strip()
            if text or href:
                link.click(timeout=5000, force=True)
                return True
    except Exception:
        pass

    # Last resort: click the center of the subject-bearing cell, never the
    # left side of the row.
    try:
        cell = row.locator('td.xY, td.xW, td.a4W').last
        if cell.count() and cell.is_visible(timeout=500):
            box = cell.bounding_box()
            page = _page()
            if box and page:
                page.mouse.click(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.5)
                return True
    except Exception:
        pass

    return False


def _conversation_is_open() -> bool:
    """Return True only when Gmail is displaying an actual conversation."""
    page = _page()
    if page is None:
        return False
    try:
        url = page.url or ""
        # Gmail may open a thread from search using either:
        #   #inbox/<thread-id>
        #   #all/<thread-id>
        #   #search/<query>/<thread-id>
        # Therefore #search by itself is not enough to say that we are still
        # on the results page. What matters is that a thread-id follows it.
        thread_route = bool(re.search(
            r"#(?:inbox|all|sent|important|starred|drafts|spam|trash|scheduled)/[^/?#]+$",
            url, re.IGNORECASE
        )) or bool(re.search(
            r"#search/[^#]*/[A-Za-z0-9_-]{8,}(?:[/?#].*)?$",
            url, re.IGNORECASE
        ))
        if not thread_route:
            return False

        has_heading = False
        for selector in ("h2.hP", 'h2[role="heading"]', '[role="main"] h2.hP'):
            try:
                loc = page.locator(selector).first
                if loc.count() and loc.is_visible(timeout=500) and _visible_text(loc):
                    has_heading = True
                    break
            except Exception:
                pass

        if not has_heading:
            return False

        for selector in ("div.a3s.aiL", "div.a3s", '[role="main"] div.a3s'):
            try:
                locators = page.locator(selector)
                for i in range(locators.count() - 1, -1, -1):
                    loc = locators.nth(i)
                    if loc.is_visible(timeout=500) and len(_visible_text(loc)) >= 3:
                        return True
            except Exception:
                pass
        return False
    except Exception:
        return False

def _wait_until_conversation_open() -> bool:

    deadline = (
        time.time()
        + _OPEN_WAIT_SECONDS
    )

    while time.time() < deadline:

        if _conversation_is_open():

            return True

        time.sleep(0.35)

    return False


def _reacquire_result(
    wanted: Dict[str, Any],
):

    results = _collect_message_rows()

    if not results:

        return None

    match = _find_best_matching_result(
        wanted,
        results,
    )

    if match:

        return match

    # If the original result is still present by index,
    # use it only as a final fallback.
    original_index = wanted.get(
        "_locator_index"
    )

    if isinstance(
        original_index,
        int,
    ):

        for result in results:

            if (
                result.get("_locator_index")
                == original_index
            ):

                return result

    return None


def _open_result(
    index: int,
) -> str:

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

    if (
        index < 1
        or index > len(_SEARCH_RESULTS)
    ):

        return (
            f"I found {len(_SEARCH_RESULTS)} emails. "
            f"Please choose a number from 1 to "
            f"{len(_SEARCH_RESULTS)}."
        )

    wanted = dict(
        _SEARCH_RESULTS[index - 1]
    )

    page = _page()

    if page is None:

        return (
            "Gmail automation is not available."
        )

    # --------------------------------------------------------------
    # Make sure we are still on Gmail search/inbox.
    # --------------------------------------------------------------

    if not _ensure_gmail():

        return (
            "I could not access Gmail."
        )

    # --------------------------------------------------------------
    # Re-find the actual row immediately before clicking.
    # --------------------------------------------------------------

    for attempt in range(
        1,
        _UI_RETRY_COUNT + 1,
    ):

        try:

            candidate = _reacquire_result(
                wanted
            )

            if candidate is None:

                time.sleep(0.5)

                continue

            rows = _message_rows()

            if rows is None:

                continue

            locator_index = candidate.get(
                "_locator_index"
            )

            if not isinstance(
                locator_index,
                int,
            ):

                continue

            if (
                locator_index
                >= rows.count()
            ):

                continue

            row = rows.nth(
                locator_index
            )

            # Capture the current URL so we can verify
            # that Gmail actually navigated.
            before_url = page.url or ""

            if not _click_row(row):

                _log(
                    "Could not click result on attempt",
                    attempt,
                )

                continue

            if _wait_until_conversation_open():

                # Give Gmail a moment to finish rendering
                # the message body.
                time.sleep(0.6)

                captured = _capture_current_email()

                if captured.startswith(
                    "Email:"
                ):

                    return captured

                if (
                    page.url
                    and page.url != before_url
                ):

                    captured = _capture_current_email()

                    if captured.startswith(
                        "Email:"
                    ):

                        return captured

            # If the click didn't open the message,
            # go back to the search results and try again.
            try:

                page.go_back(
                    wait_until="domcontentloaded",
                    timeout=10000,
                )

                time.sleep(1.0)

            except Exception:

                pass

        except Exception as exc:

            _log(
                "Open attempt failed:",
                repr(exc),
            )

            try:

                if _conversation_is_open():

                    page.go_back(
                        wait_until="domcontentloaded",
                        timeout=10000,
                    )

                    time.sleep(1.0)

            except Exception:

                pass

    return (
        "I found the email, but Gmail did not open "
        "the message conversation after multiple attempts. "
        "The result is still available; try opening it again."
    )


# ============================================================================
# CAPTURE OPENED EMAIL
# ============================================================================

def _capture_current_email() -> str:
    """Capture only the opened Gmail conversation, never the whole page."""
    global _CURRENT_EMAIL
    page = _page()
    if page is None:
        return "Gmail automation is not available."
    if not _conversation_is_open():
        return "Gmail is not currently displaying an opened email."

    subject = ""
    for selector in ("h2.hP", 'h2[role="heading"]', '[role="main"] h2.hP'):
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible(timeout=700):
                subject = _visible_text(loc)
                if subject:
                    break
        except Exception:
            pass

    sender = ""
    for selector in ("span[email]", ".gD[email]", ".gD", "[email]"):
        try:
            loc = page.locator(selector).first
            if loc.count() and loc.is_visible(timeout=700):
                sender = _clean_text(loc.get_attribute("email") or _visible_text(loc))
                if sender:
                    break
        except Exception:
            pass

    message_text = ""
    for selector in ("div.a3s.aiL", "div.a3s", '[role="main"] div.a3s'):
        try:
            locators = page.locator(selector)
            for i in range(locators.count() - 1, -1, -1):
                loc = locators.nth(i)
                if loc.is_visible(timeout=700):
                    candidate = _visible_text(loc)
                    if len(candidate) > len(message_text):
                        message_text = candidate
        except Exception:
            pass

    if not message_text:
        return (
            "I opened the Gmail conversation, but Gmail did not expose "
            "the actual message body yet."
        )

    subject = subject or str(_CURRENT_EMAIL.get("subject", "") or "")
    sender = sender or str(_CURRENT_EMAIL.get("sender", "") or "")
    _CURRENT_EMAIL = {
        "sender": sender,
        "subject": subject,
        "body": message_text,
        "opened_at": time.time(),
        "url": page.url or "",
    }

    spoken = message_text[:12000]
    if len(message_text) > 12000:
        spoken += " ..."
    return f"Email: {subject or 'this email'}" + (f" from {sender}" if sender else "") + f".\n\n{spoken}"

# ============================================================================
# OPEN GMAIL
# ============================================================================

def _open_gmail() -> str:

    email = _setup_email_id()

    if not email:

        return (
            "I could not save the Gmail address."
        )

    if not _ensure_gmail():

        return (
            "I could not open Gmail."
        )

    if not _gmail_logged_in():

        return (
            f"Gmail is open for {email}. "
            "Please sign into that Gmail account "
            "in the JEEV browser profile."
        )

    return (
        f"Gmail is open for {email}."
    )


# ============================================================================
# LATEST
# ============================================================================

def _read_latest() -> str:

    global _SEARCH_RESULTS

    if not _ensure_gmail():

        return (
            "I could not open Gmail."
        )

    if not _gmail_logged_in():

        return (
            "Gmail is not signed in. "
            "Please sign into Gmail first."
        )

    page = _page()

    if page is None:

        return (
            "Gmail automation is not available."
        )

    try:

        page.goto(
            _GMAIL_URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )

        time.sleep(1.5)

    except Exception:

        pass

    _SEARCH_RESULTS = (
        _wait_for_search_results()
    )

    if not _SEARCH_RESULTS:

        return (
            "I could not find visible emails in Gmail."
        )

    return _open_result(1)


# ============================================================================
# SEARCH
# ============================================================================

def _search_gmail(query: str) -> str:
    global _SEARCH_RESULTS
    global _CURRENT_EMAIL

    query = _clean_text(query)
    if not query:
        return "No Gmail search query was provided."
    if not _ensure_gmail():
        return "I could not open Gmail."
    if not _gmail_logged_in():
        return "Gmail is not signed in. Please sign into Gmail first."

    page = _page()
    if page is None:
        return "Gmail automation is not available."

    # Force Gmail to a known top-level state first.  Hash-only navigation can
    # otherwise leave the old conversation DOM in place in a persistent Brave
    # profile, which makes row detection race with Gmail's SPA renderer.
    try:
        page.goto("https://mail.google.com/mail/u/0/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(1.2)
    except Exception:
        pass

    search_url = "https://mail.google.com/mail/u/0/#search/" + quote(query, safe="")
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1.0)
        # Wait for Gmail's hash route to settle.
        deadline = time.time() + 8.0
        wanted_route = "#search/"
        while time.time() < deadline and wanted_route not in (page.url or ""):
            time.sleep(0.25)
        time.sleep(1.0)
    except Exception as exc:
        return f"Gmail search failed: {exc}"

    _SEARCH_RESULTS = _wait_for_filtered_search_results(query)
    if not _SEARCH_RESULTS:
        # One final DOM refresh without changing the query.
        try:
            page.reload(wait_until="domcontentloaded", timeout=30000)
            time.sleep(2.0)
        except Exception:
            pass
        _SEARCH_RESULTS = _wait_for_filtered_search_results(query)

    if not _SEARCH_RESULTS:
        return f"I could not find visible Gmail results for '{query}'."

    _CURRENT_EMAIL = {}
    lines = []
    for i, item in enumerate(_SEARCH_RESULTS, 1):
        sender = item.get("sender", "") or "Unknown sender"
        subject = item.get("subject", "") or "(no subject)"
        snippet = item.get("snippet", "") or ""
        if len(snippet) > 180:
            snippet = snippet[:180] + "..."
        lines.append(f"{i}. {sender} — {subject}" + (f". {snippet}" if snippet else ""))

    return (
        f"I found {len(_SEARCH_RESULTS)} matching emails.\n"
        + "\n".join(lines)
        + "\nTell me the number of the email you want to open."
    )


# ============================================================================
# SEARCH + READ
# ============================================================================

def _read_search(
    query: str,
) -> str:

    result = _search_gmail(query)

    if not _SEARCH_RESULTS:

        return result

    # If exactly one message matches,
    # automatically open it.
    if len(_SEARCH_RESULTS) == 1:

        return _open_result(1)

    return result


# ============================================================================
# SEARCH + OPEN
# ============================================================================

def _search_and_open(
    query: str,
) -> str:

    result = _search_gmail(query)

    if not _SEARCH_RESULTS:

        return result

    # If one result exists, open it immediately.
    if len(_SEARCH_RESULTS) == 1:

        return _open_result(1)

    # If multiple results exist, choose the strongest
    # result based on the natural-language query.
    #
    # We intentionally do not blindly open result #1
    # because that could open the wrong message.

    query_lower = query.casefold()

    scored = []

    for index, item in enumerate(
        _SEARCH_RESULTS,
        1,
    ):

        haystack = " ".join(
            [
                str(
                    item.get(
                        "sender",
                        "",
                    )
                ),
                str(
                    item.get(
                        "subject",
                        "",
                    )
                ),
                str(
                    item.get(
                        "snippet",
                        "",
                    )
                ),
            ]
        ).casefold()

        score = 0

        for word in re.findall(
            r"[a-z0-9@._+-]+",
            query_lower,
        ):

            if len(word) >= 3 and word in haystack:

                score += 1

        scored.append(
            (
                score,
                index,
                item,
            )
        )

    scored.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    if scored and scored[0][0] > 0:

        # Only automatically open if the best match
        # is meaningfully stronger than the next result.
        best_score = scored[0][0]

        second_score = (
            scored[1][0]
            if len(scored) > 1
            else 0
        )

        if (
            best_score >= 2
            and best_score > second_score
        ):

            return _open_result(
                scored[0][1]
            )

    return (
        result
        + "\nI found multiple possible matches, "
        "so I did not open an ambiguous message. "
        "Tell me the number you want."
    )


# ============================================================================
# CURRENT EMAIL
# ============================================================================

def _current_email() -> str:

    if not _CURRENT_EMAIL:

        return (
            "There is no selected email yet."
        )

    subject = (
        _CURRENT_EMAIL.get(
            "subject",
            "",
        )
        or "(no subject)"
    )

    sender = (
        _CURRENT_EMAIL.get(
            "sender",
            "",
        )
        or "unknown sender"
    )

    body = (
        _CURRENT_EMAIL.get(
            "body",
            "",
        )
        or ""
    )

    if len(body) > 12000:

        body = (
            body[:12000]
            + " ..."
        )

    return (
        f"Selected email: {subject}, "
        f"from {sender}.\n\n"
        f"{body}"
    )


# ============================================================================
# REPLY
# ============================================================================

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

            loc = (
                page
                .locator(selector)
                .last
            )

            if (
                loc.count()
                and loc.is_visible(
                    timeout=1000
                )
            ):

                return loc

        except Exception:

            pass

    return None


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

            loc = (
                page
                .locator(selector)
                .last
            )

            if (
                loc.count()
                and loc.is_visible(
                    timeout=1000
                )
            ):

                return loc

        except Exception:

            pass

    return None


def _generate_reply_text() -> str:

    global _PENDING_REPLY

    if not _CURRENT_EMAIL:

        return (
            "There is no selected email to reply to."
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
            "The selected email has no readable content."
        )

    api_key = (
        os.environ.get(
            "GEMINI_API_KEY"
        )
        or os.environ.get(
            "GOOGLE_API_KEY"
        )
    )

    if not api_key:

        return (
            "I cannot generate the reply because "
            "GEMINI_API_KEY or GOOGLE_API_KEY is "
            "not available."
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
  unless the email establishes it.
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
                "Gemini did not generate a reply."
            )

        _PENDING_REPLY = reply

        return (
            "Generated reply:\n\n"
            + reply
            + "\n\nSay 'send it' when you want "
            "me to send it."
        )

    except Exception as exc:

        _log(
            "Reply generation failed:",
            repr(exc),
        )

        return (
            f"I could not generate the reply: {exc}"
        )


def _reply_to_current_email() -> str:

    if not _CURRENT_EMAIL:

        return (
            "There is no selected email to reply to."
        )

    if not _PENDING_REPLY:

        return (
            "No generated reply is waiting. "
            "Generate a reply first."
        )

    page = _page()

    if page is None:

        return (
            "Gmail automation is not available."
        )

    button = _find_reply_button()

    if button is None:

        return (
            "I could not find Gmail's Reply button."
        )

    try:

        button.scroll_into_view_if_needed(
            timeout=2000
        )

        button.click(
            timeout=5000
        )

        time.sleep(1.0)

    except Exception as exc:

        return (
            f"I could not open Gmail's reply box: {exc}"
        )

    editor = _find_reply_editor()

    if editor is None:

        return (
            "I could not find Gmail's reply editor."
        )

    try:

        editor.click()

        editor.fill(
            _PENDING_REPLY
        )

        return (
            "The generated reply is in Gmail. "
            "Say 'send it' if you want me to send it."
        )

    except Exception as exc:

        return (
            f"I could not enter the generated reply: {exc}"
        )


# ============================================================================
# SEND
# ============================================================================

def _send_current_reply() -> str:

    global _PENDING_REPLY

    page = _page()

    if page is None:

        return (
            "Gmail automation is not available."
        )

    selectors = [
        'div[role="button"][aria-label^="Send"]',
        'div[role="button"][data-tooltip^="Send"]',
        'button[aria-label^="Send"]',
        '[role="button"][command="Send"]',
    ]

    button = None

    for selector in selectors:

        try:

            loc = (
                page
                .locator(selector)
                .last
            )

            if (
                loc.count()
                and loc.is_visible(
                    timeout=1000
                )
            ):

                button = loc

                break

        except Exception:

            pass

    if button is None:

        return (
            "I could not find Gmail's Send button."
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
            f"I could not send the Gmail reply: {exc}"
        )


# ============================================================================
# CLOSE
# ============================================================================

def _close() -> str:

    global _PAGE
    global _CONTEXT
    global _CONNECTION
    global _PLAYWRIGHT
    global _BROWSER_PROCESS
    global _CURRENT_EMAIL
    global _SEARCH_RESULTS
    global _PENDING_REPLY

    try:

        if _CONNECTION is not None:

            _CONNECTION.close()

    except Exception:

        pass

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

    except Exception:

        pass

    _PAGE = None
    _CONTEXT = None
    _CONNECTION = None
    _PLAYWRIGHT = None
    _BROWSER_PROCESS = None

    _CURRENT_EMAIL = {}
    _SEARCH_RESULTS = []
    _PENDING_REPLY = ""

    return (
        "Gmail browser closed."
    )


# ============================================================================
# CLEAN PYTHON SHUTDOWN
# ============================================================================

def _shutdown_gmail_playwright() -> None:

    global _PAGE
    global _CONTEXT
    global _CONNECTION
    global _PLAYWRIGHT

    # Important:
    # DO NOT terminate the independent browser here.

    try:

        if _CONTEXT is not None:
            _CONTEXT.close()

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


atexit.register(
    _shutdown_gmail_playwright
)


# ============================================================================
# MAIN CONTROLLER
# ============================================================================

def gmail_control(
    command: Dict[str, Any],
) -> str:

    if not isinstance(
        command,
        dict,
    ):

        return (
            "Invalid Gmail command."
        )

    action = str(
        command.get(
            "action",
            "",
        )
        or command.get(
            "command",
            "",
        )
        or ""
    ).strip().lower()

    _log(
        "action=",
        repr(action),
        "query=",
        repr(
            command.get(
                "query",
                "",
            )
        ),
        "receiver=",
        repr(
            command.get(
                "receiver",
                "",
            )
        ),
    )

    try:

        # --------------------------------------------------------------
        # SETUP / OPEN
        # --------------------------------------------------------------

        if action in (
            "setup",
            "connect",
            "setup_gmail",
            "open",
            "open_gmail",
            "start",
        ):

            return _open_gmail()

        # --------------------------------------------------------------
        # LATEST
        # --------------------------------------------------------------

        if action in (
            "latest",
            "latest_mail",
            "read_latest",
            "read_mail",
            "read_email",
        ):

            return _read_latest()

        # --------------------------------------------------------------
        # SEARCH
        # --------------------------------------------------------------

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

            return _search_gmail(
                query
            )

        # --------------------------------------------------------------
        # SEARCH + READ
        # --------------------------------------------------------------

        if action in (
            "read_search",
            "search_and_read",
        ):

            query = (
                command.get("query")
                or command.get("search")
                or ""
            )

            return _read_search(
                query
            )

        # --------------------------------------------------------------
        # SEARCH + OPEN
        #
        # Examples:
        #   "find and open John's email"
        #   "open the email from Google"
        # --------------------------------------------------------------

        if action in (
            "search_and_open",
            "open_by_query",
            "find_and_open",
            "open_search_result",
        ):

            query = (
                command.get("query")
                or command.get("search")
                or command.get("text")
                or ""
            )

            return _search_and_open(
                query
            )

        # --------------------------------------------------------------
        # SELECT / OPEN NUMBER
        # --------------------------------------------------------------

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
                    "Please tell me which email "
                    "number to open."
                )

            return _open_result(
                index
            )

        # --------------------------------------------------------------
        # CURRENT
        # --------------------------------------------------------------

        if action in (
            "current",
            "current_email",
            "selected",
            "that_one",
        ):

            return _current_email()

        # --------------------------------------------------------------
        # GENERATE REPLY
        # --------------------------------------------------------------

        if action in (
            "generate_reply",
            "draft_reply",
            "reply_generate",
        ):

            return _generate_reply_text()

        # --------------------------------------------------------------
        # PUT REPLY INTO GMAIL
        # --------------------------------------------------------------

        if action in (
            "reply",
            "write_reply",
            "compose_reply",
        ):

            return _reply_to_current_email()

        # --------------------------------------------------------------
        # AUTONOMOUS REPLY
        #
        # This opens/selects and drafts the reply.
        # It does NOT send without the explicit send action.
        # --------------------------------------------------------------

        if action in (
            "auto_reply",
            "autonomous_reply",
            "compose_auto_reply",
            "reply_on_its_own",
        ):

            if not _CURRENT_EMAIL:

                opened = _open_gmail()

                if any(
                    word in opened.casefold()
                    for word in (
                        "failed",
                        "error",
                        "could not",
                    )
                ):

                    return opened

                latest = _read_latest()

                if (
                    not _CURRENT_EMAIL
                    and isinstance(
                        latest,
                        str,
                    )
                ):

                    return latest

            generated = (
                _generate_reply_text()
            )

            if not _PENDING_REPLY:

                return generated

            composed = (
                _reply_to_current_email()
            )

            return (
                f"{composed}\n"
                "Reply composed in Gmail. "
                "It has NOT been sent."
            )

        # --------------------------------------------------------------
        # SEND
        # --------------------------------------------------------------

        if action in (
            "send",
            "send_reply",
            "send_email",
        ):

            return _send_current_reply()

        # --------------------------------------------------------------
        # CLOSE
        # --------------------------------------------------------------

        if action in (
            "close",
            "close_gmail",
            "stop",
        ):

            return _close()

        return (
            f"Unknown Gmail action: {action}. "
            "Supported actions include setup, open, "
            "latest, search, read_search, search_and_open, "
            "select, current, generate_reply, reply, "
            "auto_reply, send, and close."
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


# ============================================================================
# DIRECT TEST
# ============================================================================

if __name__ == "__main__":

    print(
        gmail_control(
            {
                "action": "setup"
            }
        )
    )

