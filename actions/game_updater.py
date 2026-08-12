import subprocess
import webbrowser


def game_updater(parameters=None, player=None, speak=None):
    parameters = parameters or {}

    action = str(
        parameters.get("action", "update")
    ).strip().lower()

    platform = str(
        parameters.get("platform", "both")
    ).strip().lower()

    game_name = str(
        parameters.get("game_name", "")
    ).strip()

    shutdown_when_done = bool(
        parameters.get("shutdown_when_done", False)
    )

    try:
        if action == "list":
            return (
                "Game listing requested. "
                "Steam/Epic game database integration "
                "is not configured yet."
            )

        elif action == "download_status":
            return (
                f"Download status requested"
                f"{f' for {game_name}' if game_name else ''}. "
                "Game download monitoring is not configured yet."
            )

        elif action == "update":
            if platform == "steam":
                webbrowser.open(
                    "steam://open/downloads"
                )
                return "Steam downloads opened."

            elif platform == "epic":
                webbrowser.open(
                    "com.epicgames.launcher://"
                )
                return "Epic Games Launcher opened."

            else:
                webbrowser.open(
                    "steam://open/downloads"
                )

                return (
                    "Steam downloads opened. "
                    "Epic Games integration is not configured yet."
                )

        elif action == "install":
            if platform == "steam":
                webbrowser.open(
                    "steam://open/games"
                )
                return (
                    f"Steam opened for installing "
                    f"{game_name or 'the requested game'}."
                )

            elif platform == "epic":
                webbrowser.open(
                    "com.epicgames.launcher://"
                )
                return (
                    f"Epic Games Launcher opened for "
                    f"{game_name or 'the requested game'}."
                )

            return "Please specify Steam or Epic."

        elif action == "schedule":
            return (
                "Game update scheduling is not configured yet."
            )

        elif action == "cancel_schedule":
            return (
                "Game update schedule cancellation "
                "is not configured yet."
            )

        elif action == "schedule_status":
            return (
                "Game update schedule status "
                "is not configured yet."
            )

        return f"Unknown game updater action: {action}"

    except Exception as e:
        return f"Game updater failed: {e}"