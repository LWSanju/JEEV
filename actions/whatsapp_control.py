import os
import re
import time
import subprocess
from pathlib import Path


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

def _focus_whatsapp():

    window = _find_whatsapp_window()

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

    existing = _find_whatsapp_window()

    if existing:

        print(
            "[JEEV][WhatsApp] "
            "WhatsApp Desktop already running."
        )

        return _focus_whatsapp()

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

            print(
                "[JEEV][WhatsApp] "
                "REAL WhatsApp Desktop launched."
            )

            return _focus_whatsapp()

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

def _open_chat(receiver):

    receiver = _clean_contact(
        receiver
    )

    if not receiver:

        return (
            "No WhatsApp contact name was provided."
        )

    print(
        "[JEEV][WhatsApp] "
        "Opening chat:",
        receiver,
    )

    # --------------------------------------------------------
    # MUST OPEN REAL DESKTOP APP
    # --------------------------------------------------------

    if not _launch_whatsapp():

        return (
            "I could not open or focus "
            "WhatsApp Desktop."
        )

    pyautogui = _keyboard()

    if pyautogui is None:

        return (
            "WhatsApp control needs pyautogui. "
            "Run: pip install pyautogui"
        )

    try:

        # ----------------------------------------------------
        # FINAL SAFETY CHECK
        # ----------------------------------------------------

        if not _focus_whatsapp():

            return (
                "WhatsApp Desktop could not be focused. "
                "I did NOT control Edge."
            )

        time.sleep(0.8)

        # ----------------------------------------------------
        # IMPORTANT
        #
        # Ctrl+F searches messages/chats.
        #
        # Ctrl+N opens the NEW CHAT contact picker.
        #
        # ----------------------------------------------------

        pyautogui.hotkey(
            "ctrl",
            "n",
        )

        time.sleep(0.8)

        # ----------------------------------------------------
        # SEARCH CONTACT
        # ----------------------------------------------------

        pyautogui.write(
            receiver,
            interval=0.04,
        )

        time.sleep(1.5)

        # ----------------------------------------------------
        # SELECT FIRST MATCH
        # ----------------------------------------------------

        pyautogui.press(
            "enter"
        )

        time.sleep(1.2)

        # ----------------------------------------------------
        # VERIFY WHATSAPP STILL OWNS THE FOREGROUND
        # ----------------------------------------------------

        window = _find_whatsapp_window()

        if not window:

            return (
                "WhatsApp Desktop was lost during "
                "contact search. I did NOT continue."
            )

        if _is_browser(
            window.get("process", "")
        ):

            return (
                "A browser became active instead of "
                "WhatsApp Desktop. I did NOT continue."
            )

        print(
            "[JEEV][WhatsApp] "
            "Chat opened:",
            receiver,
        )

        return (
            f"Opened the WhatsApp chat for {receiver}."
        )

    except Exception as e:

        print(
            "[JEEV][WhatsApp] "
            f"Chat opening error: {e}"
        )

        return (
            f"WhatsApp chat opening failed: {e}"
        )

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
    ):

        return _open_chat(
            receiver
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