"""JEEV desktop automation bridge for robocorp-windows.

This is deliberately a small adapter instead of making the whole JEEV
application depend on Robot Framework. It uses the current Robocorp
Windows UIAutomation package directly from Python and returns False when
Robocorp is unavailable so the existing JEEV fallbacks remain usable.
"""

from __future__ import annotations

from typing import Optional


try:
    from robocorp import windows as _windows
except Exception:  # pragma: no cover - depends on release environment
    _windows = None


def robocorp_available() -> bool:
    return _windows is not None


def _timeout(value: float = 0.9) -> float:
    try:
        return max(0.1, float(value))
    except Exception:
        return 0.9


def robocorp_find_window(locator: str, timeout: float = 0.9):
    if _windows is None:
        return None
    try:
        return _windows.find_window(
            locator,
            timeout=_timeout(timeout),
            wait_time=0.0,
            foreground=True,
            raise_error=False,
        )
    except Exception:
        return None


def robocorp_focus_executable(executable: str, timeout: float = 0.9) -> bool:
    """Find and foreground a native application by executable name."""
    window = robocorp_find_window(
        f"executable:{executable}",
        timeout=timeout,
    )
    if window is None:
        return False
    try:
        window.foreground_window()
        return bool(window.is_active())
    except Exception:
        return True


def robocorp_focus_handle(hwnd: int, timeout: float = 0.9) -> bool:
    """Foreground an already verified native window handle."""
    try:
        handle = int(hwnd)
    except Exception:
        return False
    if handle <= 0:
        return False

    window = robocorp_find_window(
        f"handle:{handle}",
        timeout=timeout,
    )
    if window is None:
        return False
    try:
        window.foreground_window()
        return bool(window.is_active())
    except Exception:
        return True


def robocorp_send_keys(keys: str, interval: float = 0.01) -> bool:
    """Send keys to the current foreground Windows application."""
    if _windows is None:
        return False
    try:
        _windows.desktop().send_keys(
            keys=str(keys),
            interval=max(0.0, float(interval)),
        )
        return True
    except Exception:
        return False


def robocorp_windows_search(text: str, wait_time: float = 3.0) -> bool:
    if _windows is None:
        return False
    try:
        _windows.desktop().windows_search(
            str(text),
            wait_time=max(0.0, float(wait_time)),
        )
        return True
    except Exception:
        return False


def robocorp_windows_run(text: str, wait_time: float = 1.0) -> bool:
    if _windows is None:
        return False
    try:
        _windows.desktop().windows_run(
            str(text),
            wait_time=max(0.0, float(wait_time)),
        )
        return True
    except Exception:
        return False


def robocorp_click(window_locator: str, control_locator: str,
                   timeout: float = 0.9) -> bool:
    """Click a child control using a Robocorp locator."""
    window = robocorp_find_window(window_locator, timeout=timeout)
    if window is None:
        return False
    try:
        window.click(
            control_locator,
            search_depth=12,
            timeout=_timeout(timeout),
            wait_time=0.3,
        )
        return True
    except Exception:
        return False


def robocorp_set_value(window_locator: str, control_locator: str,
                       value: str, timeout: float = 0.9) -> bool:
    """Set a text/value control through Robocorp UIAutomation."""
    window = robocorp_find_window(window_locator, timeout=timeout)
    if window is None:
        return False
    try:
        window.set_value(
            str(value),
            locator=control_locator,
            search_depth=12,
            timeout=_timeout(timeout),
            send_keys_fallback=True,
        )
        return True
    except Exception:
        return False


class RobocorpDesktop:
    """Compatibility facade for callers that prefer an object API."""
    available = staticmethod(robocorp_available)
    find_window = staticmethod(robocorp_find_window)
    focus_executable = staticmethod(robocorp_focus_executable)
    focus_handle = staticmethod(robocorp_focus_handle)
    send_keys = staticmethod(robocorp_send_keys)
    windows_search = staticmethod(robocorp_windows_search)
    windows_run = staticmethod(robocorp_windows_run)
    click = staticmethod(robocorp_click)
    set_value = staticmethod(robocorp_set_value)
