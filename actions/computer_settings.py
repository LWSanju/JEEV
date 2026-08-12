import os
import re
import subprocess
import time


# ============================================================
# JEEV — WINDOWS COMPUTER SETTINGS
# Dynamic application control
# ============================================================


# ============================================================
# NAME NORMALIZATION
# ============================================================

def _normalize_name(name):
    """
    Normalize a human application name so it can be compared
    against Windows process names.
    """

    name = str(name or "").strip().lower()

    # Remove quotes and punctuation
    name = re.sub(
        r"[^\w\s.\-]",
        "",
        name,
    )

    # Convert separators to spaces
    name = name.replace("-", " ")
    name = name.replace("_", " ")

    # Remove common executable suffix
    if name.endswith(".exe"):
        name = name[:-4]

    # Collapse whitespace
    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    # Common speech variations.
    # These are NOT application mappings.
    # They only clean up what speech recognition may produce.
    aliases = {
        "vs code": "visual studio code",
        "vscode": "visual studio code",
        "ms edge": "microsoft edge",
        "chrome browser": "google chrome",
        "windows explorer": "file explorer",
        "file explorer": "explorer",
    }

    return aliases.get(
        name,
        name,
    )


# ============================================================
# GET ALL CURRENTLY RUNNING PROCESSES
# ============================================================

def _get_running_processes():
    """
    Dynamically retrieves all running Windows processes.

    Returns:

        [
            {
                "name": "Spotify.exe",
                "process_name": "Spotify",
                "pid": 1234,
            },
            ...
        ]

    No application list is required.
    """

    processes = []

    try:

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    "Get-Process | "
                    "Select-Object "
                    "ProcessName,Id | "
                    "ForEach-Object { "
                    "$_.ProcessName + '|' + $_.Id "
                    "}"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return []

        for line in result.stdout.splitlines():

            line = line.strip()

            if not line:
                continue

            parts = line.split("|")

            if len(parts) != 2:
                continue

            process_name = parts[0].strip()
            pid_text = parts[1].strip()

            if not process_name:
                continue

            if not pid_text.isdigit():
                continue

            processes.append(
                {
                    "name": (
                        process_name
                        + ".exe"
                    ),
                    "process_name": process_name,
                    "pid": int(pid_text),
                }
            )

    except Exception as e:

        print(
            "[JEEV] ⚠️ "
            f"Could not read processes: {e}"
        )

    return processes


# ============================================================
# PROCESS NAME WITHOUT SPACES / PUNCTUATION
# ============================================================

def _compact_name(name):

    name = _normalize_name(name)

    return re.sub(
        r"[^a-z0-9]",
        "",
        name,
    )


# ============================================================
# FIND BEST PROCESS MATCH
# ============================================================

def _find_application_processes(
    application_name
):
    """
    Dynamically finds the best matching running processes.

    Example:

        "Spotify"
            → Spotify.exe

        "Blender"
            → blender.exe

        "Visual Studio Code"
            → Code.exe

        "Adobe Photoshop"
            → Photoshop.exe

    No hardcoded application database is required.
    """

    target = _normalize_name(
        application_name
    )

    if not target:
        return []

    target_compact = _compact_name(
        target
    )

    if not target_compact:
        return []

    processes = _get_running_processes()

    scored = []

    for process in processes:

        process_name = process[
            "process_name"
        ]

        process_normalized = (
            _normalize_name(
                process_name
            )
        )

        process_compact = _compact_name(
            process_normalized
        )

        if not process_compact:
            continue

        score = 0

        # ----------------------------------------------------
        # Exact match
        # ----------------------------------------------------

        if (
            target_compact
            == process_compact
        ):

            score = 1000


        # ----------------------------------------------------
        # Target starts with process
        #
        # "chrome" → chrome
        # ----------------------------------------------------

        elif process_compact.startswith(
            target_compact
        ):

            score = 850


        # ----------------------------------------------------
        # Process starts with target
        #
        # "photoshop" → photoshop2026
        # ----------------------------------------------------

        elif target_compact.startswith(
            process_compact
        ):

            score = 800


        # ----------------------------------------------------
        # Target contained in process
        # ----------------------------------------------------

        elif target_compact in process_compact:

            score = 700


        # ----------------------------------------------------
        # Process contained in target
        # ----------------------------------------------------

        elif process_compact in target_compact:

            score = 650


        # ----------------------------------------------------
        # Multi-word matching
        #
        # "Adobe Photoshop"
        #       ↓
        # "photoshop"
        # ----------------------------------------------------

        else:

            target_words = [
                word
                for word in target.split()
                if len(word) >= 3
            ]

            process_words = [
                word
                for word in process_normalized.split()
                if len(word) >= 3
            ]

            common_words = set(
                target_words
            ) & set(
                process_words
            )

            if common_words:

                score = (
                    400
                    + (
                        len(common_words)
                        * 100
                    )
                )


            # ------------------------------------------------
            # Check each meaningful target word against the
            # process name.
            # ------------------------------------------------

            if score == 0:

                for word in target_words:

                    compact_word = (
                        _compact_name(
                            word
                        )
                    )

                    if (
                        len(compact_word)
                        >= 4
                        and compact_word
                        in process_compact
                    ):

                        score = max(
                            score,
                            500,
                        )


        if score > 0:

            scored.append(
                (
                    score,
                    process,
                )
            )

    # Highest confidence first
    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    # --------------------------------------------------------
    # Don't blindly kill multiple unrelated processes.
    #
    # If we have an exact match, return exact matches.
    # Otherwise return the strongest match.
    # --------------------------------------------------------

    if not scored:
        return []

    highest_score = scored[0][0]

    if highest_score >= 1000:

        return [
            process
            for score, process
            in scored
            if score >= 1000
        ]

    # For normal fuzzy matches, only take the strongest
    # candidate(s).
    return [
        process
        for score, process
        in scored
        if score == highest_score
    ]


# ============================================================
# GET PROCESS IDS
# ============================================================

def _get_process_ids(
    process_names
):

    if not process_names:
        return []

    wanted = {
        _normalize_name(name)
        for name in process_names
    }

    ids = []

    for process in _get_running_processes():

        if (
            _normalize_name(
                process["name"]
            )
            in wanted
        ):

            ids.append(
                process["pid"]
            )

    return list(
        dict.fromkeys(ids)
    )


# ============================================================
# TERMINATE PROCESS TREE
# ============================================================

def _terminate_process(
    process
):
    """
    Terminates the selected process and its child processes.

    /T = terminate child processes too
    /F = force termination
    """

    process_name = process[
        "process_name"
    ]

    pid = process[
        "pid"
    ]

    print(
        "[JEEV] 🔴 Terminating:",
        f"{process_name}.exe",
        f"(PID {pid})",
    )

    try:

        result = subprocess.run(
            [
                "taskkill",
                "/F",
                "/T",
                "/PID",
                str(pid),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:

            return True

        print(
            "[JEEV] ⚠️ taskkill failed:",
            result.stderr.strip(),
        )

    except Exception as e:

        print(
            "[JEEV] ⚠️ "
            f"Termination error: {e}"
        )

    return False


# ============================================================
# CHECK WHETHER PROCESS IS STILL RUNNING
# ============================================================

def _is_process_running(
    process
):

    target_pid = process[
        "pid"
    ]

    target_name = (
        process[
            "process_name"
        ].lower()
    )

    for current in _get_running_processes():

        if current["pid"] == target_pid:
            return True

        # Some applications restart with a new PID.
        # Keep the name check available separately.
        if (
            current["process_name"]
            .lower()
            == target_name
        ):
            return True

    return False


# ============================================================
# VERIFY PROCESS CLOSED
# ============================================================

def _verify_closed(
    processes,
    timeout=5.0,
):
    """
    Wait and repeatedly verify that the application process
    has disappeared.

    This prevents JEEV from claiming success just because
    taskkill returned.
    """

    deadline = (
        time.time()
        + timeout
    )

    while time.time() < deadline:

        still_running = False

        current_processes = (
            _get_running_processes()
        )

        for original in processes:

            original_pid = original[
                "pid"
            ]

            original_name = (
                original[
                    "process_name"
                ].lower()
            )

            for current in current_processes:

                current_pid = current[
                    "pid"
                ]

                current_name = (
                    current[
                        "process_name"
                    ].lower()
                )

                # Same process
                if (
                    current_pid
                    == original_pid
                ):

                    still_running = True
                    break

                # Same executable restarted
                if (
                    current_name
                    == original_name
                ):

                    still_running = True
                    break

            if still_running:
                break

        if not still_running:

            return True

        time.sleep(0.5)

    return False


# ============================================================
# CLOSE APPLICATION DYNAMICALLY
# ============================================================

def _close_application(
    application_name
):
    """
    Dynamically closes virtually any currently running
    Windows application.

    No application needs to be manually registered.
    """

    application_name = str(
        application_name or ""
    ).strip()

    if not application_name:

        return (
            False,
            "No application name was provided.",
        )

    print(
        "[JEEV] 🔎 Searching running applications for:",
        application_name,
    )

    # --------------------------------------------------------
    # Find the actual running process.
    # --------------------------------------------------------

    matches = (
        _find_application_processes(
            application_name
        )
    )

    if not matches:

        return (
            False,
            f"I couldn't find a running application "
            f"matching '{application_name}'.",
        )

    print(
        "[JEEV] 🎯 Matched:",
        [
            f"{p['process_name']}.exe "
            f"(PID {p['pid']})"
            for p in matches
        ],
    )

    # --------------------------------------------------------
    # Safety check:
    #
    # Don't allow a very weak fuzzy match to accidentally
    # terminate something unrelated.
    # --------------------------------------------------------

    # The matching engine already requires meaningful
    # similarity. We only terminate the selected best match.
    # --------------------------------------------------------

    terminated_any = False

    for process in matches:

        if _terminate_process(
            process
        ):

            terminated_any = True

    if not terminated_any:

        return (
            False,
            f"I couldn't terminate '{application_name}'.",
        )

    # --------------------------------------------------------
    # VERIFY
    # --------------------------------------------------------

    if _verify_closed(
        matches,
        timeout=5.0,
    ):

        print(
            "[JEEV] ✅ Confirmed closed:",
            application_name,
        )

        return (
            True,
            f"{application_name} has been closed successfully.",
        )

    # --------------------------------------------------------
    # One controlled retry.
    # --------------------------------------------------------

    print(
        "[JEEV] ⚠️ Application still running. "
        "Attempting one final termination.",
    )

    current_matches = (
        _find_application_processes(
            application_name
        )
    )

    for process in current_matches:

        _terminate_process(
            process
        )

    if _verify_closed(
        current_matches,
        timeout=3.0,
    ):

        print(
            "[JEEV] ✅ Confirmed closed after retry:",
            application_name,
        )

        return (
            True,
            f"{application_name} has been closed successfully.",
        )

    return (
        False,
        f"I could not completely close "
        f"{application_name}. The application "
        f"is still running.",
    )


# ============================================================
# MAIN COMPUTER SETTINGS FUNCTION
# ============================================================

def computer_settings(
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

    description = str(
        parameters.get(
            "description",
            "",
        )
    ).strip()

    value = parameters.get(
        "value"
    )

    try:

        # ====================================================
        # VOLUME
        # ====================================================

        if action in (
            "volume_up",
            "volume_down",
            "mute",
        ):

            import ctypes

            VK_VOLUME_MUTE = 0xAD
            VK_VOLUME_DOWN = 0xAE
            VK_VOLUME_UP = 0xAF

            key = {
                "volume_up": VK_VOLUME_UP,
                "volume_down": VK_VOLUME_DOWN,
                "mute": VK_VOLUME_MUTE,
            }[action]

            ctypes.windll.user32.keybd_event(
                key,
                0,
                0,
                0,
            )

            ctypes.windll.user32.keybd_event(
                key,
                0,
                2,
                0,
            )

            return (
                f"Volume action "
                f"'{action}' completed."
            )


        # ====================================================
        # CLOSE APPLICATION
        # ====================================================

        if action in (
            "close",
            "close_app",
            "close_application",
            "terminate",
            "quit",
        ):

            app_name = (
                value
                or description
            )

            success, message = (
                _close_application(
                    app_name
                )
            )

            # Return the REAL result.
            return message


        # ====================================================
        # LOCK
        # ====================================================

        if action == "lock":

            subprocess.run(
                [
                    "rundll32.exe",
                    "user32.dll,LockWorkStation",
                ]
            )

            return "Computer locked."


        # ====================================================
        # RESTART
        # ====================================================

        if action == "restart":

            subprocess.run(
                [
                    "shutdown",
                    "/r",
                    "/t",
                    "5",
                ]
            )

            return (
                "Computer will restart "
                "in 5 seconds."
            )


        # ====================================================
        # SHUTDOWN
        # ====================================================

        if action == "shutdown":

            subprocess.run(
                [
                    "shutdown",
                    "/s",
                    "/t",
                    "5",
                ]
            )

            return (
                "Computer will shut down "
                "in 5 seconds."
            )


        # ====================================================
        # REFRESH
        # ====================================================

        if action in (
            "refresh",
            "reload",
        ):

            import ctypes

            VK_F5 = 0x74

            ctypes.windll.user32.keybd_event(
                VK_F5,
                0,
                0,
                0,
            )

            ctypes.windll.user32.keybd_event(
                VK_F5,
                0,
                2,
                0,
            )

            return "Screen refreshed."


        # ====================================================
        # WINDOWS SETTINGS
        # ====================================================

        if action in (
            "settings",
            "open_settings",
        ):

            subprocess.Popen(
                [
                    "cmd",
                    "/c",
                    "start",
                    "",
                    "ms-settings:",
                ]
            )

            return (
                "Windows Settings opened."
            )


        # ====================================================
        # FULLSCREEN
        # ====================================================

        if action == "fullscreen":

            import ctypes

            VK_F11 = 0x7A

            ctypes.windll.user32.keybd_event(
                VK_F11,
                0,
                0,
                0,
            )

            ctypes.windll.user32.keybd_event(
                VK_F11,
                0,
                2,
                0,
            )

            return (
                "Fullscreen toggled."
            )


        # ====================================================
        # UNKNOWN ACTION
        # ====================================================

        return (
            f"Computer setting action "
            f"'{action}' completed."
        )


    except Exception as e:

        return (
            f"Computer settings failed: {e}"
        )

