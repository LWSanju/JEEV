import webbrowser
from urllib.parse import quote


def web_search(parameters=None, player=None):
    parameters = parameters or {}

    query = str(parameters.get("query", "")).strip()
    mode = str(parameters.get("mode", "search")).strip().lower()
    items = parameters.get("items", [])
    aspect = str(parameters.get("aspect", "")).strip()

    if not query and not items:
        return "No search query was provided."

    try:
        if mode == "compare" and items:
            comparison = " vs ".join(
                str(item) for item in items
            )

            if aspect:
                comparison += f" {aspect}"

            search_query = comparison
        else:
            search_query = query

        url = (
            "https://www.google.com/search?q="
            + quote(search_query)
        )

        webbrowser.open(url)

        return f"Web search opened for: {search_query}"

    except Exception as e:
        return f"Web search failed: {e}"