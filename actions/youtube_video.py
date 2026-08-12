import webbrowser
from urllib.parse import quote


def youtube_video(parameters=None, response=None, player=None):
    parameters = parameters or {}

    action = str(parameters.get("action", "play")).strip().lower()
    query = str(parameters.get("query", "")).strip()
    url = str(parameters.get("url", "")).strip()
    region = str(parameters.get("region", "US")).strip().upper()

    try:
        if action == "play":
            if not query:
                return "Please provide a YouTube search query."

            search_url = (
                "https://www.youtube.com/results?search_query="
                + quote(query)
            )
            webbrowser.open(search_url)
            return f"YouTube search opened for {query}."

        elif action == "get_info":
            if not url:
                return "Please provide a YouTube video URL."

            webbrowser.open(url)
            return "The YouTube video was opened."

        elif action == "trending":
            trending_url = (
                f"https://www.youtube.com/feed/trending?gl={region}"
            )
            webbrowser.open(trending_url)
            return f"YouTube trending opened for region {region}."

        elif action == "summarize":
            if not url:
                return "Please provide a YouTube video URL to summarize."

            webbrowser.open(url)
            return (
                "The YouTube video was opened. "
                "Automatic video summarization is not configured yet."
            )

        return f"Unknown YouTube action: {action}"

    except Exception as e:
        return f"YouTube control failed: {e}"