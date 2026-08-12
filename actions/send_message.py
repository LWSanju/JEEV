# ============================================================
# JEEV — GENERIC SEND MESSAGE
# ============================================================
#
# WhatsApp is delegated to whatsapp_control.py.
# Telegram remains handled here.
#
# ============================================================

import urllib.parse
import webbrowser


def send_message(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
):
    """
    Generic messaging dispatcher.

    WhatsApp -> actions.whatsapp_control
    Telegram -> Telegram share URL
    """

    parameters = parameters or {}

    receiver = str(
        parameters.get("receiver", "")
    ).strip()

    message_text = str(
        parameters.get("message_text", "")
    ).strip()

    platform = str(
        parameters.get("platform", "")
    ).strip().lower()

    if not receiver:
        return "No recipient was provided."

    if not message_text:
        return "No message text was provided."

    # ========================================================
    # WHATSAPP
    # ========================================================

    if platform in (
        "whatsapp",
        "whatsapp desktop",
        "whatsapp web",
    ):

        print(
            "[JEEV][SendMessage] "
            "Delegating WhatsApp to whatsapp_control."
        )

        try:

            from actions.whatsapp_control import (
                whatsapp_control
            )

            return whatsapp_control(
                parameters={
                    "action": "send_message",
                    "receiver": receiver,
                    "message_text": message_text,
                },
                response=response,
                player=player,
            )

        except Exception as e:

            print(
                "[JEEV][SendMessage] "
                f"WhatsApp controller error: {e}"
            )

            return (
                "WhatsApp control failed: "
                f"{e}"
            )

    # ========================================================
    # TELEGRAM
    # ========================================================

    if platform == "telegram":

        try:

            encoded_message = urllib.parse.quote(
                message_text
            )

            url = (
                "https://t.me/share/url"
                f"?text={encoded_message}"
            )

            print(
                "[JEEV][SendMessage] "
                "Opening Telegram sharing..."
            )

            webbrowser.open(url)

            return (
                f"Telegram sharing opened for "
                f"{receiver}."
            )

        except Exception as e:

            print(
                "[JEEV][SendMessage] "
                f"Telegram error: {e}"
            )

            return (
                "Could not prepare the Telegram "
                f"message: {e}"
            )

    # ========================================================
    # PLATFORM NOT SPECIFIED
    # ========================================================

    if not platform:

        return (
            "No messaging platform was specified. "
            "For WhatsApp, use WhatsApp Desktop."
        )

    # ========================================================
    # UNKNOWN PLATFORM
    # ========================================================

    return (
        f"Platform '{platform}' is not supported yet."
    )


# ============================================================
# COMPATIBILITY ALIAS
# ============================================================

def sendMessage(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
):

    return send_message(
        parameters=parameters,
        response=response,
        player=player,
        session_memory=session_memory,
    )