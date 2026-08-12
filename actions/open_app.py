import os
import time
import re
import subprocess
import webbrowser
from pathlib import Path


# ============================================================
# JEEV — WINDOWS APPLICATION LAUNCHER
# ============================================================

WHATSAPP_DESKTOP_APP_ID = (
    "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"
)


# ============================================================
# NAME HELPERS
# ============================================================

def _normalize_name(name):
    name = str(name or "").strip().lower()

    name = name.replace('"', "").replace("'", "")

    if name.endswith(".exe"):
        name = name[:-4]

    if name.endswith(".lnk"):
        name = name[:-4]

    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()

    aliases = {
        "vs code": "visual studio code",
        "vscode": "visual studio code",
        "ms edge": "microsoft edge",
        "edge browser": "microsoft edge",
        "chrome browser": "google chrome",
        "file explorer": "explorer",
        "windows explorer": "explorer",
        "whatsapp desktop": "whatsapp",
        "whatsapp application": "whatsapp",
    }

    return aliases.get(name, name)


def _compact_name(name):
    return re.sub(
        r"[^a-z0-9]",
        "",
        _normalize_name(name)
    )


# ============================================================
# START MENU
# ============================================================

def _start_menu_locations():
    locations = []

    appdata = os.environ.get("APPDATA")
    program_data = os.environ.get("PROGRAMDATA")

    if appdata:
        locations.append(
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )

    if program_data:
        locations.append(
            Path(program_data)
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )

    return [
        path
        for path in locations
        if path.exists()
    ]


def _find_start_menu_apps():
    applications = []

    for root in _start_menu_locations():
        try:
            for shortcut in root.rglob("*.lnk"):
                applications.append({
                    "name": shortcut.stem,
                    "path": str(shortcut),
                    "type": "shortcut",
                })

        except Exception as e:
            print(
                "[JEEV] Start Menu scan failed:",
                e
            )

    return applications


# ============================================================
# APPLICATION DIRECTORIES
# ============================================================

def _application_directories():
    directories = []

    for variable in (
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramW6432",
        "LOCALAPPDATA",
        "APPDATA",
    ):
        value = os.environ.get(variable)

        if value:
            path = Path(value)

            if path.exists():
                directories.append(path)

    return directories


def _find_common_executables():
    applications = []

    for root in _application_directories():

        try:

            for directory in root.iterdir():

                if not directory.is_dir():
                    continue

                try:

                    for exe in directory.glob("*.exe"):

                        applications.append({
                            "name": exe.stem,
                            "path": str(exe),
                            "type": "executable",
                        })

                except Exception:
                    continue

        except Exception:
            continue

    return applications


# ============================================================
# PATH APPLICATIONS
# ============================================================

def _find_path_executables():
    applications = []

    for directory in os.environ.get(
        "PATH",
        ""
    ).split(os.pathsep):

        directory = directory.strip()

        if not directory:
            continue

        path = Path(directory)

        if not path.exists():
            continue

        try:

            for exe in path.glob("*.exe"):

                applications.append({
                    "name": exe.stem,
                    "path": str(exe),
                    "type": "path",
                })

        except Exception:
            continue

    return applications


# ============================================================
# DIRECT EXECUTABLE
# ============================================================

def _direct_executable(app_name):

    expanded = os.path.expandvars(
        os.path.expanduser(
            str(app_name)
        )
    )

    path = Path(expanded)

    if path.exists() and path.is_file():

        return {
            "name": path.stem,
            "path": str(path),
            "type": "direct",
        }

    return None


# ============================================================
# APPLICATION MATCHING
# ============================================================

def _score_application(
    requested,
    candidate
):

    requested_normalized = _normalize_name(
        requested
    )

    candidate_normalized = _normalize_name(
        candidate
    )

    requested_compact = _compact_name(
        requested
    )

    candidate_compact = _compact_name(
        candidate
    )

    if not requested_compact:
        return 0

    if not candidate_compact:
        return 0

    if requested_compact == candidate_compact:
        return 1000

    if requested_normalized == candidate_normalized:
        return 950

    if candidate_compact.startswith(
        requested_compact
    ):
        return 850

    if requested_compact.startswith(
        candidate_compact
    ):
        return 800

    if requested_compact in candidate_compact:
        return 750

    if candidate_compact in requested_compact:
        return 700

    requested_words = [
        word
        for word in requested_normalized.split()
        if len(word) >= 3
    ]

    candidate_words = [
        word
        for word in candidate_normalized.split()
        if len(word) >= 3
    ]

    matches = 0

    for word in requested_words:

        compact_word = _compact_name(
            word
        )

        for candidate_word in candidate_words:

            compact_candidate_word = (
                _compact_name(candidate_word)
            )

            if (
                compact_word
                == compact_candidate_word
            ):
                matches += 1
                break

            if (
                len(compact_word) >= 4
                and compact_word
                in compact_candidate_word
            ):
                matches += 1
                break

    if matches:
        return 400 + matches * 100

    return 0


def _build_application_index():

    applications = []

    print(
        "[JEEV] Building Windows application index..."
    )

    applications.extend(
        _find_start_menu_apps()
    )

    applications.extend(
        _find_common_executables()
    )

    applications.extend(
        _find_path_executables()
    )

    unique = {}

    for application in applications:

        try:

            path = os.path.normcase(
                os.path.abspath(
                    application["path"]
                )
            )

            unique[path] = application

        except Exception:
            continue

    applications = list(
        unique.values()
    )

    print(
        "[JEEV] Application index:",
        len(applications),
        "entries"
    )

    return applications


def _find_application(app_name):

    app_name = str(
        app_name or ""
    ).strip()

    if not app_name:
        return None

    direct = _direct_executable(
        app_name
    )

    if direct:
        return direct

    applications = _build_application_index()

    scored = []

    for application in applications:

        score = _score_application(
            app_name,
            application["name"]
        )

        if score > 0:

            scored.append(
                (
                    score,
                    application
                )
            )

    if not scored:
        return None

    scored.sort(
        key=lambda item: item[0],
        reverse=True
    )

    best_score = scored[0][0]

    if best_score < 600:
        return None

    return scored[0][1]


# ============================================================
# NORMAL APPLICATION LAUNCH
# ============================================================

def _launch_application(application):

    if not application:
        return False

    path = application["path"]

    print(
        "[JEEV] Launching:",
        path
    )

    try:

        if application["type"] == "shortcut":

            subprocess.Popen(
                [
                    "cmd",
                    "/c",
                    "start",
                    "",
                    path,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        else:

            subprocess.Popen(
                [path],
                cwd=os.path.dirname(path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        return True

    except Exception as e:

        print(
            "[JEEV] Launch failed:",
            e
        )

        return False


# ============================================================
# FIND REAL WINDOWS APP ID
# ============================================================

def _find_windows_app_id():

    print(
        "[JEEV] Asking Windows for WhatsApp AppID..."
    )

    ps = r'''
$apps = Get-StartApps

foreach ($app in $apps) {

    if (
        $app.Name -like "*WhatsApp*"
    ) {

        Write-Output (
            $app.Name + "|" + $app.AppID
        )
    }
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

        output = (
            result.stdout
            or ""
        ).strip()

        if not output:

            print(
                "[JEEV] Windows returned no WhatsApp AppID."
            )

            return None

        for line in output.splitlines():

            line = line.strip()

            if "|" not in line:
                continue

            name, app_id = line.split(
                "|",
                1
            )

            name = name.strip()
            app_id = app_id.strip()

            if (
                "whatsapp"
                in name.lower()
                and app_id
            ):

                print(
                    "[JEEV] Windows WhatsApp:",
                    name
                )

                print(
                    "[JEEV] WhatsApp AppID:",
                    app_id
                )

                return app_id

    except Exception as e:

        print(
            "[JEEV] AppID lookup failed:",
            e
        )

    return None


# ============================================================
# LAUNCH WINDOWS STORE / MSIX APP
# ============================================================

def _launch_windows_app(app_id):

    if not app_id:
        return False

    print(
        "[JEEV] Launching Windows AppID:",
        app_id
    )

    # --------------------------------------------------------
    # METHOD 1
    # --------------------------------------------------------

    try:

        subprocess.Popen(
            [
                "explorer.exe",
                f"shell:AppsFolder\\{app_id}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return True

    except Exception as e:

        print(
            "[JEEV] Explorer launch failed:",
            e
        )

    # --------------------------------------------------------
    # METHOD 2
    # --------------------------------------------------------

    try:

        command = (
            f'Start-Process '
            f'"shell:AppsFolder\\{app_id}"'
        )

        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return True

    except Exception as e:

        print(
            "[JEEV] PowerShell launch failed:",
            e
        )

    return False


# ============================================================
# WHATSAPP PROCESS CHECK
#
# IMPORTANT:
# This is NOT used to decide whether WhatsApp is already open.
# It is only used AFTER launching.
# ============================================================

def _whatsapp_process_running():

    try:

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-Process | "
                    "Where-Object { "
                    "$_.ProcessName -like '*WhatsApp*' "
                    "} | "
                    "Select-Object -ExpandProperty ProcessName"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        output = (
            result.stdout
            or ""
        ).strip()

        if output:

            print(
                "[JEEV] WhatsApp process detected:",
                output.replace(
                    "\n",
                    ", "
                )
            )

            return True

    except Exception:
        pass

    return False


# ============================================================
# WINDOW SEARCH
# ============================================================

def _find_window_by_title(title):

    if not title:
        return None

    safe_title = (
        str(title)
        .replace("'", "''")
    )

    ps = f"""
$windows = Get-Process |
    Where-Object {{
        $_.MainWindowHandle -ne 0 -and
        $_.MainWindowTitle -and
        $_.MainWindowTitle -like "*{safe_title}*"
    }} |
    Select-Object -First 1 Id,MainWindowHandle,MainWindowTitle

if ($windows) {{
    Write-Output (
        $windows.Id.ToString() + "|" +
        $windows.MainWindowHandle.ToString() + "|" +
        $windows.MainWindowTitle
    )
}}
"""

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

        output = (
            result.stdout
            or ""
        ).strip()

        if not output:
            return None

        parts = output.split(
            "|",
            2
        )

        if len(parts) != 3:
            return None

        return {
            "pid": parts[0].strip(),
            "handle": parts[1].strip(),
            "title": parts[2].strip(),
        }

    except Exception:
        return None


# ============================================================
# FOCUS WINDOW
# ============================================================

def _focus_window(title):

    info = _find_window_by_title(
        title
    )

    if not info:
        return False

    try:

        ps = f"""
$shell = New-Object -ComObject WScript.Shell
$shell.AppActivate({info['pid']})
Start-Sleep -Milliseconds 300
Write-Output "SUCCESS"
"""

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

        return (
            "SUCCESS"
            in (
                result.stdout
                or ""
            )
        )

    except Exception:
        return False


# ============================================================
# WAIT FOR REAL WHATSAPP WINDOW
# ============================================================

def _wait_for_whatsapp_window(
    timeout=20
):

    print(
        "[JEEV] Waiting for actual WhatsApp window..."
    )

    deadline = (
        time.time()
        + timeout
    )

    while time.time() < deadline:

        window = _find_window_by_title(
            "WhatsApp"
        )

        if window:

            print(
                "[JEEV] REAL WhatsApp window found:",
                window["title"]
            )

            _focus_window(
                "WhatsApp"
            )

            return True

        time.sleep(0.5)

    return False


# ============================================================
# OPEN APP
# ============================================================

def open_app(
    parameters=None,
    response=None,
    player=None
):

    parameters = parameters or {}

    app_name = str(
        parameters.get(
            "app_name",
            parameters.get(
                "application",
                parameters.get(
                    "name",
                    ""
                )
            )
        )
    ).strip()

    if not app_name:
        return (
            "No application name was provided."
        )

    key = _normalize_name(
        app_name
    )

    print(
        "[JEEV] Open request:",
        app_name
    )

    # ========================================================
    # WHATSAPP DESKTOP
    # ========================================================

    if key == "whatsapp":

        print(
            "[JEEV] WhatsApp Desktop request detected."
        )

        # IMPORTANT:
        #
        # We DO NOT check for an existing window here.
        #
        # This was causing the false:
        # "WhatsApp is already open"
        #
        # message.
        #
        # Always perform the launch operation.

        app_id = _find_windows_app_id()

        if not app_id:

            print(
                "[JEEV] Using fallback WhatsApp AppID."
            )

            app_id = (
                WHATSAPP_DESKTOP_APP_ID
            )

        launched = _launch_windows_app(
            app_id
        )

        if not launched:

            return (
                "I found WhatsApp Desktop, "
                "but Windows could not launch it."
            )

        # Give Windows a moment to create
        # the WhatsApp process/window.

        time.sleep(1)

        # Wait for the actual visible window.

        if _wait_for_whatsapp_window(
            timeout=20
        ):

            return (
                "Opened WhatsApp Desktop successfully."
            )

        # If the process exists but the window
        # is not visible yet, wait a little longer.

        if _whatsapp_process_running():

            print(
                "[JEEV] WhatsApp process exists, "
                "but the window is not visible yet."
            )

            time.sleep(3)

            if _wait_for_whatsapp_window(
                timeout=8
            ):

                return (
                    "Opened WhatsApp Desktop successfully."
                )

        return (
            "Windows received the WhatsApp launch "
            "command, but the WhatsApp window did "
            "not appear."
        )

    # ========================================================
    # WHATSAPP WEB
    # ========================================================

    if key in (
        "whatsapp web",
        "web whatsapp"
    ):

        try:

            webbrowser.open(
                "https://web.whatsapp.com"
            )

            return (
                "Opened WhatsApp Web."
            )

        except Exception as e:

            return (
                f"Could not open WhatsApp Web: {e}"
            )

    # ========================================================
    # COMMON WEBSITES
    # ========================================================

    websites = {
        "youtube":
            "https://www.youtube.com",

        "google":
            "https://www.google.com",

        "gmail":
            "https://mail.google.com",

        "github":
            "https://github.com",
    }

    if key in websites:

        try:

            webbrowser.open(
                websites[key]
            )

            return (
                f"Opened {app_name}."
            )

        except Exception as e:

            return (
                f"Could not open {app_name}: {e}"
            )

    # ========================================================
    # DIRECT EXECUTABLE
    # ========================================================

    direct = _direct_executable(
        app_name
    )

    if direct:

        print(
            "[JEEV] Direct executable:",
            direct["path"]
        )

        if not _launch_application(
            direct
        ):

            return (
                f"I found {app_name}, "
                "but Windows could not launch it."
            )

        return (
            f"Opened {app_name}."
        )

    # ========================================================
    # DYNAMIC APPLICATION SEARCH
    # ========================================================

    application = _find_application(
        app_name
    )

    if not application:

        return (
            "I couldn't find a Windows application "
            f"matching '{app_name}'."
        )

    print(
        "[JEEV] Matched application:",
        application["name"],
        "->",
        application["path"],
    )

    if not _launch_application(
        application
    ):

        return (
            f"I found {app_name}, "
            "but Windows could not launch it."
        )

    return (
        f"Opened {app_name}."
    )


# ============================================================
# COMPATIBILITY ALIAS
# ============================================================

def open_application(
    parameters=None,
    response=None,
    player=None
):

    return open_app(
        parameters=parameters,
        response=response,
        player=player,
    )