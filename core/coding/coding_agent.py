from __future__ import annotations

import ast
import difflib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from or_client import get_client
except Exception:
    get_client = None


MAX_READ_CHARS = 30000
MAX_TOOL_OUTPUT = 12000
MAX_FILES_IN_CONTEXT = 80
MAX_AGENT_STEPS = 80
MAX_INVALID_TOOL_RETRIES = 3
DEFAULT_MAX_TOKENS = 12000

IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".nuxt", ".turbo", ".idea", ".vscode",
}


class CodingError(RuntimeError):
    pass


@dataclass
class Change:
    path: str
    action: str
    before_hash: str = ""
    after_hash: str = ""


@dataclass
class AgentState:
    task_id: str
    root: str
    request: str
    mode: str
    started_at: float
    step: int = 0
    status: str = "running"
    summary: str = ""
    plan: list[str] | None = None
    changes: list[dict[str, Any]] | None = None
    tests: list[dict[str, Any]] | None = None
    continuation_count: int = 0
    last_error: str = ""

    def __post_init__(self):
        if self.plan is None:
            self.plan = []
        if self.changes is None:
            self.changes = []
        if self.tests is None:
            self.tests = []


class CodingWorkspace:
    """OpenCode-inspired bounded workspace tool layer for JEEV."""

    def __init__(self, root: str | Path, allow_outside_root: bool = False):
        self.root = Path(root).expanduser().resolve()
        self.allow_outside_root = allow_outside_root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, value: str | Path) -> Path:
        raw = Path(str(value or "."))
        path = raw if raw.is_absolute() else self.root / raw
        path = path.resolve()
        if not self.allow_outside_root:
            try:
                path.relative_to(self.root)
            except ValueError:
                raise CodingError(f"Path is outside coding workspace: {path}")
        return path

    @staticmethod
    def _hash(path: Path) -> str:
        if not path.exists() or not path.is_file():
            return ""
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    def tree(self, max_files: int = MAX_FILES_IN_CONTEXT) -> list[str]:
        results: list[str] = []
        for base, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
            rel_base = Path(base).relative_to(self.root)
            for name in files:
                if name.startswith(".") and name not in {".env.example"}:
                    continue
                rel = (rel_base / name).as_posix()
                results.append(rel)
                if len(results) >= max_files:
                    return sorted(results)
        return sorted(results)

    def read(self, path: str, start: int = 1, end: int | None = None) -> str:
        p = self._path(path)
        if not p.exists():
            raise CodingError(f"File does not exist: {path}")
        if not p.is_file():
            raise CodingError(f"Not a file: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(True)
        start_i = max(0, start - 1)
        selected = lines[start_i:end]
        out = "".join(selected)
        if len(out) > MAX_READ_CHARS:
            out = out[:MAX_READ_CHARS] + "\n...[truncated]..."
        return out

    def write(self, path: str, content: str) -> Change:
        p = self._path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        before = self._hash(p)
        p.write_text(content, encoding="utf-8", newline="")
        after = self._hash(p)
        return Change(str(p.relative_to(self.root)), "write", before, after)

    def edit(self, path: str, old: str, new: str, replace_all: bool = False) -> Change:
        p = self._path(path)
        if not p.exists():
            raise CodingError(f"File does not exist: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        count = text.count(old)
        if count == 0:
            raise CodingError(f"Edit target was not found in {path}")
        if count > 1 and not replace_all:
            raise CodingError(f"Edit target occurs {count} times in {path}; use replace_all=true or provide more context")
        before = self._hash(p)
        text = text.replace(old, new, -1 if replace_all else 1)
        p.write_text(text, encoding="utf-8", newline="")
        return Change(str(p.relative_to(self.root)), "edit", before, self._hash(p))

    def glob(self, pattern: str) -> list[str]:
        out: list[str] = []
        for p in self.root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in IGNORED_DIRS for part in p.relative_to(self.root).parts):
                continue
            rel = p.relative_to(self.root).as_posix()
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(p.name, pattern):
                out.append(rel)
        return sorted(out)[:500]

    def grep(self, pattern: str, glob: str = "**/*", max_matches: int = 100) -> list[dict[str, Any]]:
        rx = re.compile(pattern, re.IGNORECASE)
        matches: list[dict[str, Any]] = []
        candidates = self.tree(max_files=10000) if glob in {"**/*", "*", "**"} else self.glob(glob)
        for rel in candidates:
            if len(matches) >= max_matches:
                break
            p = self.root / rel
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    matches.append({"path": rel, "line": lineno, "text": line[:500]})
                    if len(matches) >= max_matches:
                        break
        return matches

    def run(self, command: str, timeout: int = 120) -> dict[str, Any]:
        # Deliberately shell=True on Windows because coding tasks often need
        # commands such as "python -m pytest" or "npm run build". The agent
        # must still stay inside the selected workspace via cwd.
        started = time.time()
        proc = subprocess.run(
            command,
            cwd=str(self.root),
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1, min(int(timeout), 600)),
        )
        output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
        if len(output) > MAX_TOOL_OUTPUT:
            output = output[-MAX_TOOL_OUTPUT:]
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "output": output,
            "duration": round(time.time() - started, 2),
        }

    def snapshot(self) -> dict[str, str]:
        snap: dict[str, str] = {}
        for rel in self.tree(max_files=10000):
            p = self.root / rel
            if p.is_file():
                snap[rel] = self._hash(p)
        return snap


class JEEVCodingAgent:
    """Long-running natural-language coding loop inspired by OpenCode primitives."""

    def __init__(
        self,
        root: str | Path,
        model: str | None = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ):
        self.workspace = CodingWorkspace(root)
        self.model = model
        self.status_callback = status_callback
        self.state: AgentState | None = None
        self._stop = threading.Event()
        self._session: list[dict[str, str]] = []

    def _status(self, message: str) -> None:
        if self.status_callback:
            try:
                self.status_callback(message)
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()

    def _state_path(self) -> Path:
        return self.workspace.root / ".jeev" / "coding" / f"{self.state.task_id}.json"

    def _save_state(self) -> None:
        if not self.state:
            return
        p = self._state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self.state), indent=2, ensure_ascii=False), encoding="utf-8")

    def _model(self):
        if get_client is None:
            raise CodingError("OpenRouter client is unavailable.")
        client = get_client()
        if client is None:
            raise CodingError("OpenRouter client could not be initialized.")
        return client

    def _context(self) -> str:
        files = self.workspace.tree()
        tree = "\n".join(files)
        if len(tree) > 16000:
            tree = tree[:16000] + "\n..."
        return tree

    def _system_prompt(self) -> str:
        return """You are JEEV Coding Agent, an autonomous software engineering agent.

The user speaks simple English, but you must operate on the real project workspace.
Work like a professional coding agent: inspect before changing, make small verifiable
changes, run tests when useful, diagnose failures, and continue until the requested
work is actually complete.

You have tools: tree, read, glob, grep, write, edit, run, finish.
Return EXACTLY one JSON object per response with this shape:
{"action":"tool","tool":"read|glob|grep|write|edit|run|finish","args":{...}}
For finish use {"action":"finish","summary":"..."}.
Never put markdown fences around the JSON.
Do not invent file contents. Read relevant files before editing them.
Prefer edit for localized changes and write for new files or complete replacements.
After a failed command, inspect the failure and fix it rather than merely reporting it.
Do not modify secrets, credentials, .env files, or files outside the workspace.
Do not delete the project or perform destructive cleanup unless explicitly required.
Large tasks are allowed: continue across many tool calls. Never stop merely because
one model response is short; preserve state and continue.
"""

    def _call_model(self, user_prompt: str) -> str:
        messages = list(self._session)
        messages.append({"role": "user", "content": user_prompt})
        reply = self._model().multi_turn(
            messages,
            model=self.model,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=0.15,
        )
        if not reply:
            raise CodingError("The coding model returned no usable response.")
        self._session.append({"role": "user", "content": user_prompt})
        self._session.append({"role": "assistant", "content": reply})
        return reply

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = str(text or "").strip()
        if not text:
            raise CodingError("Coding model returned an empty response.")
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        candidates = [text]
        start = text.find("{")
        if start >= 0 and start != 0:
            candidates.append(text[start:])
        for candidate in candidates:
            try:
                value = json.loads(candidate)
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
        if start >= 0:
            decoder = json.JSONDecoder()
            try:
                value, _ = decoder.raw_decode(text[start:])
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
        raise CodingError("Coding model returned invalid tool JSON.")

    @staticmethod
    def _normalize_action(action: dict[str, Any]) -> dict[str, Any]:
        """Normalize common free-model variations into our strict tool protocol."""
        out = dict(action or {})
        raw_action = str(out.get("action", "")).strip().lower()
        raw_tool = str(out.get("tool", "")).strip().lower()
        args = out.get("args")
        if not isinstance(args, dict):
            args = {}

        aliases = {
            "list": "tree", "list_files": "tree", "filesystem": "tree",
            "read_file": "read", "cat": "read", "view": "read",
            "search": "grep", "search_files": "grep", "find": "grep",
            "find_files": "glob", "list_matching_files": "glob",
            "create_file": "write", "write_file": "write", "create": "write",
            "modify": "edit", "edit_file": "edit", "patch": "edit",
            "execute": "run", "shell": "run", "command": "run",
            "done": "finish", "complete": "finish",
        }
        tool = aliases.get(raw_tool, raw_tool)

        # Some free models omit the tool name but provide recognizable arguments.
        if not tool:
            if any(k in args for k in ("old", "new", "replace_all")):
                tool = "edit"
            elif "content" in args and "path" in args:
                tool = "write"
            elif "command" in args:
                tool = "run"
            elif "pattern" in args and "glob" not in args:
                tool = "glob"
            elif "pattern" in args or "max_matches" in args:
                tool = "grep"
            elif "path" in args:
                tool = "read"

        if raw_action in {"finish", "done", "complete"} or tool == "finish":
            return {"action": "finish", "summary": str(out.get("summary") or out.get("message") or "Coding task completed.")}
        return {"action": "tool", "tool": tool, "args": args}

    def _tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "tree":
            return {"ok": True, "files": self.workspace.tree(max_files=int(args.get("max_files", 300)))}
        if name == "read":
            return {"ok": True, "path": args.get("path"), "content": self.workspace.read(str(args.get("path")), int(args.get("start", 1)), args.get("end"))}
        if name == "glob":
            return {"ok": True, "matches": self.workspace.glob(str(args.get("pattern", "**/*")))}
        if name == "grep":
            return {"ok": True, "matches": self.workspace.grep(str(args.get("pattern", "")), str(args.get("glob", "**/*")), int(args.get("max_matches", 100)))}
        if name == "write":
            c = self.workspace.write(str(args["path"]), str(args.get("content", "")))
            return {"ok": True, "change": asdict(c)}
        if name == "edit":
            c = self.workspace.edit(str(args["path"]), str(args["old"]), str(args.get("new", "")), bool(args.get("replace_all", False)))
            return {"ok": True, "change": asdict(c)}
        if name == "run":
            return self.workspace.run(str(args["command"]), int(args.get("timeout", 120)))
        raise CodingError(f"Unknown coding tool: {name}")

    def _bootstrap(self) -> None:
        request = self.state.request
        self._session = [{"role": "system", "content": self._system_prompt()}]
        prompt = (
            f"PROJECT ROOT: {self.workspace.root}\n\n"
            f"PROJECT FILES:\n{self._context()}\n\n"
            f"USER REQUEST:\n{request}\n\n"
            "Start by inspecting the project. If the task is large, plan internally and then execute it. "
            "Do not finish until the implementation is complete and verified."
        )
        self._session.append({"role": "user", "content": prompt})

    def run_task(self, request: str, mode: str = "build") -> dict[str, Any]:
        request = str(request or "").strip()
        if not request:
            raise CodingError("Coding request is empty.")
        if mode not in {"build", "plan"}:
            mode = "build"
        task_id = uuid.uuid4().hex[:12]
        self.state = AgentState(task_id, str(self.workspace.root), request, mode, time.time())
        self._bootstrap()
        self._status(f"Coding task {task_id} started.")
        before = self.workspace.snapshot()

        try:
            for step in range(1, MAX_AGENT_STEPS + 1):
                if self._stop.is_set():
                    self.state.status = "stopped"
                    break
                self.state.step = step
                self._save_state()

                # Re-anchor context periodically so long jobs do not drift.
                if step == 1 or step % 8 == 0:
                    self._session.append({
                        "role": "user",
                        "content": (
                            "CURRENT WORKSPACE SNAPSHOT:\n" + self._context() +
                            "\nContinue the task from the current filesystem state."
                        ),
                    })

                raw = self._call_model(
                    "Continue executing the coding task. Inspect or modify the workspace as needed. "
                    "Return one JSON tool action only."
                )
                action = self._normalize_action(self._parse_json(raw))
                if action.get("action") == "finish":
                    summary = str(action.get("summary", "Coding task completed."))
                    # Never report an explicit model failure as a successful build.
                    if any(token in summary.lower() for token in (
                        "unable to complete", "no files were modified",
                        "could not complete", "failed to complete",
                    )) and not self.state.changes:
                        self.state.status = "failed"
                        self.state.summary = summary
                    else:
                        self.state.status = "completed"
                        self.state.summary = summary
                    break

                tool = str(action.get("tool", "")).strip().lower()
                args = action.get("args") or {}
                if not tool:
                    invalid_count = getattr(self, "_invalid_tool_count", 0) + 1
                    self._invalid_tool_count = invalid_count
                    result = {
                        "ok": False,
                        "error": "No coding tool was selected. Choose exactly one of: tree, read, glob, grep, write, edit, run, finish.",
                    }
                    self._status(f"Coding model returned no tool name (retry {invalid_count}/{MAX_INVALID_TOOL_RETRIES}).")
                    self._session.append({
                        "role": "user",
                        "content": (
                            "PROTOCOL ERROR: your previous JSON selected no tool. "
                            "Return exactly one JSON object using one of these tools: "
                            "tree, read, glob, grep, write, edit, run, finish. "
                            "For write include path and content; for run include command. "
                            "Do not return prose or markdown."
                        ),
                    })
                    if invalid_count >= MAX_INVALID_TOOL_RETRIES:
                        self.state.status = "failed"
                        self.state.summary = "Coding model repeatedly returned no valid workspace tool."
                        break
                    continue

                try:
                    result = self._tool(tool, args)
                    if result.get("change"):
                        self.state.changes.append(result["change"])
                    self._status(f"Coding: {tool} {args.get('path', args.get('command', ''))}".strip())
                except Exception as exc:
                    result = {"ok": False, "error": str(exc)}
                    self.state.last_error = str(exc)
                    self._status(f"Coding tool error: {exc}")

                self._invalid_tool_count = 0
                serialized = json.dumps(result, ensure_ascii=False)
                if len(serialized) > MAX_TOOL_OUTPUT:
                    serialized = serialized[:MAX_TOOL_OUTPUT] + "..."
                self._session.append({
                    "role": "user",
                    "content": f"TOOL RESULT ({tool}):\n{serialized}\nContinue.",
                })

                # In plan mode, permit inspection but don't permit mutations.
                if mode == "plan" and tool in {"write", "edit", "run"}:
                    self.state.status = "planned"
                    self.state.summary = "Plan-only mode blocked a mutating/execution action."
                    break
            else:
                self.state.status = "max_steps"
                self.state.summary = "Task reached the safety step limit; state was preserved for continuation."

            after = self.workspace.snapshot()
            changed = []
            for path, digest in after.items():
                if before.get(path) != digest:
                    changed.append(path)
            for path in before:
                if path not in after:
                    changed.append(path)
            self.state.changes = self.state.changes or []
            self._save_state()
            self._status(self.state.summary or self.state.status)
            return {
                "ok": self.state.status in {"completed", "planned"},
                "task_id": self.state.task_id,
                "status": self.state.status,
                "summary": self.state.summary,
                "steps": self.state.step,
                "changed_files": sorted(set(changed)),
                "state_file": str(self._state_path()),
            }
        except Exception as exc:
            self.state.status = "failed"
            self.state.last_error = str(exc)
            self.state.summary = f"Coding task failed: {exc}"
            self._save_state()
            self._status(self.state.summary)
            return {
                "ok": False,
                "task_id": self.state.task_id,
                "status": "failed",
                "summary": self.state.summary,
                "steps": self.state.step,
                "state_file": str(self._state_path()),
            }

    def inspect(self) -> dict[str, Any]:
        return {
            "root": str(self.workspace.root),
            "files": self.workspace.tree(max_files=500),
            "coding_state_dir": str(self.workspace.root / ".jeev" / "coding"),
        }
