import webbrowser
from urllib.parse import quote


def weather_action(parameters=None, player=None):
    parameters = parameters or {}

    city = str(parameters.get("city", "")).strip()

    if not city:
        return "Please provide a city name."

    try:
        url = f"https://www.google.com/search?q={quote('weather ' + city)}"
        webbrowser.open(url)
        return f"Weather report opened for {city}."

    except Exception as e:
        return f"Could not open weather report: {e}"