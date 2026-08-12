import webbrowser
from urllib.parse import quote


def browser_control(parameters=None, player=None):
    parameters = parameters or {}

    action = str(parameters.get("action", "")).strip().lower()
    url = str(parameters.get("url", "")).strip()
    query = str(parameters.get("query", "")).strip()
    text = str(parameters.get("text", "")).strip()
    key = str(parameters.get("key", "")).strip()

    try:
        if action == "go_to":
            if not url:
                return "No URL was provided."

            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            webbrowser.open(url)
            return f"Opened {url}."

        elif action == "search":
            if not query:
                return "No search query was provided."

            search_url = (
                "https://www.google.com/search?q="
                + quote(query)
            )
            webbrowser.open(search_url)
            return f"Searching for {query}."

        elif action == "close":
            return "Browser close requested."

        elif action == "scroll":
            return "Browser scroll requested."

        elif action == "press":
            return f"Browser key press requested: {key or text}."

        elif action in (
            "click",
            "type",
            "fill_form",
            "smart_click",
            "smart_type",
            "get_text",
        ):
            return (
                f"Browser action '{action}' received. "
                "Advanced browser automation is not configured yet."
            )

        return f"Unknown browser action: {action}"

    except Exception as e:
        return f"Browser control failed: {e}"