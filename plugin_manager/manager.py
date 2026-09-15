from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path
from threading import RLock

from .installer import install_from_url
from .registry import CapabilityRegistry
from .validator import validate_plugin_directory

_URL_RE=re.compile(r"https?://[^\s<>\"']+",re.I)

class PluginManager:
    def __init__(self,base_dir:Path|None=None):
        self.base_dir=Path(base_dir or Path(__file__).resolve().parent.parent)
        self.plugins_dir=self.base_dir/"plugins"
        self.installed_dir=self.plugins_dir/"installed"
        self.downloads_dir=self.plugins_dir/"downloads"
        self.cache_dir=self.plugins_dir/"cache"
        self.disabled_dir=self.plugins_dir/"disabled"
        for p in (self.installed_dir,self.downloads_dir,self.cache_dir,self.disabled_dir): p.mkdir(parents=True,exist_ok=True)
        self.registry=CapabilityRegistry(self.plugins_dir/"registry"/"registry.json")
        self._lock=RLock()
        self._loaded={}
        self.scan()

    def scan(self):
        with self._lock:
            for root in self.installed_dir.iterdir():
                if not root.is_dir(): continue
                try:
                    manifest,warnings=validate_plugin_directory(root)
                    self.registry.register(manifest,root,enabled=True)
                except Exception as exc:
                    print(f"[JEEV][Plugins] Ignoring invalid plugin {root.name}: {exc}")

    def extract_url(self,text:str)->str|None:
        m=_URL_RE.search(text or "")
        return m.group(0).rstrip(".,);]}") if m else None

    def install_url(self,url:str,allow_high_risk=False):
        manifest,target,warnings=install_from_url(url,self.installed_dir,self.downloads_dir,allow_high_risk=allow_high_risk)
        self.registry.register(manifest,target,enabled=True)
        return {"ok":True,"plugin":manifest.to_dict(),"path":str(target),"warnings":warnings}

    def install_from_text(self,text:str,allow_high_risk=False):
        url=self.extract_url(text)
        if not url: return {"ok":False,"error":"No GitHub plugin URL found."}
        return self.install_url(url,allow_high_risk=allow_high_risk)

    def list_plugins(self): return self.registry.list_plugins()
    def has_capability(self,capability:str)->bool: return self.registry.has_capability(capability)

    def disable(self,plugin_id:str):
        p=self.registry.data.get("plugins",{}).get(plugin_id)
        if not p: return {"ok":False,"error":"Plugin not found."}
        self.registry.set_enabled(plugin_id,False); return {"ok":True,"message":f"{plugin_id} disabled."}

    def enable(self,plugin_id:str):
        p=self.registry.data.get("plugins",{}).get(plugin_id)
        if not p: return {"ok":False,"error":"Plugin not found."}
        self.registry.set_enabled(plugin_id,True); return {"ok":True,"message":f"{plugin_id} enabled."}

    def uninstall(self,plugin_id:str):
        p=self.registry.data.get("plugins",{}).get(plugin_id)
        if not p: return {"ok":False,"error":"Plugin not found."}
        root=Path(p.get("root",self.installed_dir/plugin_id))
        self.registry.unregister(plugin_id)
        if root.exists(): shutil.rmtree(root)
        self._loaded.pop(plugin_id,None)
        return {"ok":True,"message":f"{plugin_id} uninstalled."}

    def status_text(self):
        plugins=self.list_plugins()
        if not plugins: return "No plugins installed yet."
        lines=[f"{len(plugins)} plugin(s) installed:"]
        for p in plugins:
            state="enabled" if p.get("enabled") else "disabled"
            lines.append(f"â€¢ {p.get('name',p.get('id'))} {p.get('version','')} â€” {state}")
        return "\n".join(lines)

    def maybe_handle_chat(self,text:str):
        """Handle plugin-manager chat commands without touching the main AI loop."""
        t=(text or "").strip()
        low=t.lower()
        if not t: return None
        if self.extract_url(t) and any(x in low for x in ("plugin","install","github","add this")):
            return self.install_from_text(t)
        if low in {"show plugins","list plugins","my plugins","installed plugins"}:
            return {"ok":True,"message":self.status_text()}
        m=re.match(r"(?:disable|turn off)\s+plugin\s+([a-z0-9_.-]+)$",low)
        if m: return self.disable(m.group(1))
        m=re.match(r"(?:enable|turn on)\s+plugin\s+([a-z0-9_.-]+)$",low)
        if m: return self.enable(m.group(1))
        m=re.match(r"uninstall\s+plugin\s+([a-z0-9_.-]+)$",low)
        if m: return self.uninstall(m.group(1))
        return None

_SINGLETON=None
def get_plugin_manager(base_dir=None):
    global _SINGLETON
    if _SINGLETON is None: _SINGLETON=PluginManager(base_dir)
    return _SINGLETON

