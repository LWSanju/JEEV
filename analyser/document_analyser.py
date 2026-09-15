"""JEEV document extraction: PDF native text + OCR for scanned pages, DOCX/XLSX/text."""
from __future__ import annotations
import json, logging, tempfile
from pathlib import Path
from typing import Any
logger=logging.getLogger("jeev.analyser.document")
MAX_TEXT=90000; MAX_PDF_PAGES=60; MAX_OCR=9000
TEXT_EXT={".txt",".md",".markdown",".log",".csv",".json",".xml",".py",".js",".ts",".html",".css",".yaml",".yml"}

def _clean(x:Any)->str: return str(x or "").replace("\x00","").strip()

def _plain(path:Path)->str: return path.read_text(encoding="utf-8",errors="replace")[:MAX_TEXT]

def _docx(path:Path)->str:
    try: from docx import Document
    except Exception: return "DOCX support requires python-docx."
    try:
        d=Document(str(path)); out=[]
        for p in d.paragraphs:
            if _clean(p.text): out.append(_clean(p.text))
        for n,t in enumerate(d.tables,1):
            out.append(f"[TABLE {n}]")
            for r in t.rows: out.append(" | ".join(_clean(c.text) for c in r.cells))
        return "\n".join(out)[:MAX_TEXT]
    except Exception as e: return f"DOCX extraction failed: {e}"

def _sheet(path:Path)->str:
    try: import openpyxl
    except Exception: return "Spreadsheet support requires openpyxl."
    try:
        wb=openpyxl.load_workbook(str(path),read_only=True,data_only=True); out=[]
        for ws in wb.worksheets:
            out.append(f"[SHEET: {ws.title}]")
            for row in ws.iter_rows(values_only=True):
                vals=["" if v is None else str(v) for v in row]
                if any(vals): out.append(" | ".join(vals))
        return "\n".join(out)[:MAX_TEXT]
    except Exception as e: return f"Spreadsheet extraction failed: {e}"

def _pdf_native(path:Path):
    try:
        import fitz
        doc=fitz.open(str(path)); pages=[]; sparse=0
        for i in range(min(len(doc),MAX_PDF_PAGES)):
            t=_clean(doc[i].get_text("text")); pages.append(t); sparse += len(t)<40
        return doc,pages,sparse>0
    except Exception as e:
        logger.warning("PyMuPDF unavailable: %s",e)
        try:
            from pypdf import PdfReader
            r=PdfReader(str(path)); pages=[]
            for p in r.pages[:MAX_PDF_PAGES]: pages.append(_clean(p.extract_text() or ""))
            return None,pages,any(len(x)<40 for x in pages)
        except Exception as e2:
            logger.warning("pypdf unavailable: %s",e2); return None,[],True

def _ocr(doc,pages,client):
    out={}
    if doc is None: return out
    with tempfile.TemporaryDirectory(prefix="jeev_pdf_ocr_") as td:
        for i,t in enumerate(pages):
            if len(t)>=40: continue
            try:
                pix=doc[i].get_pixmap(matrix=__import__('fitz').Matrix(1.8,1.8),alpha=False)
                img=Path(td)/f"page_{i+1}.png"; pix.save(str(img))
                prompt=(f"This is page {i+1} of a PDF. Read ALL visible text accurately. Preserve "
                        "headings, labels, numbers, table cells, URLs and code. Do not summarize "
                        "before transcribing. Use [unclear] for genuinely unreadable text.")
                system="You are JEEV MARK I's PDF OCR engine. Extract visible text accurately. Do not invent missing text."
                r=client.vision_from_file(prompt=prompt,image_path=str(img),system=system,max_tokens=MAX_OCR)
                if r: out[i+1]=str(r).strip()[:MAX_OCR]
            except Exception as e: logger.warning("OCR page %s failed: %s",i+1,e)
    return out

def extract_document(path:Path,*,client:Any):
    ext=path.suffix.lower()
    if ext==".pdf":
        doc,pages,needs=_pdf_native(path); ocr=_ocr(doc,pages,client) if needs else {}
        blocks=[]
        for n in range(1,max(len(pages),max(ocr.keys(),default=0))+1):
            native=pages[n-1] if n<=len(pages) else ""; scanned=ocr.get(n,"")
            if native: blocks.append(f"[PAGE {n}]\n{native}")
            if scanned and scanned.strip()!=native.strip(): blocks.append(f"[PAGE {n} — IMAGE/OCR]\n{scanned}")
        return "\n\n".join(blocks)[:MAX_TEXT],{"type":"pdf","pages":len(pages),"ocr_pages":sorted(ocr)}
    if ext in TEXT_EXT:
        t=_plain(path)
        if ext==".json":
            try: t=json.dumps(json.loads(t),indent=2,ensure_ascii=False)
            except Exception: pass
        return t[:MAX_TEXT],{"type":"text","pages":1}
    if ext==".docx": return _docx(path),{"type":"docx","pages":1}
    if ext in {".xlsx",".xlsm",".xls"}: return _sheet(path),{"type":"spreadsheet","pages":1}
    return "",{"type":"unsupported","pages":0,"error":f"Unsupported document type: {ext or 'unknown'}"}
