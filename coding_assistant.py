"""Very small coding bridge for JEEV.

JEEV does not run a local coding agent for normal coding requests.
It opens the user's ChatGPT session in the browser and places the request
there, keeping JEEV lightweight.
"""

from __future__ import annotations

import urllib.parse
import webbrowser


CHATGPT_URL = "https://chatgpt.com/"


def open_coding_assistant(request: str) -> str:
    request = str(request or "").strip()

    if not request:
        return "No coding request was supplied."

    prompt = (
        "I am sending this coding task from JEEV. "
        "Please handle the coding work directly in ChatGPT:\n\n"
        f"{request}"
    )

    # Keep the URL bounded even if a very large voice transcription arrives.
    prompt = prompt[:12000]
    url = CHATGPT_URL + "?" + urllib.parse.urlencode({"q": prompt})

    opened = webbrowser.open_new_tab(url)

    if opened:
        return "ChatGPT is open with your coding request."
    return "I prepared the coding request, but the browser could not be opened."


if __name__ == "__main__":
    print(open_coding_assistant("Create a Python hello-world program."))
