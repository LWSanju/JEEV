from pathlib import Path
import shutil
import os


def file_controller(parameters=None, player=None):
    parameters = parameters or {}

    action = str(parameters.get("action", "")).strip().lower()
    path = str(parameters.get("path", "")).strip()
    destination = str(parameters.get("destination", "")).strip()
    new_name = str(parameters.get("new_name", "")).strip()
    content = str(parameters.get("content", ""))
    name = str(parameters.get("name", "")).strip()
    extension = str(parameters.get("extension", "")).strip()
    count = parameters.get("count", 10)

    shortcuts = {
        "desktop": Path.home() / "Desktop",
        "downloads": Path.home() / "Downloads",
        "documents": Path.home() / "Documents",
        "home": Path.home(),
    }

    try:
        target = shortcuts.get(
            path.lower(),
            Path(path).expanduser() if path else Path.home()
        )

        if action == "list":
            if not target.exists():
                return f"Path not found: {target}"

            items = list(target.iterdir())

            if not items:
                return "The folder is empty."

            return "\n".join(
                f"{'[DIR]' if item.is_dir() else '[FILE]'} {item.name}"
                for item in items
            )

        elif action == "info":
            if not target.exists():
                return f"Path not found: {target}"

            stat = target.stat()

            return (
                f"Name: {target.name}\n"
                f"Path: {target}\n"
                f"Type: {'Folder' if target.is_dir() else 'File'}\n"
                f"Size: {stat.st_size} bytes"
            )

        elif action == "create_file":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Created file: {target}"

        elif action == "create_folder":
            target.mkdir(parents=True, exist_ok=True)
            return f"Created folder: {target}"

        elif action == "read":
            if not target.is_file():
                return "The specified path is not a file."

            return target.read_text(
                encoding="utf-8",
                errors="replace"
            )[:20000]

        elif action == "write":
            if not target.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)

            target.write_text(content, encoding="utf-8")
            return f"Written to {target}."

        elif action == "delete":
            if not target.exists():
                return f"Path not found: {target}"

            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

            return f"Deleted: {target}"

        elif action == "move":
            if not target.exists():
                return f"Source not found: {target}"

            shutil.move(str(target), destination)
            return f"Moved {target} to {destination}."

        elif action == "copy":
            if not target.exists():
                return f"Source not found: {target}"

            if target.is_dir():
                shutil.copytree(
                    str(target),
                    str(Path(destination) / target.name),
                    dirs_exist_ok=True
                )
            else:
                shutil.copy2(str(target), destination)

            return f"Copied {target} to {destination}."

        elif action == "rename":
            if not target.exists():
                return f"Path not found: {target}"

            new_path = target.parent / new_name
            target.rename(new_path)

            return f"Renamed to {new_path.name}."

        elif action == "find":
            search_root = target if target.is_dir() else target.parent

            matches = []

            for item in search_root.rglob("*"):
                if not item.is_file():
                    continue

                if name and name.lower() not in item.name.lower():
                    continue

                if extension and item.suffix.lower() != extension.lower():
                    continue

                matches.append(str(item))

                if len(matches) >= 50:
                    break

            if not matches:
                return "No matching files found."

            return "\n".join(matches)

        elif action == "largest":
            if not target.is_dir():
                return "Largest-file search requires a folder."

            try:
                count = int(count)
            except (TypeError, ValueError):
                count = 10

            files = [
                item for item in target.rglob("*")
                if item.is_file()
            ]

            files.sort(
                key=lambda x: x.stat().st_size,
                reverse=True
            )

            results = []

            for item in files[:count]:
                size = item.stat().st_size
                results.append(
                    f"{size:,} bytes - {item}"
                )

            return "\n".join(results) if results else "No files found."

        elif action == "disk_usage":
            usage = shutil.disk_usage(target.anchor)

            return (
                f"Total: {usage.total / (1024**3):.2f} GB\n"
                f"Used: {usage.used / (1024**3):.2f} GB\n"
                f"Free: {usage.free / (1024**3):.2f} GB"
            )

        elif action == "organize_desktop":
            desktop = Path.home() / "Desktop"
            return "Desktop organization requested."

        return f"Unknown file controller action: {action}"

    except Exception as e:
        return f"File controller failed: {e}"