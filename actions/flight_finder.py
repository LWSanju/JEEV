import webbrowser
from urllib.parse import quote


def flight_finder(parameters=None, player=None):
    parameters = parameters or {}

    origin = parameters.get("origin", "").strip()
    destination = parameters.get("destination", "").strip()
    date = parameters.get("date", "").strip()
    return_date = parameters.get("return_date", "").strip()
    passengers = parameters.get("passengers", 1)
    cabin = parameters.get("cabin", "economy").strip().lower()

    if not origin or not destination or not date:
        return "I need the departure city, destination, and departure date."

    try:
        passengers = int(passengers)
    except (TypeError, ValueError):
        passengers = 1

    # Google Flights search URL
    url = (
        "https://www.google.com/travel/flights?"
        f"q={quote(origin)}%20to%20{quote(destination)}"
        f"%20on%20{quote(date)}"
    )

    if return_date:
        url += f"%20returning%20{quote(return_date)}"

    try:
        webbrowser.open(url)
    except Exception as e:
        return f"Could not open Google Flights: {e}"

    message = (
        f"Google Flights opened for {origin} to {destination} "
        f"on {date}, {passengers} passenger(s), {cabin}."
    )

    if return_date:
        message += f" Return date: {return_date}."

    return message