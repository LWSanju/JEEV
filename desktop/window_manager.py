import ctypes
import subprocess
import time


USER32 = ctypes.windll.user32

SW_RESTORE = 9


def _enum_windows():

    results = []

    @ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p
    )
    def callback(hwnd, _):

        if not USER32.IsWindowVisible(hwnd):
            return True

        length = USER32.GetWindowTextLengthW(hwnd)

        if length <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(
            length + 1
        )

        USER32.GetWindowTextW(
            hwnd,
            buffer,
            length + 1
        )

        title = buffer.value.strip()

        if not title:
            return True

        pid = ctypes.c_ulong()

        USER32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(pid)
        )

        results.append({
            "hwnd": int(hwnd),
            "pid": int(pid.value),
            "title": title,
        })

        return True

    USER32.EnumWindows(
        callback,
        0
    )

    return results


def windows():
    return _enum_windows()


def find_window(title_contains):

    needle = str(
        title_contains or ""
    ).strip().lower()

    if not needle:
        return None

    for item in _enum_windows():

        if needle in item["title"].lower():
            return item

    return None


def get_foreground_window():

    hwnd = int(
        USER32.GetForegroundWindow()
    )

    if not hwnd:
        return None

    length = USER32.GetWindowTextLengthW(
        hwnd
    )

    buffer = ctypes.create_unicode_buffer(
        max(length + 1, 2)
    )

    USER32.GetWindowTextW(
        hwnd,
        buffer,
        len(buffer)
    )

    pid = ctypes.c_ulong()

    USER32.GetWindowThreadProcessId(
        hwnd,
        ctypes.byref(pid)
    )

    return {
        "hwnd": hwnd,
        "pid": int(pid.value),
        "title": buffer.value.strip(),
    }


def focus_hwnd(hwnd):

    try:

        hwnd = int(hwnd)

        USER32.ShowWindow(
            hwnd,
            SW_RESTORE
        )

        USER32.SetForegroundWindow(
            hwnd
        )

        time.sleep(0.25)

        return (
            int(USER32.GetForegroundWindow())
            == hwnd
        )

    except Exception:
        return False


def focus_window(title_contains):

    item = find_window(
        title_contains
    )

    if not item:
        return False

    return focus_hwnd(
        item["hwnd"]
    )


def launch_start_app(name):

    name = str(
        name or ""
    ).strip()

    if not name:
        return False

    safe_name = (
        name
        .replace("'", "''")
    )

    script = f"""
$apps = Get-StartApps |
    Where-Object {{
        $_.Name -like '*{safe_name}*'
    }}

if ($apps) {{

    $app = $apps |
        Select-Object -First 1

    Start-Process (
        'shell:AppsFolder\\' +
        $app.AppID
    )

    Write-Output 'JEEV_OK'
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
                script
            ],
            capture_output=True,
            text=True,
            timeout=10
        )

        return (
            "JEEV_OK"
            in (result.stdout or "")
        )

    except Exception:
        return False