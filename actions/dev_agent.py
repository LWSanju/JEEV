from pathlib import Path
import subprocess


def dev_agent(parameters=None, player=None, speak=None):
    parameters = parameters or {}

    description = str(
        parameters.get("description", "")
    ).strip()

    language = str(
        parameters.get("language", "python")
    ).strip().lower()

    project_name = str(
        parameters.get("project_name", "")
    ).strip()

    timeout = parameters.get("timeout", 30)

    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = 30

    if not description:
        return "No project description was provided."

    # Create projects inside the user's Documents folder.
    projects_root = Path.home() / "Documents" / "JARVIS_Projects"

    if project_name:
        safe_name = "".join(
            c for c in project_name
            if c.isalnum() or c in (" ", "_", "-")
        ).strip()

        project_name = safe_name or "JarvisProject"
    else:
        project_name = "JarvisProject"

    project_dir = projects_root / project_name

    try:
        project_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        readme = project_dir / "README.md"

        readme.write_text(
            f"# {project_name}\n\n"
            f"## Description\n\n"
            f"{description}\n\n"
            f"## Language\n\n"
            f"{language}\n",
            encoding="utf-8"
        )

        return (
            f"Project workspace created at:\n"
            f"{project_dir}\n\n"
            f"Description: {description}\n"
            f"Language: {language}\n"
            "Advanced AI project generation is not configured yet."
        )

    except Exception as e:
        return f"Dev agent failed: {e}"