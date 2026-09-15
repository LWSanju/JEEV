from __future__ import annotations

import json
from pathlib import Path
from typing import Any

class CapabilityRegistry:
    def __init__(self, path: Path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data=self._load()
    def _load(self):
        if not self.path.exists(): return {"plugins":{},"capabilities":{}}
        try: return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception: return {"plugins":{},"capabilities":{}}
    def save(self): self.path.write_text(json.dumps(self.data,indent=2,ensure_ascii=False),encoding="utf-8")
    def register(self,manifest,root:Path,enabled=True):
        self.data.setdefault("plugins",{})[manifest.id]={**manifest.to_dict(),"root":str(root),"enabled":bool(enabled)}
        caps=self.data.setdefault("capabilities",{})
        for cap in manifest.capabilities:
            caps[cap]={"plugin_id":manifest.id,"enabled":bool(enabled)}
        self.save()
    def unregister(self,plugin_id):
        self.data.setdefault("plugins",{}).pop(plugin_id,None)
        self.data["capabilities"]={k:v for k,v in self.data.get("capabilities",{}).items() if v.get("plugin_id")!=plugin_id}
        self.save()
    def set_enabled(self,plugin_id,enabled):
        p=self.data.get("plugins",{}).get(plugin_id)
        if not p: return False
        p["enabled"]=bool(enabled)
        for cap,v in self.data.get("capabilities",{}).items():
            if v.get("plugin_id")==plugin_id: v["enabled"]=bool(enabled)
        self.save(); return True
    def has_capability(self,cap):
        v=self.data.get("capabilities",{}).get(cap)
        return bool(v and v.get("enabled"))
    def plugin_for(self,cap):
        v=self.data.get("capabilities",{}).get(cap)
        if not v or not v.get("enabled"): return None
        return self.data.get("plugins",{}).get(v.get("plugin_id"))
    def list_plugins(self): return list(self.data.get("plugins",{}).values())

