from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MANIFEST_NAME = "jeev.plugin.json"

@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    description: str
    entrypoint: str = "plugin.py"
    capabilities: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    minimum_jeev_version: str = "1.0.0"
    source: str = ""
    trust: str = "community"
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path, source: str = "") -> "PluginManifest":
        data=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data,dict):
            raise ValueError("Plugin manifest must contain a JSON object.")
        required=("id","name","version","description")
        missing=[k for k in required if not str(data.get(k,"")).strip()]
        if missing:
            raise ValueError("Plugin manifest is missing: "+", ".join(missing))
        pid=str(data["id"]).strip().lower()
        if not pid.replace("_","-").replace(".","").isalnum():
            raise ValueError("Plugin id contains unsupported characters.")
        return cls(
            id=pid, name=str(data["name"]).strip(), version=str(data["version"]).strip(),
            description=str(data["description"]).strip(), entrypoint=str(data.get("entrypoint") or "plugin.py"),
            capabilities=[str(x).strip() for x in data.get("capabilities",[]) if str(x).strip()],
            triggers=[str(x).strip() for x in data.get("triggers",[]) if str(x).strip()],
            permissions=[str(x).strip().lower() for x in data.get("permissions",[]) if str(x).strip()],
            dependencies=[str(x).strip() for x in data.get("dependencies",[]) if str(x).strip()],
            minimum_jeev_version=str(data.get("minimum_jeev_version") or "1.0.0"),
            source=source or str(data.get("source") or ""), trust=str(data.get("trust") or "community"), raw=data,
        )

    def to_dict(self):
        return {
            "id":self.id,"name":self.name,"version":self.version,"description":self.description,
            "entrypoint":self.entrypoint,"capabilities":self.capabilities,"triggers":self.triggers,
            "permissions":self.permissions,"dependencies":self.dependencies,
            "minimum_jeev_version":self.minimum_jeev_version,"source":self.source,"trust":self.trust
        }

