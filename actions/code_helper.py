from pathlib import Path
import subprocess


def code_helper(parameters=None, player=None, speak=None):
    parameters = parameters or {}

    action = str(parameters.get("action", "auto")).strip().lower()
    description = str(parameters.get("description", "")).strip()
    language = str(parameters.get("language", "python")).strip().lower()
    output_path = str(parameters.get("output_path", "")).strip()
    file_path = str(parameters.get("file_path", "")).strip()
    code = str(parameters.get("code", ""))
    args = str(parameters.get("args", ""))
    timeout = parameters.get("timeout", 30)

    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = 30

    if action == "write":
        if not output_path:
            return "No output path was provided."

        if not code:
            return "No code was provided."

        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")

        return f"Code written to {path}."

    if action == "read":
        if not file_path:
            return "No file path was provided."

        path = Path(file_path).expanduser()

        if not path.exists():
            return f"File not found: {path}"

        return path.read_text(
            encoding="utf-8",
            errors="replace"
        )[:20000]

    if action in ("explain", "review"):
        if not file_path:
            return "Please provide a file to explain or review."

        path = Path(file_path).expanduser()

        if not path.exists():
            return f"File not found: {path}"

        source = path.read_text(
            encoding="utf-8",
            errors="replace"
        )

        return (
            f"Loaded {path.name} for {action}. "
            f"The file contains {len(source.splitlines())} lines. "
            "AI code analysis is not connected yet."
        )

    if action == "run":
        if not file_path:
            return "No file path was provided."

        path = Path(file_path).expanduser()

        if not path.exists():
            return f"File not found: {path}"

        if language in ("python", "py"):
            command = ["python", str(path)]
        else:
            return f"Running {language} files is not configured yet."

        if args:
            command.extend(args.split())

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode != 0:
            return (
                f"Program exited with code {result.returncode}.\n"
                f"{error or output}"
            )

        return output or "Program completed successfully."

    if action == "build":
        return (
            f"Build requested for {file_path or 'the project'}. "
            "Automatic project building is not configured yet."
        )

    if action in ("edit", "fix", "optimize", "document", "test"):
        return (
            f"Code action '{action}' received for "
            f"{file_path or 'the supplied code'}. "
            "Advanced AI code editing is not configured yet."
        )

    if action == "auto":
        return (
            f"Code-helper request received: "
            f"{description or 'No description provided.'}"
        )

    return f"Unknown code-helper action: {action}"