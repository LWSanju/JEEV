import os
import shutil
import subprocess
from pathlib import Path


def desktop_control(parameters=None, player=None):
    parameters = parameters or {}

    action = str(parameters.get("action", "")).strip().lower()
    path = str(parameters.get("path", "")).strip()
    url = str(parameters.get("url", "")).strip()
    mode = str(parameters.get("mode", "by_type")).strip().lower()
    task = str(parameters.get("task", "")).strip()

    desktop = Path.home() / "Desktop"

    try:
        if action == "list":
            items = list(desktop.iterdir())

            if not items:
                return "The desktop is empty."

            return "\n".join(
                f"{'[DIR]' if item.is_dir() else '[FILE]'} {item.name}"
                for item in items
            )

        elif action == "stats":
            items = list(desktop.iterdir())
            files = [x for x in items if x.is_file()]
            folders = [x for x in items if x.is_dir()]

            return (
                f"Desktop contains {len(files)} files "
                f"and {len(folders)} folders."
            )

        elif action == "wallpaper":
            image_path = Path(path).expanduser()

            if not image_path.exists():
                return f"Image not found: {image_path}"

            import ctypes

            ctypes.windll.user32.SystemParametersInfoW(
                20,
                0,
                str(image_path),
                3
            )

            return f"Wallpaper changed to {image_path.name}."

        elif action == "wallpaper_url":
            if not url:
                return "No wallpaper URL was provided."

            webbrowser = __import__("webbrowser")
            webbrowser.open(url)

            return "Wallpaper URL opened in the browser."

        elif action == "clean":
            deleted = 0

            for item in desktop.iterdir():
                try:
                    if item.is_file() or item.is_symlink():
                        item.unlink()
                        deleted += 1
                except Exception:
                    pass

            return f"Removed {deleted} desktop files."

        elif action == "organize":
            files = [
                x for x in desktop.iterdir()
                if x.is_file()
            ]

            if mode == "by_type":
                folders = {
                    ".jpg": "Images",
                    ".jpeg": "Images",
                    ".png": "Images",
                    ".gif": "Images",
                    ".mp4": "Videos",
                    ".mkv": "Videos",
                    ".mp3": "Audio",
                    ".wav": "Audio",
                    ".pdf": "Documents",
                    ".docx": "Documents",
                    ".txt": "Documents",
                    ".zip": "Archives",
                    ".rar": "Archives",
                }

                moved = 0

                for file in files:
                    folder_name = folders.get(
                        file.suffix.lower(),
                        "Other"
                    )

                    destination = desktop / folder_name
                    destination.mkdir(exist_ok=True)

                    try:
                        shutil.move(
                            str(file),
                            str(destination / file.name)
                        )
                        moved += 1
                    except Exception:
                        pass

                return f"Organized {moved} desktop files."

            return "Desktop organization mode not supported."

        elif action == "task":
            return (
                "Desktop task received: "
                f"{task or 'No task description provided.'}"
            )

        return f"Unknown desktop action: {action}"

    except Exception as e:
        return f"Desktop control failed: {e}"