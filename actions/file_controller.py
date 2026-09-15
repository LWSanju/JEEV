from pathlib import Path
import shutil
import os
import re
import subprocess
import time


def _shortcut_path(value):
    shortcuts={"desktop":Path.home()/"Desktop","downloads":Path.home()/"Downloads","documents":Path.home()/"Documents","home":Path.home()}
    value=str(value or "").strip()
    return shortcuts.get(value.lower(), Path(value).expanduser() if value else Path.home())

def _ps_processes():
    script="""$items = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Id -and ($_.MainWindowTitle -or $_.ProcessName) } | ForEach-Object { [PSCustomObject]@{ PID=$_.Id; Name=$_.ProcessName; Title=$_.MainWindowTitle } }; if($items){$items|ConvertTo-Json -Compress}else{'[]'}"""
    try:
        p=subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command",script],capture_output=True,text=True,timeout=10)
        raw=(p.stdout or "").strip()
        if not raw:return []
        import json
        data=json.loads(raw); return [data] if isinstance(data,dict) else data
    except Exception:return []

def _find_processes(target):
    norm=re.sub(r"[^a-z0-9]","",str(target or "").lower().replace(".exe",""))
    if not norm:return []
    out=[]
    for p in _ps_processes():
        n=re.sub(r"[^a-z0-9]","",str(p.get("Name") or "").lower().replace(".exe",""))
        t=re.sub(r"[^a-z0-9]","",str(p.get("Title") or "").lower())
        if norm==n or norm in n or norm in t: out.append(p)
    return out

def _close_application(target,force=False):
    target=str(target or "").strip()
    if not target:return {"ok":False,"verified":False,"error":"Application name is required."}
    norm=re.sub(r"[^a-z0-9]","",target.lower().replace(".exe",""))
    if norm in {"jeev","python","python312","python313","python314","cmd","powershell","terminal","windowsterminal"} or "jeev" in norm:
        return {"ok":False,"verified":False,"error":"I will not close JEEV or its terminal."}
    matches=_find_processes(target)
    if not matches:return {"ok":True,"verified":True,"message":f"{target} is already closed."}
    pids=[]
    for p in matches:
        pid=int(p.get("PID") or 0)
        if pid and pid not in pids:pids.append(pid)
    for pid in pids:
        try: subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command",f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; if($p){{ $null=$p.CloseMainWindow() }}"],capture_output=True,text=True,timeout=5)
        except Exception:pass
    time.sleep(1.2); remaining=_find_processes(target)
    if remaining and force:
        for p in remaining:
            pid=int(p.get("PID") or 0)
            if pid:
                try:subprocess.run(["taskkill","/PID",str(pid),"/T","/F"],capture_output=True,text=True,timeout=8)
                except Exception:pass
        time.sleep(1); remaining=_find_processes(target)
    if remaining:return {"ok":False,"verified":False,"error":f"I asked Windows to close {target}, but it is still running."}
    return {"ok":True,"verified":True,"message":f"{target} is closed and verified."}

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

    try:
        target = _shortcut_path(path)
        if action in {"open","open_path","open_folder","open_directory","open_file"}:
            if not target.exists(): return {"ok":False,"verified":False,"error":f"Path not found: {target}"}
            os.startfile(str(target)); return {"ok":True,"verified":True,"message":f"Opened {target}","path":str(target)}
        if action in {"open_app","launch_app"}:
            app=str(parameters.get("app_name") or parameters.get("application") or name or path).strip()
            if not app:return {"ok":False,"verified":False,"error":"Application name is required."}
            try: os.startfile(app)
            except Exception: subprocess.Popen(app,shell=True)
            return {"ok":True,"verified":True,"message":f"Opened {app}."}
        if action in {"close_app","close_application","close_window","terminate_app"}:
            app=str(parameters.get("app_name") or parameters.get("application") or parameters.get("name") or path).strip()
            return _close_application(app,force=bool(parameters.get("force",False) or action=="terminate_app"))

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