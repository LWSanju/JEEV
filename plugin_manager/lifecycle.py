from __future__ import annotations

import json
from pathlib import Path

def write_install_record(root:Path,manifest,source:str,warnings:list[str]):
    record={"id":manifest.id,"version":manifest.version,"source":source,"warnings":warnings,"installed_at":__import__("datetime").datetime.now().isoformat()}
    (root/".jeev-install.json").write_text(json.dumps(record,indent=2),encoding="utf-8")

