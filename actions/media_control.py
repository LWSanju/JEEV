
import ctypes
import subprocess
import time


# ============================================================
# WINDOWS MEDIA KEY CODES
# ============================================================

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF


# ============================================================
# PRESS WINDOWS MEDIA KEY
# ============================================================

def _press_media_key(vk_code):
    """
    Sends a real Windows media-key press.
    """

    user32 = ctypes.windll.user32

    user32.keybd_event(
        vk_code,
        0,
        0,
        0,
    )

    user32.keybd_event(
        vk_code,
        0,
        2,
        0,
    )


# ============================================================
# POWERSHELL MEDIA CONTROL
# ============================================================

def _powershell_media_action(action):
    """
    Attempts to control the active Windows media session
    through Windows System Media Transport Controls.

    Returns True when the command was successfully executed.
    """

    action_map = {
        "play": "Play",
        "pause": "Pause",
        "stop": "Stop",
        "next": "Next",
        "previous": "Previous",
    }

    command = action_map.get(action)

    if not command:
        return False

    # Windows.Media.Control is exposed through WinRT.
    #
    # PowerShell can access the media session manager and
    # send transport commands to the active media player.

    ps_script = f"""
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Runtime.WindowsRuntime

[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]

$manager = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync().GetAwaiter().GetResult()

$session = $manager.GetCurrentSession()

if ($null -eq $session) {{
    exit 2
}}

switch ("{command}") {{
    "Play" {{
        $session.TryPlayAsync().GetAwaiter().GetResult()
    }}

    "Pause" {{
        $session.TryPauseAsync().GetAwaiter().GetResult()
    }}

    "Stop" {{
        $session.TryStopAsync().GetAwaiter().GetResult()
    }}

    "Next" {{
        $session.TrySkipNextAsync().GetAwaiter().GetResult()
    }}

    "Previous" {{
        $session.TrySkipPreviousAsync().GetAwaiter().GetResult()
    }}
}}

exit 0
"""

    try:

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps_script,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        return result.returncode == 0

    except Exception as e:

        print(
            f"[Media] PowerShell control failed: {e}"
        )

        return False


# ============================================================
# MEDIA CONTROL
# ============================================================

def media_control(
    parameters=None,
    player=None,
):

    parameters = parameters or {}

    action = str(
        parameters.get(
            "action",
            "",
        )
    ).lower().strip()

    # Normalize common AI-generated action names.

    aliases = {
        "resume": "play",
        "continue": "play",
        "start": "play",

        "play music": "play",
        "resume music": "play",
        "continue music": "play",

        "pause music": "pause",

        "skip": "next",
        "next song": "next",
        "next music": "next",

        "previous song": "previous",
        "previous music": "previous",
        "prev": "previous",

        "playpause": "play_pause",
        "play/pause": "play_pause",
        "toggle": "play_pause",
        "toggle_playback": "play_pause",

        "stop music": "stop",

        "louder": "volume_up",
        "increase volume": "volume_up",

        "quieter": "volume_down",
        "decrease volume": "volume_down",

        "unmute": "mute",
    }

    action = aliases.get(
        action,
        action,
    )

    print(
        f"[Media] Requested action: {action}"
    )

    # ========================================================
    # EXPLICIT PLAY / RESUME
    # ========================================================

    if action == "play":

        success = _powershell_media_action(
            "play"
        )

        if success:

            return (
                "Playback resumed."
            )

        # Fallback to Windows media key.

        _press_media_key(
            VK_MEDIA_PLAY_PAUSE
        )

        time.sleep(0.15)

        return (
            "Playback resume command sent."
        )

    # ========================================================
    # EXPLICIT PAUSE
    # ========================================================

    if action == "pause":

        success = _powershell_media_action(
            "pause"
        )

        if success:

            return (
                "Playback paused."
            )

        _press_media_key(
            VK_MEDIA_PLAY_PAUSE
        )

        time.sleep(0.15)

        return (
            "Playback pause command sent."
        )

    # ========================================================
    # TOGGLE PLAY / PAUSE
    # ========================================================

    if action == "play_pause":

        _press_media_key(
            VK_MEDIA_PLAY_PAUSE
        )

        time.sleep(0.15)

        return (
            "Playback toggled."
        )

    # ========================================================
    # NEXT
    # ========================================================

    if action == "next":

        success = _powershell_media_action(
            "next"
        )

        if success:

            return (
                "Next track."
            )

        _press_media_key(
            VK_MEDIA_NEXT_TRACK
        )

        return (
            "Next track command sent."
        )

    # ========================================================
    # PREVIOUS
    # ========================================================

    if action == "previous":

        success = _powershell_media_action(
            "previous"
        )

        if success:

            return (
                "Previous track."
            )

        _press_media_key(
            VK_MEDIA_PREV_TRACK
        )

        return (
            "Previous track command sent."
        )

    # ========================================================
    # STOP
    # ========================================================

    if action == "stop":

        success = _powershell_media_action(
            "stop"
        )

        if success:

            return (
                "Playback stopped."
            )

        _press_media_key(
            VK_MEDIA_STOP
        )

        return (
            "Playback stop command sent."
        )

    # ========================================================
    # VOLUME
    # ========================================================

    if action == "volume_up":

        _press_media_key(
            VK_VOLUME_UP
        )

        return (
            "Volume increased."
        )

    if action == "volume_down":

        _press_media_key(
            VK_VOLUME_DOWN
        )

        return (
            "Volume decreased."
        )

    if action == "mute":

        _press_media_key(
            VK_VOLUME_MUTE
        )

        return (
            "Mute toggled."
        )

    # ========================================================
    # UNKNOWN
    # ========================================================

    return (
        f"Unknown media action: {action}"
    )

