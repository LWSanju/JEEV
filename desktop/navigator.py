import time

import pyautogui

from .observer import (
    find_element
)

from .state import STATE


def click_element(
    description="",
    name="",
    index=0
):

    matches = find_element(
        description=description,
        name=name
    )

    if not matches:

        return {
            "ok": False,
            "error":
                f"Could not locate '{description or name}'."
        }

    if index >= len(matches):

        return {
            "ok": False,
            "error":
                f"Only {len(matches)} matching elements found."
        }

    element = matches[index]

    x = (
        int(element["x"])
        + max(
            1,
            int(element["width"]) // 2
        )
    )

    y = (
        int(element["y"])
        + max(
            1,
            int(element["height"]) // 2
        )
    )

    pyautogui.click(
        x,
        y
    )

    time.sleep(
        0.3
    )

    STATE.update(
        last_action="click_element",
        last_target=(
            description
            or name
        )
    )

    return {

        "ok": True,

        "method":
            "windows_ui_automation",

        "element":
            element,

        "coordinates":
            [x, y]
    }


def type_text(
    text,
    clear=False
):

    if clear:

        pyautogui.hotkey(
            "ctrl",
            "a"
        )

        pyautogui.press(
            "backspace"
        )

    pyautogui.write(
        str(text),
        interval=0.02
    )

    STATE.update(
        last_action="type",
        last_target=text
    )

    return {
        "ok": True
    }


def press(key):

    pyautogui.press(
        str(key)
    )

    STATE.update(
        last_action="press",
        last_target=key
    )

    return {
        "ok": True
    }


def hotkey(keys):

    parts = [
        x.strip().lower()
        for x in
        str(keys).split("+")
        if x.strip()
    ]

    if not parts:

        return {
            "ok": False,
            "error":
                "No keys supplied."
        }

    pyautogui.hotkey(
        *parts
    )

    STATE.update(
        last_action="hotkey",
        last_target=keys
    )

    return {
        "ok": True
    }