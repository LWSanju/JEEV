from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from .validator import validate_plugin_directory
from .lifecycle import write_install_record

TIMEOUT=30

def _github_archive(url:str)->str:
    u=urlparse(url)
    parts=[x for x in u.path.strip("/").split("/") if x]
    if len(parts)<2: raise ValueError("GitHub URL must point to owner/repository.")
    owner,repo=parts[0],parts[1]
    repo=repo.removesuffix(".git")
    return f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"

def download_github(url:str,dest:Path)->Path:
    archive_url=_github_archive(url)
    r=requests.get(archive_url,timeout=TIMEOUT,headers={"User-Agent":"JEEV-Plugin-Manager/1.0"})
    if r.status_code==404:
        archive_url=archive_url.replace("/heads/main.zip","/heads/master.zip")
        r=requests.get(archive_url,timeout=TIMEOUT,headers={"User-Agent":"JEEV-Plugin-Manager/1.0"})
    r.raise_for_status()
    digest=hashlib.sha256(r.content).hexdigest()[:16]
    z=dest/f"plugin-{digest}.zip"
    z.write_bytes(r.content)
    return z

def install_from_url(url:str,installed_root:Path,downloads_root:Path,allow_high_risk=False):
    url=url.strip()
    if not (url.startswith("https://github.com/") or url.startswith("http://github.com/")):
        raise ValueError("For automatic installation, use a GitHub repository URL.")
    downloads_root.mkdir(parents=True,exist_ok=True); installed_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=downloads_root) as td:
        temp=Path(td); archive=download_github(url,temp)
        extract=temp/"extract"; extract.mkdir()
        with zipfile.ZipFile(archive) as z:
            z.extractall(extract)
        roots=[p for p in extract.iterdir() if p.is_dir()]
        if len(roots)!=1: raise ValueError("Plugin archive has an unexpected structure.")
        source_root=roots[0]
        manifest,warnings=validate_plugin_directory(source_root,source=url)
        from .permissions import approval_required
        if approval_required(manifest.permissions) and not allow_high_risk:
            raise PermissionError("Plugin requires approval for non-basic permissions: "+", ".join(manifest.permissions))
        target=installed_root/manifest.id
        if target.exists(): shutil.rmtree(target)
        shutil.copytree(source_root,target)
        write_install_record(target,manifest,url,warnings)
        return manifest,target,warnings

