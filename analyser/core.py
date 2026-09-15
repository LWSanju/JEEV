"""Unified JEEV analyzer used by main.py."""
from __future__ import annotations
import logging, threading
from pathlib import Path
from typing import Any
from .image_analyser import analyze_image,is_image_file
from .document_analyser import extract_document
logger=logging.getLogger("jeev.analyser")

class JEEVAnalyzer:
    def __init__(self):
        self._lock=threading.RLock(); self._path=None; self._name=None; self._text=""; self._meta={}
    def clear(self):
        with self._lock: self._path=self._name=None; self._text=""; self._meta={}
    def _client(self):
        from or_client import client
        return client
    def _save(self,path,text,meta):
        with self._lock: self._path=str(path); self._name=path.name; self._text=text[:120000]; self._meta=dict(meta)
    def _snapshot(self):
        with self._lock: return self._path,self._name,self._text,dict(self._meta)
    @staticmethod
    def _action(x):
        x=str(x or "analyze").strip().lower()
        return {"read":"extract_text","ocr":"extract_text","text":"extract_text","extract":"extract_text","summarise":"summary","summarize":"summary","question":"ask","qa":"ask","clear_context":"clear"}.get(x,x)
    def analyze(self,file_path=None,action="analyze",instruction="",question=""):
        action=self._action(action); requested=str(file_path or "").strip()
        if action=="clear": self.clear(); return "Analyzer context cleared."
        if not requested:
            p,name,text,meta=self._snapshot()
            if not p: return "No file is currently selected. Upload or select an image or document first."
            if action in {"ask","summary","analyze","extract_text"}: return self._answer(action,instruction,question,name or Path(p).name,text,meta)
        path=Path(requested).expanduser()
        if not path.exists(): return f"File not found: {path}"
        if not path.is_file(): return f"That path is not a file: {path}"
        if is_image_file(path):
            r=analyze_image(str(path),instruction or question,client=self._client())
            if r: self._save(path,r,{"type":"image","pages":1})
            return r
        try: text,meta=extract_document(path,client=self._client())
        except Exception as e: return f"Document extraction failed safely: {e}"
        if not text.strip(): return str(meta.get("error") or "I could not extract readable content from that file.")
        self._save(path,text,meta)
        if action=="extract_text": return f"Extracted {meta.get('type','file')} text ({meta.get('pages',1)} page(s)).\n\n{text[:100000]}"
        return self._answer(action,instruction,question,path.name,text,meta)
    def _answer(self,action,instruction,question,name,text,meta):
        if action=="extract_text": return f"Extracted {meta.get('type','file')} text ({meta.get('pages',1)} page(s)).\n\n{text[:100000]}"
        if action=="summary": task="Summarize the document clearly. Include purpose, important points, key numbers/names/dates and conclusion. Cite page markers when available."
        elif action=="ask": task=str(question or instruction or "Answer the user's question using only the document.").strip()
        else: task=str(instruction or question or "Analyze this file and give a concise useful answer. Mention important findings and page numbers when available.").strip()
        prompt=(f"FILE: {name}\nFILE TYPE: {meta.get('type','unknown')}\n\nDOCUMENT CONTENT:\n{text[:100000]}\n\nUSER TASK:\n{task}\n\nRULES:\n- Use the document as the primary source.\n- Do not invent unsupported facts.\n- If the answer is not present, say so.\n- Preserve [PAGE N] references when useful.\n- Do not silently guess [unclear] OCR text.")
        try: r=self._client().chat(prompt=prompt,system="You are JEEV MARK I's document reasoning engine. Answer using the supplied local-file content. Be accurate and explicit about uncertainty.",max_tokens=5000,temperature=0.15)
        except Exception as e: return f"Document reasoning failed safely: {e}"
        return str(r).strip() if r else "The file was read successfully, but OpenRouter did not return a usable analysis response."

analyzer=JEEVAnalyzer()
def analyze_file(parameters=None,player=None,speak=None):
    a=parameters or {}
    return analyzer.analyze(file_path=a.get("file_path") or a.get("path") or a.get("file"),action=a.get("action") or a.get("mode") or "analyze",instruction=a.get("instruction") or a.get("prompt") or "",question=a.get("question") or a.get("query") or "")
