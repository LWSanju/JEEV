import time
import subprocess
from desktop.uia import find, get_elements
from desktop.window_manager import (
    get_foreground_window,
    focus_window,
    launch_start_app,
)
from desktop.observer import observe
from desktop.navigator import (
    type_text,
    press,
    hotkey,
)
from desktop.state import STATE

try:
    from .robocorp_desktop import (
        robocorp_available,
        robocorp_focus_executable,
        robocorp_send_keys,
    )
except Exception:
    def robocorp_available(): return False
    def robocorp_focus_executable(*args, **kwargs): return False
    def robocorp_send_keys(*args, **kwargs): return False


SPOTIFY_PROCESS = "Spotify.exe"

# Last search is kept so a natural follow-up like "play that song"
# can activate the result that was just searched.
_LAST_SEARCH_QUERY = ""


def _find_spotify_windows():

    windows = []

    # Use PowerShell to identify the real Spotify process
    # and its main window handle.
    script = r"""
Get-Process Spotify -ErrorAction SilentlyContinue |
Where-Object { $_.MainWindowHandle -ne 0 } |
Select-Object Id, MainWindowHandle, MainWindowTitle |
ConvertTo-Json -Compress
"""

    try:

        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
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
            return []

        import json

        data = json.loads(
            output
        )

        if isinstance(
            data,
            dict
        ):
            data = [data]

        return data

    except Exception:
        return []


def _focus_spotify():

    # Robocorp first: current robocorp-windows uses native Windows UI
    # Automation and can foreground the real Spotify executable without
    # relying on a browser title.
    if robocorp_available():
        try:
            if robocorp_focus_executable("Spotify.exe"):
                STATE.update(application="Spotify", last_action="focus")
                return True
        except Exception:
            pass

    # -------------------------------------------------
    # Method 1:
    # Real Spotify process/window
    # -------------------------------------------------

    windows = (
        _find_spotify_windows()
    )

    if windows:

        try:

            hwnd = int(
                windows[0][
                    "MainWindowHandle"
                ]
            )

            from desktop.window_manager import (
                focus_hwnd
            )

            if focus_hwnd(hwnd):

                STATE.update(

                    application="Spotify",

                    window_title=
                        windows[0].get(
                            "MainWindowTitle",
                            "Spotify"
                        ),

                    last_action="focus"
                )

                return True

        except Exception:
            pass

    # -------------------------------------------------
    # Method 2:
    # Normal title discovery
    # -------------------------------------------------

    if focus_window(
        "Spotify"
    ):

        STATE.update(
            application="Spotify",
            last_action="focus"
        )

        return True

    return False


def _ensure_spotify():

    if _focus_spotify():
        return True

    # Try launching it.
    launched = launch_start_app(
        "Spotify"
    )

    if launched:

        # Give Spotify time to initialize.
        time.sleep(
            2.5
        )

        if _focus_spotify():
            return True

    return False



def _spotify_accessibility_playing(expected=None):
    """Best-effort UIA check. Never treat lack of UIA text as proof of failure."""
    expected_key = str(expected or "").strip().lower()
    try:
        elements = get_elements(max_items=2500)
        texts = []
        for e in elements:
            for key in ("name", "title", "value", "description"):
                v = str(e.get(key, "") or "").strip()
                if v:
                    texts.append(v.lower())
        joined = " | ".join(texts)
        playing = any(x in joined for x in (
            "pause", "now playing", "currently playing", "playing"
        ))
        expected_seen = (not expected_key) or (expected_key in joined)
        return bool(playing and expected_seen)
    except Exception:
        return False


def _verify_spotify_playback(expected=None, timeout=3.0):
    """Best-effort verification; Spotify WebView UIA is not authoritative."""
    deadline = time.time() + float(timeout)
    while time.time() < deadline:
        if _spotify_accessibility_playing(expected):
            return True
        time.sleep(0.25)
    return False


def _keyboard_select_spotify_result(index):
    """Fallback for WebView versions that expose no result rows.

    Spotify search keeps keyboard focus in the search/result surface. Moving
    down N-1 times then Enter selects the requested visible result rather than
    blindly pressing Enter for result #1.
    """
    try:
        n=max(1,int(index or 1))
        for _ in range(n-1):
            press("down")
            time.sleep(0.08)
        press("enter")
        return True
    except Exception as exc:
        print(f"[JEEV][Spotify] Keyboard result selection failed: {exc}")
        return False


def _play_last_or_named_result(search_term="", index=0):
    """Select and play result N from the CURRENT Spotify search.

    Result numbering is 1-based. Navigation is keyboard-only: no mouse clicks
    or coordinate-based selection are used. If no index is supplied, result #1
    is used.
    """
    global _LAST_SEARCH_QUERY
    term=str(search_term or _LAST_SEARCH_QUERY or "").strip()
    if not term:
        return {"ok":False,"verified":False,"error":"No Spotify search result is available to play. Search for a song first."}
    try:
        requested=max(1,int(index or 1))
    except Exception:
        requested=1

    if not _ensure_spotify():
        return {"ok":False,"verified":False,"error":"Spotify Desktop could not be located or opened."}

    # Always re-focus before interacting with search results.
    _focus_spotify()
    time.sleep(0.25)

    # Keyboard-only navigation. Never use the mouse to select Spotify results.
    method="keyboard_result_navigation"
    if not _keyboard_select_spotify_result(requested):
        return {"ok":False,"verified":False,"error":f"Could not select Spotify search result {requested}."}
    time.sleep(1.0)

    verified=_verify_spotify_playback(term,timeout=2.5)
    STATE.update(application="Spotify",last_action="play_result",last_target=term,last_result_index=requested)
    return {
        "ok":True,
        "verified":bool(verified),
        "method":method,
        "result_index":requested,
        "available_results":0,
        "message":f"Spotify result {requested} selected from the current search for '{term}'.",
    }

def _spotify_foreground():
    try:
        import ctypes
        hwnd=ctypes.windll.user32.GetForegroundWindow()
        if not hwnd: return False
        buf=ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd,buf,512)
        return "spotify" in buf.value.lower()
    except Exception: return False

def spotify_control(
    parameters=None,
    player=None
):

    parameters = (
        parameters
        or {}
    )

    action = str(
        parameters.get(
            "action",
            ""
        )
    ).strip().lower()

    query = str(
        parameters.get("query")
        or parameters.get("text")
        or ""
    ).strip()

    name = str(
        parameters.get(
            "name",
            ""
        )
    ).strip()

    description = str(
        parameters.get(
            "description",
            ""
        )
    ).strip()

    index = int(
        parameters.get(
            "index",
            0
        )
        or 0
    )

    # ==============================================
    # OPEN / FOCUS
    # ==============================================

    if action in (
        "open",
        "focus"
    ):

        ok = _ensure_spotify()

        foreground = (
            get_foreground_window()
        )

        return {

            "ok":
                ok,

            "verified":
                ok,

            "foreground":
                foreground,

            "message":
                (
                    "Spotify Desktop is focused."
                    if ok
                    else
                    "Could not locate or open "
                    "Spotify Desktop."
                )
        }

    # ==============================================
    # EVERYTHING ELSE REQUIRES SPOTIFY
    # ==============================================

    if not _ensure_spotify():

        return {

            "ok": False,

            "error":
                "Spotify Desktop could not "
                "be located or opened."
        }

    # ==============================================
    # SEARCH
    # ==============================================

    if action in (
        "search",
        "find"
    ):

        if not query:

            return {

                "ok": False,

                "error":
                    "Spotify search query "
                    "is required."
            }

        # IMPORTANT: search must NEVER activate/play the selected result.
        # Use Spotify's search-focus shortcut only, then replace the text.
        # Do not press Enter and do not send any playback/navigation key here.
        # Ctrl+K is used to focus Spotify's search field. No Enter is sent here,
        # so searching never activates a track.
        searched = False

        # Prefer the existing JEEV keyboard path: it is faster and avoids
        # Robocorp's window lookup overhead on every search.
        try:
            hotkey("ctrl+k")
            time.sleep(0.12)
            type_text(query, clear=True)
            searched = True
        except Exception as exc:
            print(f"[JEEV][Spotify] Native search input failed: {exc}")

        # Robocorp is only a fallback if the native keyboard path failed.
        # It deliberately sends NO Enter/Return after the query.
        if not searched and robocorp_available():
            try:
                if robocorp_send_keys("{CTRL}k"):
                    time.sleep(0.12)
                    robocorp_send_keys("{CTRL}a")
                    robocorp_send_keys(query)
                    searched = True
            except Exception as exc:
                print(f"[JEEV][Spotify] Robocorp search input failed: {exc}")

        if not searched:
            return {
                "ok": False,
                "error": "Could not focus Spotify search without activating playback."
            }

        # Short default wait. Spotify normally begins rendering results while
        # this controller returns; play_result performs its own row detection.
        wait_time = float(
            parameters.get(
                "wait",
                0.65
            )
        )
        time.sleep(max(0.0, min(wait_time, 2.0)))

        global _LAST_SEARCH_QUERY
        _LAST_SEARCH_QUERY = query

        STATE.update(

            application="Spotify",

            last_action="search",

            last_query=query,

            last_target=query
        )

        return {

            "ok": True,

            "action":
                "search",

            "query":
                query,

            "message":
                f"Spotify searched for '{query}'.",

            "observation":
                observe(
                    include_screenshot=False,
                    max_elements=500
                )
        }

    # ==============================================
    # PLAY RESULT
    # ==============================================

    if action in (
        "play_result",
        "select_result"
    ):

        return _play_last_or_named_result(
            name or description or query,
            index=index,
        )

    # ==============================================
    # PLAY / PAUSE
    # ==============================================

    if action == "play":
        # If a song was searched, 'play' should play that result rather than
        # merely pressing Space on whatever Spotify currently has selected.
        target = name or query or _LAST_SEARCH_QUERY
        if target:
            return _play_last_or_named_result(target, index=index)

        if not _spotify_foreground():
            return {"ok": False, "verified": False, "error": "Spotify is not the active window; playback was not verified."}
        press("space")
        time.sleep(0.5)
        verified = _verify_spotify_playback(timeout=2.0)
        return {
            "ok": True,
            "verified": bool(verified),
            "message": "Spotify playback command sent."
        }

    if action == "pause":
        if not _spotify_foreground():
            return {"ok": False, "verified": False, "error": "Spotify is not the active window."}
        press("space")
        time.sleep(0.5)
        return {
            "ok": True,
            "verified": False,
            "message": "Spotify pause command sent."
        }

    # ==============================================
    # NEXT
    # ==============================================

    if action == "next":

        hotkey(
            "ctrl+right"
        )

        return {

            "ok": True,

            "message":
                "Next Spotify track requested."
        }

    # ==============================================
    # PREVIOUS
    # ==============================================

    if action == "previous":

        hotkey(
            "ctrl+left"
        )

        return {

            "ok": True,

            "message":
                "Previous Spotify track requested."
        }

    # ==============================================
    # OBSERVE
    # ==============================================

    if action in (
        "observe",
        "inspect"
    ):

        return observe(
            include_screenshot=
                bool(
                    parameters.get(
                        "include_screenshot",
                        False
                    )
                ),

            max_elements=
                int(
                    parameters.get(
                        "max_elements",
                        500
                    )
                )
        )

    return {

        "ok": False,

        "error":
            f"Unknown Spotify action: {action}"
    }