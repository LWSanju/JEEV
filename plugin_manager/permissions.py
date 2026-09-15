from __future__ import annotations

SAFE_PERMISSIONS = {
    "file.read",
    "file.write",
    "network",
    "network.http",
    "ui.notify",
    "jeev.memory.read",
    "jeev.memory.write",
}

DANGEROUS_PERMISSIONS = {
    "process.execute",
    "system.admin",
    "credential.read",
    "desktop.control",
    "keyboard.control",
    "mouse.control",
}

def classify_permissions(perms: list[str]) -> str:
    p={str(x).strip().lower() for x in perms if str(x).strip()}
    if p & DANGEROUS_PERMISSIONS:
        return "high"
    if p - SAFE_PERMISSIONS:
        return "medium"
    return "low"

def approval_required(perms: list[str]) -> bool:
    return classify_permissions(perms) != "low"

