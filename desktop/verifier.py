import time

from .window_manager import (
    get_foreground_window
)

from .observer import (
    find_element
)


def verify_window(
    text
):

    foreground = (
        get_foreground_window()
    )

    if not foreground:
        return False

    return (
        str(text).lower()
        in
        str(
            foreground.get(
                "title",
                ""
            )
        ).lower()
    )


def verify_element(
    name="",
    control_type=""
):

    return bool(
        find_element(
            name=name,
            control_type=control_type
        )
    )


def wait_for_element(
    name="",
    control_type="",
    timeout=5
):

    deadline = (
        time.time()
        + float(timeout)
    )

    while (
        time.time()
        < deadline
    ):

        if verify_element(
            name=name,
            control_type=control_type
        ):
            return True

        time.sleep(
            0.25
        )

    return False