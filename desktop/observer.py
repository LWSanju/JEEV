from pathlib import Path

import pyautogui

from .window_manager import (
    get_foreground_window
)

from .uia import (
    get_elements,
    find
)


SCREEN_DIR = (
    Path.home()
    / "Pictures"
    / "JARVIS"
)

SCREEN_DIR.mkdir(
    parents=True,
    exist_ok=True
)


def capture(path=None):

    if not path:

        path = (
            SCREEN_DIR
            / "desktop_observation.png"
        )

    image = pyautogui.screenshot()

    image.save(
        path
    )

    return str(path)


def observe(
    include_screenshot=True,
    max_elements=500
):

    foreground = (
        get_foreground_window()
    )

    result = {

        "foreground":
            foreground,

        "ui_elements":
            get_elements(
                max_items=max_elements
            )
    }

    if include_screenshot:

        result["screenshot"] = (
            capture()
        )

    return result


def find_element(
    description="",
    name="",
    control_type=""
):

    query = (
        name
        or description
        or ""
    )

    matches = find(
        name=query,
        control_type=control_type
    )

    return matches