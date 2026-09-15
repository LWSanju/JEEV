from __future__ import annotations

import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from core.coding.coding_agent import JEEVCodingAgent, CodingError


_ACTIVE: dict[str, JEEVCodingAgent] = {}
_LOCK = threading.RLock()


def _default_root(parameters: dict[str, Any]) -> Path:
    """Resolve the coding workspace.

    Coding is deliberately filesystem-first.  This function never opens an
    editor, sends keyboard input, clicks the desktop, or delegates work to
    computer-control automation.
    """
    requested = str(
        parameters.get("project_path")
        or parameters.get("root")
        or parameters.get("workspace")
        or ""
    ).strip()

    if requested:
        root = Path(requested).expanduser().resolve()
    else:
        env_root = os.getenv("JEEV_CODING_ROOT", "").strip()
        root = (
            Path(env_root).expanduser().resolve()
            if env_root
            else Path.cwd().resolve()
        )

    root.mkdir(parents=True, exist_ok=True)
    return root


def _status_writer(player=None, speak=None) -> Callable[[str], None]:
    def emit(message: str) -> None:
        text = str(message or "").strip()
        if not text:
            return
        print(f"[JEEV-CODE] {text}")
        if player is not None:
            try:
                player.write_log(f"CODE: {text}")
            except Exception:
                pass
    return emit


def _open_notepad(path: Path) -> dict[str, Any]:
    """Open one coding file in Windows Notepad.

    This is intentionally limited to Notepad and a caller-supplied coding
    file.  It does not provide arbitrary keyboard/mouse automation.
    """
    try:
        target = path.expanduser().resolve()
        if not target.exists() or not target.is_file():
            return {
                "ok": False,
                "error": f"Cannot open missing file in Notepad: {target}",
            }

        subprocess.Popen(
            ["notepad.exe", str(target)],
            close_fds=True,
        )
        return {
            "ok": True,
            "path": str(target),
            "editor": "notepad",
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "error": "Windows Notepad was not found on this system.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Could not open Notepad: {exc}",
        }


def _requested_notepad_file(args: dict[str, Any], root: Path) -> Path | None:
    """Resolve an explicit file for the coding-only Notepad view."""
    raw = (
        args.get("notepad_path")
        or args.get("file_path")
        or args.get("file")
        or args.get("path")
        or args.get("target_file")
    )
    if raw:
        candidate = Path(str(raw)).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        return candidate

    # If the user explicitly names a source file in the natural-language
    # request, use it when that exact file exists in the workspace.
    request = str(
        args.get("request")
        or args.get("goal")
        or args.get("instruction")
        or args.get("task")
        or ""
    )
    for match in re.findall(
        r'(?<![\w.-])([A-Za-z0-9_.-]+\.(?:py|js|ts|tsx|jsx|java|c|cpp|h|hpp|cs|go|rs|html|css|json|yaml|yml|md|txt))(?![\w.-])',
        request,
        flags=re.IGNORECASE,
    ):
        candidate = root / match
        if candidate.is_file():
            return candidate

    return None


def dev_agent(parameters=None, player=None, speak=None):
    """JEEV's natural-language coding agent.

    This is the integration point for the OpenCode-inspired coding workflow:
    project inspection, read/search, edits, command execution, verification,
    long-running continuation and persisted task state.

    Coding remains filesystem-first for correctness, with an optional,
    coding-only Windows Notepad surface.  Notepad never becomes a general
    desktop-control gateway.
    """
    args = dict(parameters or {})

    # Coding may use Notepad, but only through this coding tool.  We do not
    # delegate arbitrary desktop control to the coding model, so Gmail,
    # Spotify, browser control, and the rest of JEEV remain untouched.
    requested_mode = str(
        args.get("mode") or args.get("execution_mode") or ""
    ).strip().lower()

    action = str(args.get("action", "build")).strip().lower()
    request = str(
        args.get("request")
        or args.get("goal")
        or args.get("instruction")
        or args.get("task")
        or ""
    ).strip()

    notepad_requested = requested_mode in {
        "notepad", "notepad_editor", "editor",
    } or any(
        token in request.lower()
        for token in ("write in notepad", "edit in notepad", "use notepad")
    )

    root = _default_root(args)

    # These arguments are deliberately ignored rather than forwarded to any
    # desktop automation layer.  Notepad is handled by the narrow helper below.
    args.pop("computer_control", None)
    args.pop("desktop_control", None)
    args.pop("keyboard", None)
    args.pop("keypress", None)
    args.pop("mouse", None)
    args.pop("click", None)
    args.pop("type_text", None)
    args.pop("open_editor", None)

    if action in {"open_notepad", "notepad_open"}:
        target = _requested_notepad_file(args, root)
        if target is None:
            return {
                "ok": False,
                "error": (
                    "Specify a coding file with file_path/notepad_path "
                    "to open in Notepad."
                ),
            }
        return _open_notepad(target)

    if action in {"inspect", "status"}:
        return JEEVCodingAgent(root).inspect()

    if action in {"stop", "cancel"}:
        task_id = str(args.get("task_id", "")).strip()
        with _LOCK:
            agent = _ACTIVE.get(task_id)
        if agent:
            agent.stop()
            return {"ok": True, "task_id": task_id, "status": "stopping"}
        return {"ok": False, "error": f"No active coding task named {task_id}."}

    if not request:
        return {
            "ok": False,
            "error": "Tell me what you want JEEV to build, change, fix, refactor, test, or debug.",
        }

    mode = "plan" if action in {"plan", "analyze", "analyse"} else "build"
    model = str(args.get("model", "")).strip() or None
    agent = JEEVCodingAgent(root=root, model=model, status_callback=_status_writer(player, speak))

    # A coding task is synchronous from the tool's perspective so the model gets
    # a truthful final result. JEEV's existing executor already runs tools in a
    # worker thread, so the audio event loop is not blocked.
    with _LOCK:
        # Only one task per root to prevent competing writers.
        key = str(root).lower()
        if key in _ACTIVE:
            return {
                "ok": False,
                "error": "A coding task is already running for this workspace.",
                "task_id": _ACTIVE[key].state.task_id if _ACTIVE[key].state else None,
            }
        _ACTIVE[key] = agent
    try:
        result = agent.run_task(request=request, mode=mode)

        if notepad_requested and isinstance(result, dict) and result.get("ok"):
            target = _requested_notepad_file(args, root)

            # If no exact file was supplied, choose the newest source file
            # modified during this coding task.  This keeps Notepad scoped to
            # the workspace instead of opening arbitrary desktop targets.
            if target is None:
                candidates = []
                for suffix in (
                    ".py", ".js", ".ts", ".tsx", ".jsx", ".java",
                    ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs",
                    ".html", ".css", ".json", ".yaml", ".yml", ".md", ".txt",
                ):
                    candidates.extend(root.rglob(f"*{suffix}"))
                if candidates:
                    target = max(
                        (p for p in candidates if p.is_file()),
                        key=lambda p: p.stat().st_mtime,
                        default=None,
                    )

            if target is not None:
                notepad_result = _open_notepad(target)
                result = dict(result)
                result["notepad"] = notepad_result

        return result
    except CodingError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": f"Coding agent error: {exc}"}
    finally:
        with _LOCK:
            _ACTIVE.pop(str(root).lower(), None)


def run_coding_task(request: str, project_path: str | None = None, model: str | None = None, **kwargs):
    """Compatibility API used by JEEV tests and direct callers."""
    params = {"request": str(request or "")}
    if project_path:
        params["project_path"] = project_path
    if model:
        params["model"] = model
    params.update(kwargs)
    return dev_agent(params)


__all__ = ["dev_agent", "run_coding_task"]
