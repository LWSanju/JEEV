import time

import pyautogui

from .state import STATE

from .window_manager import (
    get_foreground_window,
    focus_window,
    launch_start_app
)

from .observer import (
    observe,
    capture,
    find_element
)

from .navigator import (
    click_element,
    type_text,
    press,
    hotkey
)

from .verifier import (
    verify_window,
    verify_element,
    wait_for_element
)


def desktop_control(
    parameters=None,
    player=None
):

    p = parameters or {}

    action = str(
        p.get(
            "action",
            ""
        )
    ).strip().lower()

    app = str(
        p.get("app")
        or p.get("application")
        or ""
    ).strip()

    target = str(
        p.get("target")
        or p.get("description")
        or ""
    ).strip()

    name = str(
        p.get(
            "name",
            ""
        )
    ).strip()

    control_type = str(
        p.get(
            "control_type",
            ""
        )
    ).strip()

    text = str(
        p.get(
            "text",
            ""
        )
    )

    index = int(
        p.get(
            "index",
            0
        )
        or 0
    )

    try:

        # ==============================================
        # STATE
        # ==============================================

        if action in (
            "state",
            "status"
        ):

            state = (
                STATE.get()
            )

            return {

                "ok": True,

                "application":
                    state.application,

                "window_title":
                    state.window_title,

                "last_action":
                    state.last_action,

                "last_target":
                    state.last_target,

                "last_query":
                    state.last_query,

                "active_contact":
                    state.active_contact,

                "active_item":
                    state.active_item
            }

        # ==============================================
        # FOREGROUND WINDOW
        # ==============================================

        if action in (
            "foreground",
            "active_window"
        ):

            foreground = (
                get_foreground_window()
            )

            return {
                "ok":
                    bool(foreground),
                "foreground":
                    foreground
            }

        # ==============================================
        # OPEN APP
        # ==============================================

        if action in (
            "open_app",
            "launch"
        ):

            if not app:

                return {
                    "ok": False,
                    "error":
                        "Application name is required."
                }

            if focus_window(app):

                STATE.update(
                    application=app,
                    last_action="focus",
                    last_target=app
                )

                return {

                    "ok": True,
                    "verified": True,

                    "message":
                        f"{app} is already open."
                }

            launched = (
                launch_start_app(
                    app
                )
            )

            time.sleep(
                1.5
            )

            verified = (
                focus_window(app)
            )

            if verified:

                foreground = (
                    get_foreground_window()
                )

                STATE.update(
                    application=app,
                    window_title=(
                        foreground.get(
                            "title"
                        )
                        if foreground
                        else app
                    ),
                    last_action="open_app",
                    last_target=app
                )

            return {

                "ok":
                    verified,

                "launched":
                    launched,

                "verified":
                    verified,

                "foreground":
                    get_foreground_window()
            }

        # ==============================================
        # FOCUS
        # ==============================================

        if action in (
            "focus",
            "focus_app"
        ):

            ok = focus_window(
                app or target
            )

            return {

                "ok": ok,

                "verified": ok,

                "foreground":
                    get_foreground_window()
            }

        # ==============================================
        # OBSERVE
        # ==============================================

        if action in (
            "observe",
            "inspect",
            "screen"
        ):

            result = observe(

                include_screenshot=
                    bool(
                        p.get(
                            "include_screenshot",
                            True
                        )
                    ),

                max_elements=
                    int(
                        p.get(
                            "max_elements",
                            500
                        )
                    )
            )

            STATE.update(
                last_action="observe",
                last_target=(
                    app
                    or target
                )
            )

            return result

        # ==============================================
        # FIND UI ELEMENT
        # ==============================================

        if action in (
            "find",
            "find_element",
            "locate"
        ):

            matches = (
                find_element(
                    description=target,
                    name=name or target,
                    control_type=control_type
                )
            )

            return {

                "ok":
                    bool(matches),

                "count":
                    len(matches),

                "elements":
                    matches[:30]
            }

        # ==============================================
        # CLICK ELEMENT
        # ==============================================

        if action in (
            "click_element",
            "smart_click"
        ):

            return click_element(

                description=target,

                name=name,

                index=index
            )

        # ==============================================
        # TYPE
        # ==============================================

        if action in (
            "type_text",
            "smart_type"
        ):

            return type_text(
                text,
                clear=bool(
                    p.get(
                        "clear",
                        False
                    )
                )
            )

        # ==============================================
        # PRESS
        # ==============================================

        if action == "press":

            return press(
                p.get(
                    "key",
                    text
                )
            )

        # ==============================================
        # HOTKEY
        # ==============================================

        if action == "hotkey":

            return hotkey(
                p.get(
                    "keys",
                    text
                )
            )

        # ==============================================
        # SCROLL
        # ==============================================

        if action == "scroll":

            amount = int(
                p.get(
                    "amount",
                    4
                )
            )

            direction = str(
                p.get(
                    "direction",
                    "down"
                )
            ).lower()

            pyautogui.scroll(
                abs(amount)
                if direction == "up"
                else -abs(amount)
            )

            STATE.update(
                last_action="scroll",
                last_target=direction
            )

            return {
                "ok": True
            }

        # ==============================================
        # WAIT
        # ==============================================

        if action == "wait":

            time.sleep(
                float(
                    p.get(
                        "seconds",
                        1
                    )
                )
            )

            return {
                "ok": True
            }

        # ==============================================
        # SCREENSHOT
        # ==============================================

        if action == "screenshot":

            path = capture(
                p.get("path")
            )

            return {

                "ok": True,

                "path":
                    path
            }

        # ==============================================
        # VERIFY WINDOW
        # ==============================================

        if action == "verify_window":

            value = (
                target
                or app
            )

            ok = verify_window(
                value
            )

            return {

                "ok": ok,

                "verified": ok,

                "foreground":
                    get_foreground_window()
            }

        # ==============================================
        # VERIFY ELEMENT
        # ==============================================

        if action == "verify_element":

            value = (
                target
                or name
            )

            ok = verify_element(
                name=value,
                control_type=control_type
            )

            return {

                "ok": ok,

                "verified": ok
            }

        # ==============================================
        # WAIT FOR ELEMENT
        # ==============================================

        if action == "wait_for_element":

            value = (
                target
                or name
            )

            ok = wait_for_element(

                name=value,

                control_type=
                    control_type,

                timeout=
                    float(
                        p.get(
                            "timeout",
                            5
                        )
                    )
            )

            return {

                "ok": ok,

                "verified": ok
            }

        return {

            "ok": False,

            "error":
                f"Unknown desktop action: {action}"
        }

    except Exception as e:

        return {

            "ok": False,

            "error":
                f"Desktop control failed: {e}"
        }