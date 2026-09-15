from __future__ import annotations

from pathlib import Path
from .manifest import MANIFEST_NAME, PluginManifest
from .permissions import classify_permissions

BLOCKED_FILES={".env","api_keys.json"}
BLOCKED_EXTENSIONS={".exe",".dll",".sys"}

def validate_plugin_directory(root: Path, source: str = "") -> tuple[PluginManifest,list[str]]:
    root=Path(root)
    manifest_path=root/MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"Missing {MANIFEST_NAME}.")
    manifest=PluginManifest.from_file(manifest_path,source=source)
    entry=root/manifest.entrypoint
    if not entry.is_file():
        raise ValueError(f"Plugin entrypoint not found: {manifest.entrypoint}")
    if Path(manifest.entrypoint).is_absolute() or ".." in Path(manifest.entrypoint).parts:
        raise ValueError("Entrypoint must stay inside the plugin directory.")
    warnings=[]
    for p in root.rglob("*"):
        if not p.is_file(): continue
        if p.name.lower() in BLOCKED_FILES:
            raise ValueError(f"Plugin contains blocked sensitive file: {p.name}")
        if p.suffix.lower() in BLOCKED_EXTENSIONS:
            warnings.append(f"Binary file present: {p.relative_to(root)}")
    risk=classify_permissions(manifest.permissions)
    if risk=="high": warnings.append("Plugin requests high-risk permissions; explicit approval is required before activation.")
    return manifest,warnings

