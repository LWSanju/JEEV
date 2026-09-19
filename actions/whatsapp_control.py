import os
import re
import time
import subprocess
from pathlib import Path

try:
    from .robocorp_desktop import (
        robocorp_available,
        robocorp_focus_handle,
        robocorp_send_keys,
        robocorp_set_value,
    )
except Exception:
    def robocorp_available(): return False
    def robocorp_focus_handle(*args, **kwargs): return False
    def robocorp_send_keys(*args, **kwargs): return False
    def robocorp_set_value(*args, **kwargs): return False


# ============================================================
# JEEV — WHATSAPP DESKTOP CONTROL
# ============================================================

WHATSAPP_DESKTOP_APP_ID = (
    "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"
)


# ============================================================
# PROCESS IDENTIFICATION
# ============================================================

WHATSAPP_PROCESS_NAMES = {
    "whatsapp",
    "whatsappdesktop",
    "whatsapproot",
    "whatsappapp",
}

BROWSER_PROCESS_NAMES = {
    "msedge",
    "chrome",
    "firefox",
    "brave",
    "opera",
    "operagx",
    "vivaldi",
    "iexplore",
}


# Pending WhatsApp contact choices.  This is deliberately kept in-process
# so a follow-up such as "the second one" can select the exact candidate
# that JEEV just displayed instead of starting a new first-match search.
_PENDING_CONTACTS = {
    "query": "",
    "candidates": [],
    "created": 0.0,
}

_PENDING_TTL = 120.0

# The currently selected WhatsApp chat.  This is critical for the
# confirmation flow in main.py: after JEEV resolves a contact, a later
# "yes" must NOT perform a second search and accidentally pick another row.
_ACTIVE_CONTACT = {
    "name": "",
    "key": "",
    "selected_at": 0.0,
}

_ACTIVE_CONTACT_TTL = 600.0

# Cache the last verified WhatsApp window for the duration of one action.
# This prevents repeated PowerShell process scans/focus loops.
_LAST_WHATSAPP_WINDOW = None


def _normalize_process_name(value):
    value = str(value or "").strip().lower()

    if value.endswith(".exe"):
        value = value[:-4]

    value = re.sub(r"[^a-z0-9]", "", value)

    return value


def _is_browser(process_name):
    name = _normalize_process_name(process_name)

    if not name:
        return False

    return (
        name in BROWSER_PROCESS_NAMES
        or name.startswith("msedge")
        or name.startswith("chrome")
        or name.startswith("firefox")
        or name.startswith("brave")
        or name.startswith("opera")
    )


def _is_whatsapp_process(process_name):
    name = _normalize_process_name(process_name)

    if not name:
        return False

    # Absolute browser protection.
    if _is_browser(name):
        return False

    return name in WHATSAPP_PROCESS_NAMES


# ============================================================
# GET WINDOWS PROCESSES
# ============================================================

def _get_processes():
    """
    Returns:

        pid
        process
        title
        path

    for visible Windows processes.
    """

    ps = r'''
$items = Get-CimInstance Win32_Process |
    Where-Object {
        $_.ProcessId -and
        $_.Name
    }

foreach ($p in $items) {

    $title = ""

    try {
        $proc = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue

        if ($proc) {
            $title = $proc.MainWindowTitle
        }
    }
    catch {}

    $path = ""

    try {
        $path = $p.ExecutablePath
    }
    catch {}

    Write-Output (
        $p.ProcessId.ToString() + "|" +
        $p.Name + "|" +
        $title.Replace("|", " ") + "|" +
        $path.Replace("|", " ")
    )
}
'''

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return []

        processes = []

        for line in (result.stdout or "").splitlines():

            parts = line.split("|", 3)

            if len(parts) != 4:
                continue

            pid = parts[0].strip()
            process = parts[1].strip()
            title = parts[2].strip()
            path = parts[3].strip()

            processes.append(
                {
                    "pid": pid,
                    "process": process,
                    "title": title,
                    "path": path,
                }
            )

        return processes

    except Exception as e:

        print(
            "[JEEV][WhatsApp] Process scan failed:",
            e,
        )

        return []


# ============================================================
# FIND REAL WHATSAPP DESKTOP
# ============================================================

def _find_whatsapp_window():

    print(
        "[JEEV][WhatsApp] Searching ONLY for WhatsApp Desktop..."
    )

    processes = _get_processes()

    # --------------------------------------------------------
    # FIRST: exact WhatsApp process
    # --------------------------------------------------------

    for item in processes:

        process = item["process"]

        if not _is_whatsapp_process(process):
            continue

        if not item["title"]:
            continue

        print(
            "[JEEV][WhatsApp] REAL WhatsApp FOUND:",
            item,
        )

        return item

    # --------------------------------------------------------
    # SECOND: executable path check
    # --------------------------------------------------------

    for item in processes:

        process = _normalize_process_name(
            item["process"]
        )

        path = str(
            item.get("path", "")
        ).lower()

        title = str(
            item.get("title", "")
        )

        if _is_browser(process):
            continue

        if not title:
            continue

        whatsapp_path = (
            "5319275a" in path
            or "whatsappdesktop" in path
            or "\\whatsapp\\" in path
        )

        if whatsapp_path:

            print(
                "[JEEV][WhatsApp] REAL WhatsApp found by path:",
                item,
            )

            return item

    # --------------------------------------------------------
    # NEVER accept browser windows.
    # --------------------------------------------------------

    for item in processes:

        title = str(
            item.get("title", "")
        ).lower()

        process = item["process"]

        if "whatsapp" not in title:
            continue

        if _is_browser(process):

            print(
                "[JEEV][WhatsApp] BLOCKED browser:",
                process,
                "|",
                title,
            )

            continue

    print(
        "[JEEV][WhatsApp] REAL WhatsApp Desktop NOT FOUND."
    )

    return None


# ============================================================
# FOCUS WHATSAPP
# ============================================================

def _whatsapp_foreground_pid():
    """Return the foreground window PID without spawning PowerShell."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:
        return None


def _focus_whatsapp(window=None):

    global _LAST_WHATSAPP_WINDOW
    window = window or _LAST_WHATSAPP_WINDOW or _find_whatsapp_window()

    # Fast path: WhatsApp is already foreground. This avoids a Robocorp
    # UIAutomation lookup on every message/search operation.
    try:
        if window and int(window.get("pid", 0) or 0) == _whatsapp_foreground_pid():
            _LAST_WHATSAPP_WINDOW = window
            return True
    except Exception:
        pass

    if not window:
        print(
            "[JEEV][WhatsApp] "
            "Focus BLOCKED — WhatsApp Desktop not found."
        )

        return False

    process = window["process"]

    # FINAL SAFETY CHECK
    if _is_browser(process):

        print(
            "[JEEV][WhatsApp] "
            "BLOCKED browser focus:",
            process,
        )

        return False

    if not _is_whatsapp_process(process):

        path = str(
            window.get("path", "")
        ).lower()

        if not (
            "5319275a" in path
            or "whatsappdesktop" in path
            or "\\whatsapp\\" in path
        ):

            print(
                "[JEEV][WhatsApp] "
                "BLOCKED unknown process:",
                process,
            )

            return False

    print(
        "[JEEV][WhatsApp] Focusing:",
        window["process"],
        "|",
        window["title"],
    )

    # Robocorp first. The handle comes from our verified WhatsApp process,
    # so this cannot accidentally foreground Chrome/Edge/Firefox.
    if robocorp_available():
        try:
            if robocorp_focus_handle(int(window["pid"]), timeout=0.9):
                _LAST_WHATSAPP_WINDOW = window
                return True
        except Exception:
            pass

    ps = f'''
$shell = New-Object -ComObject WScript.Shell

try {{
    $success = $shell.AppActivate({window["pid"]})

    Start-Sleep -Milliseconds 500

    if ($success) {{
        Write-Output "SUCCESS"
    }}
    else {{
        Write-Output "FAILED"
    }}
}}
catch {{
    Write-Output "FAILED"
}}
'''

    try:

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )

        if "SUCCESS" in (
            result.stdout or ""
        ):

            print(
                "[JEEV][WhatsApp] "
                "WhatsApp Desktop focused."
            )

            _LAST_WHATSAPP_WINDOW = window
            return True

        print(
            "[JEEV][WhatsApp] "
            "Could not focus WhatsApp."
        )

        return False

    except Exception as e:

        print(
            "[JEEV][WhatsApp] Focus error:",
            e,
        )

        return False


# ============================================================
# LAUNCH WHATSAPP DESKTOP
# ============================================================

def _launch_whatsapp():

    print(
        "[JEEV][WhatsApp] "
        "Checking WhatsApp Desktop..."
    )

    global _LAST_WHATSAPP_WINDOW
    existing = _find_whatsapp_window()

    if existing:

        _LAST_WHATSAPP_WINDOW = existing
        print(
            "[JEEV][WhatsApp] "
            "WhatsApp Desktop already running."
        )

        return _focus_whatsapp(existing)

    print(
        "[JEEV][WhatsApp] "
        "WhatsApp Desktop is NOT running."
    )

    print(
        "[JEEV][WhatsApp] "
        "Launching Microsoft Store WhatsApp AppID..."
    )

    try:

        subprocess.Popen(
            [
                "explorer.exe",
                "shell:AppsFolder\\"
                + WHATSAPP_DESKTOP_APP_ID,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    except Exception as e:

        print(
            "[JEEV][WhatsApp] "
            "AppID launch failed:",
            e,
        )

        return False

    # --------------------------------------------------------
    # WAIT FOR REAL WHATSAPP
    # --------------------------------------------------------

    deadline = time.time() + 20

    while time.time() < deadline:

        window = _find_whatsapp_window()

        if window:

            _LAST_WHATSAPP_WINDOW = window
            print(
                "[JEEV][WhatsApp] "
                "REAL WhatsApp Desktop launched."
            )

            return _focus_whatsapp(window)

        time.sleep(0.5)

    print(
        "[JEEV][WhatsApp] "
        "WhatsApp Desktop did not appear."
    )

    return False


# ============================================================
# KEYBOARD
# ============================================================

def _keyboard():

    try:

        import pyautogui

        pyautogui.PAUSE = 0.12
        pyautogui.FAILSAFE = True

        return pyautogui

    except ImportError:

        return None


# ============================================================
# CLEAN CONTACT
# ============================================================

def _clean_contact(value):

    value = str(
        value or ""
    ).strip()

    value = re.sub(
        r"\bwhatsapp\b",
        "",
        value,
        flags=re.I,
    )

    value = re.sub(
        r"\b(chat|contact|person)\b",
        "",
        value,
        flags=re.I,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip(" .,-")

    return value


# ============================================================
# OPEN CHAT
# ============================================================

def _normalize_contact_key(value):

    value = _clean_contact(value)
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _parse_contact_index(value):
    """Accept 1/2/3 as well as first/second/third/fourth/fifth."""

    text = str(value or "").strip().lower()

    if text.isdigit():
        number = int(text)
        return number if number > 0 else None

    words = {
        "first": 1,
        "1st": 1,
        "one": 1,
        "second": 2,
        "2nd": 2,
        "two": 2,
        "third": 3,
        "3rd": 3,
        "three": 3,
        "fourth": 4,
        "4th": 4,
        "four": 4,
        "fifth": 5,
        "5th": 5,
        "five": 5,
        "sixth": 6,
        "6th": 6,
        "six": 6,
        "seventh": 7,
        "7th": 7,
        "seven": 7,
        "eighth": 8,
        "8th": 8,
        "eight": 8,
        "ninth": 9,
        "9th": 9,
        "nine": 9,
        "tenth": 10,
        "10th": 10,
        "ten": 10,
    }

    for word, number in words.items():
        if re.search(r"\b" + re.escape(word) + r"\b", text):
            return number

    match = re.search(r"\b(?:number|option|contact)\s*(\d+)\b", text)
    if match:
        return int(match.group(1))

    return None



def _pywinauto_whatsapp_candidates(receiver, window=None):
    """
    Fallback UIA reader for WhatsApp Desktop/WebView2.

    Some WhatsApp builds expose no useful elements through the project's
    global UIA enumerator.  pywinauto can sometimes attach directly to the
    WhatsApp process and expose the WebView descendants instead.
    """
    try:
        from pywinauto import Desktop
    except Exception:
        return []

    window = window or _LAST_WHATSAPP_WINDOW or _find_whatsapp_window()
    if not window:
        return []

    try:
        pid = int(window.get("pid", 0) or 0)
    except Exception:
        pid = 0
    if not pid:
        return []

    query = _normalize_contact_key(receiver)
    if not query:
        return []

    try:
        desktop = Desktop(backend="uia")
        roots = desktop.windows(process=pid)
    except Exception as exc:
        print("[JEEV][WhatsApp] pywinauto attach failed:", exc)
        return []

    exact = []
    partial = []
    seen = set()

    for root in roots:
        try:
            controls = [root] + root.descendants()
        except Exception:
            controls = [root]

        for control in controls[:5000]:
            try:
                name = str(control.window_text() or "").strip()
            except Exception:
                continue
            if not name:
                continue

            key = _normalize_contact_key(name)
            if not key or not (key == query or query in key or key in query):
                continue

            try:
                rect = control.rectangle()
                x = int(rect.left)
                y = int(rect.top)
                width = int(rect.width())
                height = int(rect.height())
            except Exception:
                continue

            if width <= 0 or height <= 0:
                continue

            try:
                control_type = str(control.element_info.control_type or "")
            except Exception:
                control_type = ""

            # Prefer actual selectable/text rows.  Generic descendants are
            # accepted because WebView2 versions differ in what they expose.
            useful = (
                "listitem" in control_type.lower()
                or "dataitem" in control_type.lower()
                or "button" in control_type.lower()
                or "text" in control_type.lower()
                or "custom" in control_type.lower()
                or not control_type
            )
            if not useful:
                continue

            candidate = {
                "name": name,
                "title": name,
                "control_type": control_type,
                "process_id": pid,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            }

            # Reject giant containers/search panes. We want contact-like rows.
            if width > 700 or height > 140 or height < 12:
                continue

            # Keep only one raw UIA node per visual row. WebView2 commonly
            # exposes the same contact name through several nested Text/Custom
            # nodes, which previously inflated 5 contacts into 14+ results.
            row_key = (key, y // 35)
            if row_key in seen:
                continue
            seen.add(row_key)

            if key == query:
                exact.append(candidate)
            else:
                partial.append(candidate)

    candidates = exact or partial
    candidates.sort(key=lambda e: (e["y"], e["x"]))

    # Final visual-row collapse. Same contact name within ~28 px vertically
    # is one WhatsApp result, regardless of nested accessibility nodes.
    unique = []
    for candidate in candidates:
        if any(
            _normalize_contact_key(candidate.get("name", "")) ==
            _normalize_contact_key(existing.get("name", ""))
            and abs(int(candidate.get("y", 0)) - int(existing.get("y", 0))) <= 28
            for existing in unique
        ):
            continue
        unique.append(candidate)

    return unique[:30]


def _whatsapp_uia_candidates(receiver, window=None):
    """
    Find visible WhatsApp search-result rows for *receiver*.

    WhatsApp Desktop has changed its Chromium/WebView UI several times.
    The old implementation was too strict: it required every UIA element to
    expose the exact WhatsApp PID and one of a small set of control types.
    That can make a perfectly visible search result look like "not found".

    We therefore use a layered approach:
      1. enumerate desktop.uia elements;
      2. prefer elements belonging to the real WhatsApp PID, but tolerate
         missing/zero process_id metadata;
      3. accept useful text-like controls and rows;
      4. match exact names first, then partial names;
      5. deduplicate repeated WebView/UIA representations.
    """
    try:
        from desktop.uia import get_elements
    except Exception as exc:
        print("[JEEV][WhatsApp] UIA unavailable:", exc)
        return []

    window = window or _LAST_WHATSAPP_WINDOW or _find_whatsapp_window()
    if not window:
        return []

    try:
        whatsapp_pid = int(window.get("pid", 0) or 0)
    except Exception:
        whatsapp_pid = 0

    query = _normalize_contact_key(receiver)
    if not query:
        return []

    try:
        elements = get_elements(max_items=4000)
    except Exception as exc:
        print("[JEEV][WhatsApp] UIA enumeration failed:", exc)
        elements = []

    # If the project's global UIA scanner sees nothing, attach directly to
    # the WhatsApp process through pywinauto before giving up.
    if not elements:
        fallback = _pywinauto_whatsapp_candidates(receiver, window=window)
        if fallback:
            print(
                f"[JEEV][WhatsApp] pywinauto found {len(fallback)} candidate(s)."
            )
            return fallback

    exact = []
    partial = []

    for element in elements:
        try:
            ep = int(element.get("process_id", 0) or 0)
        except Exception:
            ep = 0

        # Prefer real WhatsApp elements.  Some WebView2/UIA providers expose
        # process_id=0, so do not discard those automatically.
        if whatsapp_pid and ep and ep != whatsapp_pid:
            continue

        name = str(
            element.get("name", element.get("title", "")) or ""
        ).strip()
        if not name:
            continue

        control_type = str(
            element.get("control_type", element.get("type", "")) or ""
        ).lower()

        # Search results are commonly ListItem/Button/Text/Custom, but newer
        # WebView builds sometimes expose generic descendants.  Geometry is
        # the final sanity check.
        if control_type and not any(
            token in control_type
            for token in ("listitem", "list", "button", "text", "custom", "dataitem", "hyperlink")
        ):
            # Keep only elements that look like a visible UI row.
            if not (element.get("x") is not None and element.get("y") is not None):
                continue

        try:
            x = int(element.get("x", 0) or 0)
            y = int(element.get("y", 0) or 0)
            width = int(element.get("width", 0) or 0)
            height = int(element.get("height", 0) or 0)
        except Exception:
            continue

        if width <= 0 or height <= 0:
            continue

        key = _normalize_contact_key(name)
        if not key:
            continue

        if key == query:
            exact.append(dict(element))
        elif query in key or key in query:
            partial.append(dict(element))

    candidates = exact or partial

    # Stable screen order.
    candidates.sort(
        key=lambda e: (
            int(e.get("y", 0) or 0),
            int(e.get("x", 0) or 0),
        )
    )

    unique = []
    for element in candidates:
        name_key = _normalize_contact_key(
            element.get("name", element.get("title", ""))
        )
        x = int(element.get("x", 0) or 0)
        y = int(element.get("y", 0) or 0)
        width = int(element.get("width", 0) or 0)
        height = int(element.get("height", 0) or 0)

        # Search panes, headers and parent containers are not contact rows.
        if width > 700 or height > 140 or height < 12:
            continue

        # A single WhatsApp contact is frequently represented by several
        # nested WebView2 accessibility nodes. Collapse by name + visual row,
        # not name + x-coordinate. The previous x-based key was the reason
        # one visible contact could become multiple reported contacts.
        duplicate_row = False
        for existing in unique:
            existing_name = _normalize_contact_key(
                existing.get("name", existing.get("title", ""))
            )
            existing_y = int(existing.get("y", 0) or 0)
            if name_key == existing_name and abs(y - existing_y) <= 28:
                duplicate_row = True
                break

        if duplicate_row:
            continue

        unique.append(dict(element))

    # Return only actual visible rows, in screen order.
    unique.sort(key=lambda e: (int(e.get("y", 0) or 0), int(e.get("x", 0) or 0)))
    return unique[:30]


def _remember_contact_candidates(receiver, candidates):

    _PENDING_CONTACTS["query"] = _clean_contact(receiver)
    _PENDING_CONTACTS["candidates"] = list(candidates)
    _PENDING_CONTACTS["created"] = time.time()


def _pending_candidates_for(receiver=""):


    if not _PENDING_CONTACTS["candidates"]:
        return []

    if time.time() - float(_PENDING_CONTACTS["created"] or 0) > _PENDING_TTL:
        _PENDING_CONTACTS["query"] = ""
        _PENDING_CONTACTS["candidates"] = []
        return []

    query = _normalize_contact_key(receiver)
    pending_query = _normalize_contact_key(_PENDING_CONTACTS["query"])

    allowed_followups = {
        pending_query, "", "one", "two", "three", "four", "five",
        "six", "seven", "eight", "nine", "ten",
        "first", "second", "third", "fourth", "fifth",
        "sixth", "seventh", "eighth", "ninth", "tenth",
    }
    if query and query not in allowed_followups and _parse_contact_index(receiver) is None:
        return []

    return list(_PENDING_CONTACTS["candidates"])


def _click_candidate(element):
    pyautogui = _keyboard()
    if pyautogui is None:
        return False

    try:
        x = int(element.get("x", 0) or 0) + max(1, int(element.get("width", 1) or 1) // 2)
        y = int(element.get("y", 0) or 0) + max(1, int(element.get("height", 1) or 1) // 2)
    except Exception:
        return False

    if x <= 0 or y <= 0:
        return False

    try:
        pyautogui.click(x, y)
        time.sleep(1.0)
        return True
    except Exception as exc:
        print("[JEEV][WhatsApp] Candidate click failed:", exc)
        return False


def _set_active_contact(name):
    name = _clean_contact(name)
    _ACTIVE_CONTACT["name"] = name
    _ACTIVE_CONTACT["key"] = _normalize_contact_key(name)
    _ACTIVE_CONTACT["selected_at"] = time.time()


def _active_contact_matches(name):
    key = _normalize_contact_key(name)

    if not key or not _ACTIVE_CONTACT.get("key"):
        return False

    if (
        time.time()
        - float(
            _ACTIVE_CONTACT.get(
                "selected_at",
                0,
            )
            or 0
        )
        > _ACTIVE_CONTACT_TTL
    ):
        _ACTIVE_CONTACT["name"] = ""
        _ACTIVE_CONTACT["key"] = ""
        _ACTIVE_CONTACT["selected_at"] = 0.0
        return False

    active_key = _ACTIVE_CONTACT.get(
        "key",
        "",
    )

    # Exact selected contact match.
    if key == active_key:
        return True

    # Mouse-only selections are stored as:
    #
    #     "Vishal — result 2"
    #
    # Treat the original query as the active destination so a
    # later confirmation such as "yes, send it" does not perform
    # a second search.
    active_name = str(
        _ACTIVE_CONTACT.get(
            "name",
            "",
        )
        or ""
    )

    if " — result " in active_name:
        original_query = active_name.split(
            " — result ",
            1,
        )[0]

        original_key = _normalize_contact_key(
            original_query
        )

        if (
            original_key
            and key == original_key
        ):
            return True

    return False


def _clear_active_contact():
    _ACTIVE_CONTACT["name"] = ""
    _ACTIVE_CONTACT["key"] = ""
    _ACTIVE_CONTACT["selected_at"] = 0.0


def _paste_text(pyautogui, text):
    """Paste Unicode safely; pyautogui.write cannot type Tamil reliably."""
    text = str(text or "")
    if not text:
        return True
    try:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        return True
    except Exception:
        try:
            pyautogui.write(text, interval=0.018)
            return True
        except Exception as exc:
            print("[JEEV][WhatsApp] Text input failed:", exc)
            return False


def _uia_window_controls(window):
    try:
        from pywinauto import Desktop
        pid=int((window or {}).get("pid",0) or 0)
        if not pid:return []
        roots=Desktop(backend="uia").windows(process=pid)
        out=[]
        for root in roots:
            try:out.extend([root]+root.descendants())
            except Exception:out.append(root)
        return out
    except Exception as exc:
        print("[JEEV][WhatsApp] UIA attach failed:",exc); return []

def _uia_find_search_edit(window):
    scored=[]
    for c in _uia_window_controls(window):
        try:
            typ=str(c.element_info.control_type or "").lower(); name=str(c.window_text() or "").lower(); aid=str(c.element_info.automation_id or "").lower()
            if "edit" not in typ and "document" not in typ:continue
            score=0
            if "search" in name:score-=100
            if "new chat" in name:score-=80
            if "search" in aid:score-=50
            try:
                r=c.rectangle()
                if r.width()>120 and r.height()<100:score-=10
            except Exception:pass
            scored.append((score,c))
        except Exception:pass
    scored.sort(key=lambda x:x[0]); return scored[0][1] if scored else None

def _uia_set_value(control,text):
    text=str(text or "")
    for fn in (lambda:control.set_edit_text(text), lambda:control.iface_value.SetValue(text)):
        try:
            fn(); return True
        except Exception:pass
    return False

def _uia_invoke_candidate(candidate,window):
    pid=int((window or {}).get("pid",0) or 0); name=str(candidate.get("name") or candidate.get("title") or "").strip(); typ=str(candidate.get("control_type") or "")
    try:
        from desktop.uia import invoke_process_element
        if pid and invoke_process_element(pid,name=name,control_type=typ,x=int(candidate.get("x",0) or 0),y=int(candidate.get("y",0) or 0)):return True
    except Exception:pass
    key=_normalize_contact_key(name); cy=int(candidate.get("y",0) or 0)
    for c in _uia_window_controls(window):
        try:
            ck=_normalize_contact_key(c.window_text()); r=c.rectangle()
            if not ck or (ck!=key and key not in ck and ck not in key) or abs(int(r.top)-cy)>35:continue
            for fn in (getattr(c,"invoke",None),getattr(c,"select",None)):
                if fn:
                    try:fn(); return True
                    except Exception:pass
        except Exception:pass
    return False

def _uia_search_contact(receiver,window):
    # UIA only: invoke New Chat if necessary, then set the Edit ValuePattern.
    search=_uia_find_search_edit(window)
    if search is None:
        for c in _uia_window_controls(window):
            try:
                n=str(c.window_text() or "").lower(); t=str(c.element_info.control_type or "").lower()
                if "new chat" in n and "button" in t:
                    try:c.invoke()
                    except Exception:continue
                    time.sleep(.8); break
            except Exception:pass
        search=_uia_find_search_edit(window)
    if search is None:return False,"WhatsApp search Edit control is not exposed through UIA."
    if not _uia_set_value(search,receiver):return False,"UIA could not set the WhatsApp search field value."
    time.sleep(1.2); return True,""


# ============================================================
# MOUSE SEARCH + ROBOCORP KEYBOARD CONTACT SELECTION
# ============================================================
#
# Final fallback strategy:
#
#   1. Focus the real WhatsApp Desktop window.
#   2. Physically click the visible Search box.
#   3. Enter the requested contact name.
#   4. Wait for WhatsApp to render the visible results.
#   5. Treat the first five visible result rows as:
#          1, 2, 3, 4, 5
#   6. Ask JEEV which number the user wants.
#   7. On "2"/"second", physically click row 2.
#
# This deliberately does NOT depend on:
#   - WhatsApp UI Automation search controls
#   - UIA InvokePattern
#   - pywinauto control selection
#
# The only UI operation used for the final selection is the mouse.
# ============================================================

_MOUSE_SEARCH_X_RATIO = 0.190
_MOUSE_SEARCH_Y_RATIO = 0.211

_MOUSE_RESULT_X_RATIO = 0.190
_MOUSE_FIRST_RESULT_Y_RATIO = 0.377
_MOUSE_RESULT_Y_STEP_RATIO = 0.130

_MOUSE_MAX_VISIBLE_CONTACTS = 5
_MOUSE_SEARCH_SETTLE = 1.25


def _get_whatsapp_screen_rect(window=None):
    """
    Get the actual WhatsApp top-level window rectangle.

    Returns:
        (left, top, width, height)

    Uses the HWND belonging to the currently focused WhatsApp
    window when possible. This makes the mouse coordinates scale
    with the actual window size instead of assuming one fixed
    1008x593 screenshot.
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32

        hwnd = user32.GetForegroundWindow()

        if not hwnd:
            return None

        title_buf = ctypes.create_unicode_buffer(512)

        user32.GetWindowTextW(
            hwnd,
            title_buf,
            512,
        )

        title = title_buf.value.lower()

        if "whatsapp" not in title:
            return None

        rect = ctypes.wintypes.RECT()

        if not user32.GetWindowRect(
            hwnd,
            ctypes.byref(rect),
        ):
            return None

        left = int(rect.left)
        top = int(rect.top)
        right = int(rect.right)
        bottom = int(rect.bottom)

        width = right - left
        height = bottom - top

        if width <= 200 or height <= 150:
            return None

        return (
            left,
            top,
            width,
            height,
        )

    except Exception as exc:
        print(
            "[JEEV][WhatsApp] Could not read "
            "WhatsApp screen rectangle:",
            exc,
        )
        return None


def _mouse_point_for_whatsapp(
    x_ratio,
    y_ratio,
    window=None,
):
    """
    Convert normalized WhatsApp coordinates into screen coordinates.
    """
    rect = _get_whatsapp_screen_rect(
        window
    )

    if not rect:
        return None

    left, top, width, height = rect

    x = int(
        left
        + width * x_ratio
    )

    y = int(
        top
        + height * y_ratio
    )

    return x, y


def _mouse_click_whatsapp_point(
    x_ratio,
    y_ratio,
    window=None,
    pause=0.35,
):
    """
    Physically click a normalized point in the WhatsApp window.
    """
    pyautogui = _keyboard()

    if pyautogui is None:
        return False

    point = _mouse_point_for_whatsapp(
        x_ratio,
        y_ratio,
        window=window,
    )

    if not point:
        return False

    x, y = point

    try:
        pyautogui.moveTo(
            x,
            y,
            duration=0.15,
        )

        pyautogui.click()

        if pause:
            time.sleep(pause)

        return True

    except Exception as exc:
        print(
            "[JEEV][WhatsApp] Mouse click failed:",
            exc,
        )
        return False


def _mouse_search_box(window=None):
    """
    Click the visible WhatsApp search box.

    Order:
      1. image template if the release contains one;
      2. normalized physical mouse coordinate.

    The current windows_autotest archive has no search-box image,
    so normal operation uses the calibrated mouse coordinate.
    """
    pyautogui = _keyboard()
    if pyautogui is None:
        return False

    print(
        "[JEEV][WhatsApp] "
        "Mouse-first: locating Search box..."
    )

    # Future/template path. We intentionally do not invent a template
    # filename; only existing assets are used.
    search_folders = (
        "whatsapp/search_box",
        "whatsapp/search",
        "Whatsapp/search_box",
        "WhatsApp/search_box",
    )

    rect = _get_whatsapp_screen_rect(window)
    region = None
    if rect:
        left, top, width, height = rect
        region = (
            int(left),
            int(top),
            int(width * 0.38),
            int(height * 0.32),
        )

    for folder in search_folders:
        point = _locate_whatsapp_image(
            folder,
            confidence=0.80,
            timeout=0.35,
            region=region,
        )
        if point:
            pyautogui.moveTo(*point, duration=0.12)
            pyautogui.click()
            time.sleep(0.35)
            return True

    return _mouse_click_whatsapp_point(
        _MOUSE_SEARCH_X_RATIO,
        _MOUSE_SEARCH_Y_RATIO,
        window=window,
        pause=0.35,
    )


def _mouse_type_search(receiver):
    """
    Type/paste the search query after the physical mouse click.

    pyautogui is used only as the input mechanism. The location
    of the field is determined by the mouse click above rather
    than UIA.
    """
    pyautogui = _keyboard()

    if pyautogui is None:
        return False

    receiver = str(
        receiver or ""
    ).strip()

    if not receiver:
        return False

    try:
        # The field was physically clicked above. Use Robocorp's native
        # keyboard channel first so Unicode/input handling is centralized.
        if robocorp_available():
            try:
                if robocorp_send_keys("{CTRL}a"):
                    if robocorp_send_keys(receiver):
                        time.sleep(_MOUSE_SEARCH_SETTLE)
                        return True
            except Exception:
                pass

        # pyautogui remains the hard fallback.
        pyautogui.hotkey(
            "ctrl",
            "a",
        )

        time.sleep(0.08)

        if not _paste_text(
            pyautogui,
            receiver,
        ):
            return False

        time.sleep(
            _MOUSE_SEARCH_SETTLE
        )

        return True

    except Exception as exc:
        print(
            "[JEEV][WhatsApp] Search text input failed:",
            exc,
        )
        return False


def _mouse_contact_row_point(
    index,
    window=None,
):
    """
    Return the center point of visible search result #index.

    The coordinates are normalized against the actual WhatsApp
    window, so normal resizing is supported.

    Calibrated against the WhatsApp Desktop layout shown in the
    current project screenshot:
        row 1 ≈ 37.7% down the window
        row spacing ≈ 13.0%
    """
    try:
        index = int(index)
    except Exception:
        return None

    if (
        index < 1
        or index > _MOUSE_MAX_VISIBLE_CONTACTS
    ):
        return None

    y_ratio = (
        _MOUSE_FIRST_RESULT_Y_RATIO
        + (
            index - 1
        )
        * _MOUSE_RESULT_Y_STEP_RATIO
    )

    return _mouse_point_for_whatsapp(
        _MOUSE_RESULT_X_RATIO,
        y_ratio,
        window=window,
    )


def _mouse_click_contact_row(
    index,
    window=None,
    verify=True,
):
    """
    Physically click search-result row #index.

    The click itself is always mouse-based. Verification is done by
    checking that the right-hand chat pane changes after the click.
    """
    pyautogui = _keyboard()

    if pyautogui is None:
        return False

    point = _mouse_contact_row_point(
        index,
        window=window,
    )

    if not point:
        return False

    region = _whatsapp_chat_region(window)
    before = (
        _whatsapp_screen_signature(region)
        if verify
        else None
    )

    x, y = point

    print(
        f"[JEEV][WhatsApp] "
        f"Mouse-first: clicking contact row {index} "
        f"at ({x}, {y})"
    )

    try:
        pyautogui.moveTo(
            x,
            y,
            duration=0.15,
        )

        time.sleep(0.15)
        pyautogui.click()
        time.sleep(1.10)

        if not verify:
            return True

        if _wait_for_whatsapp_chat_change(
            before,
            window=window,
            timeout=4.0,
        ):
            print(
                "[JEEV][WhatsApp] "
                f"Contact row {index} click verified."
            )
            return True

        print(
            "[JEEV][WhatsApp] "
            f"Contact row {index} click NOT verified."
        )
        return False

    except Exception as exc:
        print(
            "[JEEV][WhatsApp] "
            "Contact row mouse click failed:",
            exc,
        )
        return False

def _build_mouse_pending_candidates(
    receiver,
):
    """
    Build exactly the five selectable positions that WhatsApp
    presents in the visible search-result area.

    Names are deliberately left blank because this path does not
    trust UIA to read the WebView. JEEV can therefore safely ask:

        "I found matching contacts. Which number?"

    without accidentally mixing UIA results with mouse positions.
    """
    receiver = _clean_contact(
        receiver
    )

    candidates = []

    for index in range(
        1,
        _MOUSE_MAX_VISIBLE_CONTACTS + 1,
    ):
        candidates.append(
            {
                "index": index,
                "name": (
                    f"WhatsApp result {index}"
                ),
                "title": (
                    f"WhatsApp result {index}"
                ),
                "x": 0,
                "y": 0,
                "width": 0,
                "height": 0,
                "mouse_only": True,
                "query": receiver,
            }
        )

    return candidates


def _mouse_search_contact(
    receiver,
    window=None,
):
    """
    Perform the complete mouse-first search.

    Returns:
        (success, message)
    """
    receiver = _clean_contact(
        receiver
    )

    if not receiver:
        return (
            False,
            "No WhatsApp contact name was provided.",
        )

    if not _mouse_search_box(
        window=window
    ):
        return (
            False,
            "I could not click the WhatsApp Search box.",
        )

    if not _mouse_type_search(
        receiver
    ):
        return (
            False,
            "I clicked WhatsApp Search, but could not enter the contact name.",
        )

    print(
        "[JEEV][WhatsApp] "
        f"Mouse-first search completed for: {receiver}"
    )

    return True, ""


def _robocorp_select_whatsapp_result(index, reset_selection=True):
    """
    Select WhatsApp search result N using the same keyboard-navigation
    pattern used by JEEV's Spotify controller.

    The search box is clicked with the mouse first.  Once WhatsApp has
    rendered the results, Robocorp owns the keyboard interaction:
        result 1 -> Enter
        result 2 -> Down, Enter
        result 3 -> Down, Down, Enter
        ...

    No coordinate-based mouse click is used to choose the contact.
    """
    if not robocorp_available():
        print("[JEEV][WhatsApp] Robocorp is unavailable for result selection.")
        return False

    try:
        n = max(1, int(index or 1))
    except Exception:
        n = 1

    try:
        # WhatsApp normally leaves keyboard focus in the search/results
        # surface after the search text is entered.  A short delay gives the
        # WebView time to finish rendering before navigation begins.
        time.sleep(0.25)

        # Same principle as Spotify: move down N-1 times, then Enter.
        # This deliberately does not click a result with coordinates.
        if reset_selection:
            # Home is intentionally avoided here because WhatsApp can interpret
            # it as text navigation inside the Edit control on some builds.
            # The search operation leaves the first result as the default
            # keyboard target.
            pass

        for _ in range(n - 1):
            if not robocorp_send_keys("{DOWN}", interval=0.03):
                return False
            time.sleep(0.08)

        if not robocorp_send_keys("{ENTER}", interval=0.03):
            return False

        time.sleep(1.10)
        print(
            f"[JEEV][WhatsApp] Robocorp keyboard selected result {n} "
            f"(Down x {max(0, n - 1)} + Enter)."
        )
        return True

    except Exception as exc:
        print("[JEEV][WhatsApp] Robocorp keyboard selection failed:", exc)
        return False


def _select_pending_contact_keyboard(index):
    """
    Select the pending WhatsApp contact using keyboard navigation.

    This mirrors Spotify's proven result-selection flow: the mouse is used
    only to get into WhatsApp's Search box; Robocorp then uses Down/Enter to
    select the requested result.
    """
    candidates = _pending_candidates_for()

    if not candidates:
        return (
            "There is no pending WhatsApp contact search. "
            "Please tell me the contact name first."
        )

    try:
        index = int(index)
    except Exception:
        return "Please choose a contact number from 1 to 5."

    if index < 1 or index > len(candidates):
        return "Please choose a contact number from 1 to 5."

    window = (
        _LAST_WHATSAPP_WINDOW
        or _find_whatsapp_window()
    )

    if not window:
        return "WhatsApp Desktop could not be found."

    if not _focus_whatsapp(window):
        return "WhatsApp Desktop could not be focused."

    if not _whatsapp_foreground():
        return "WhatsApp is not the active window, so I did NOT select a contact."

    # Do NOT search again here.
    # The original search is still the active search surface. Re-searching
    # was the reason the old mouse implementation could lose the intended
    # result and click the wrong row.
    selected = _robocorp_select_whatsapp_result(index)

    if not selected:
        return (
            f"I could not select WhatsApp search result {index} "
            "using keyboard navigation."
        )

    # Verify that WhatsApp actually moved into a chat before reporting
    # success.  We still do not identify the contact by UIA; the selected
    # result number is the user's explicit choice.
    _PENDING_CONTACTS["candidates"] = []

    query = str(
        _PENDING_CONTACTS.get("query", "")
        or ""
    ).strip()

    selected_name = f"{query} — result {index}"
    _set_active_contact(selected_name)

    return (
        f"Selected WhatsApp contact {index} "
        f"for '{query}'."
    )

def _select_pending_contact_mouse(index):
    """
    Backward-compatible alias.

    Older JEEV routing code may still refer to the previous mouse-selection
    helper name. Contact selection is intentionally keyboard-based now:
    Robocorp sends Down/Enter after the mouse is used only for the Search box.
    """
    return _select_pending_contact_keyboard(index)


def _select_pending_contact(index):
    """
    Compatibility wrapper.

    Pending contact selection uses Robocorp keyboard navigation,
    matching the Spotify result-selection pattern.
    """
    return _select_pending_contact_keyboard(index)


def _open_chat(receiver, contact_index=None):
    """
    Final WhatsApp contact-opening flow.

    Normal flow:

        "message Vishal"
                ↓
        physically click Search
                ↓
        type/paste "Vishal"
                ↓
        WhatsApp displays visible results
                ↓
        JEEV asks "which one?"
                ↓
        user says "2" / "second"
                ↓
        Robocorp sends Down + Enter to select result 2

    UIA result invocation and coordinate-based result clicking are not used
    for contact selection.
    """

    receiver = _clean_contact(
        receiver
    )

    parsed = (
        _parse_contact_index(
            contact_index
        )
        if contact_index is not None
        else None
    )

    if parsed is None:
        parsed = _parse_contact_index(
            receiver
        )

    # --------------------------------------------------------
    # USER HAS ANSWERED "2", "SECOND", ETC.
    # --------------------------------------------------------

    if (
        parsed is not None
        and _pending_candidates_for()
    ):
        return _select_pending_contact_keyboard(
            parsed
        )

    # --------------------------------------------------------
    # NO CONTACT NAME
    # --------------------------------------------------------

    if not receiver:

        if (
            _ACTIVE_CONTACT.get("key")
            and _focus_whatsapp()
        ):
            return (
                "WhatsApp chat for "
                f"{_ACTIVE_CONTACT.get('name') or 'the selected contact'} "
                "is active."
            )

        return (
            "No WhatsApp contact name was provided."
        )

    # --------------------------------------------------------
    # OPEN / FOCUS WHATSAPP
    # --------------------------------------------------------

    if not _launch_whatsapp():
        return (
            "I could not open or focus WhatsApp Desktop."
        )

    window = (
        _LAST_WHATSAPP_WINDOW
        or _find_whatsapp_window()
    )

    if (
        not window
        or not _focus_whatsapp(window)
    ):
        return (
            "WhatsApp Desktop could not be focused."
        )

    # --------------------------------------------------------
    # FINAL MOUSE-FIRST SEARCH
    # --------------------------------------------------------

    ok, msg = _mouse_search_contact(
        receiver,
        window=window,
    )

    if not ok:
        return msg

    # --------------------------------------------------------
    # FIVE VISIBLE POSITIONS
    # --------------------------------------------------------
    #
    # We deliberately do not use UIA to identify or invoke the
    # result rows. The rows are selected by their visible screen
    # position.
    #
    # This is the requested final fallback.
    # --------------------------------------------------------

    candidates = (
        _build_mouse_pending_candidates(
            receiver
        )
    )

    _remember_contact_candidates(
        receiver,
        candidates,
    )

    return (
        f"I found up to {_MOUSE_MAX_VISIBLE_CONTACTS} "
        f"WhatsApp search results for '{receiver}'. "
        "Which one do you want? "
        "Please say a number from 1 to 5."
    )



def _whatsapp_foreground():
    try:
        import ctypes
        hwnd=ctypes.windll.user32.GetForegroundWindow()
        if not hwnd: return False
        buf=ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd,buf,512)
        return "whatsapp" in buf.value.lower()
    except Exception: return False

def _send_message(receiver, message_text, contact_index=None):
    message_text = str(message_text or "").strip()
    if not message_text:
        return "No WhatsApp message text was provided."

    receiver = _clean_contact(receiver)

    # IMPORTANT: main.py asks for confirmation after contact resolution.
    # When the user then says yes, do NOT search again.  The active chat is
    # already the verified destination.
    if receiver and not _active_contact_matches(receiver):
        result = _open_chat(receiver, contact_index=contact_index)
        if not (
            result.startswith("Opened the WhatsApp chat")
            or result.startswith("Selected WhatsApp contact")
        ):
            return result

    pyautogui = _keyboard()
    if pyautogui is None:
        return "WhatsApp control needs pyautogui. Run: pip install pyautogui"

    # The active chat is already the verified destination. Re-focusing here
    # used to trigger another process scan and could steal focus from the
    # composer. Only recover focus if the destination was not already active.
    if not _ACTIVE_CONTACT.get("key"):
        window = _LAST_WHATSAPP_WINDOW or _find_whatsapp_window()
        if not window or not _focus_whatsapp(window):
            return "WhatsApp Desktop could not be focused."

    if not _whatsapp_foreground():
        return "WhatsApp is not the active window, so I did NOT send the message."

    if not _paste_text(pyautogui, message_text):
        return "I could not enter the WhatsApp message."

    if robocorp_available():
        try:
            if not robocorp_send_keys("{ENTER}"):
                pyautogui.press("enter")
        except Exception:
            pyautogui.press("enter")
    else:
        pyautogui.press("enter")
    time.sleep(1.0)

    if not _whatsapp_foreground():
        return "WhatsApp lost focus while sending, so I could not verify the message was sent."

    if receiver:
        _set_active_contact(receiver)

    return "WhatsApp message sent and the WhatsApp window remained active."


def _reply(message_text):
    return _send_message("", message_text)

# ============================================================
# MAIN WHATSAPP CONTROL
# ============================================================

def whatsapp_control(
    parameters=None,
    response=None,
    player=None,
):

    parameters = parameters or {}

    action = str(
        parameters.get(
            "action",
            "",
        )
    ).strip().lower()

    receiver = (
        parameters.get("receiver")
        or parameters.get("contact")
        or ""
    )

    message_text = (
        parameters.get("message_text")
        or parameters.get("message")
        or ""
    )

    contact_index = parameters.get("contact_index")

    print(
        "[JEEV][WhatsApp]",
        "action=",
        repr(action),
        "receiver=",
        repr(receiver),
    )

    # ========================================================
    # OPEN WHATSAPP
    # ========================================================

    if action in (
        "open",
        "open_app",
        "focus",
    ):

        if _launch_whatsapp():

            return (
                "WhatsApp Desktop is open."
            )

        return (
            "I could not open WhatsApp Desktop."
        )

    # ========================================================
    # OPEN CHAT
    # ========================================================

    if action in (
        "open_chat",
        "chat",
        "search_contact",
        "find_contact",
    ):

        return _open_chat(
            receiver,
            contact_index=contact_index,
        )

    # ========================================================
    # SEND MESSAGE
    # ========================================================

    if action in (
        "send_message",
        "send",
    ):

        return _send_message(
            receiver,
            message_text,
            contact_index=contact_index,
        )

    # ========================================================
    # REPLY
    # ========================================================

    if action in (
        "reply",
        "send_reply",
    ):

        return _reply(
            message_text
        )

    # ========================================================
    # STATUS
    # ========================================================

    if action == "status":

        window = _find_whatsapp_window()

        if window:

            return (
                "WhatsApp Desktop is running."
            )

        return (
            "WhatsApp Desktop is not running."
        )

    # ========================================================
    # UNKNOWN
    # ========================================================

    return (
        "Unknown WhatsApp action. "
        "Use open_chat, send_message, "
        "reply, focus, or status."
    )


# ============================================================
# COMPATIBILITY ALIAS
# ============================================================

def whatsapp_control_tool(
    parameters=None,
    response=None,
    player=None,
):

    return whatsapp_control(
        parameters=parameters,
        response=response,
        player=player,
    )