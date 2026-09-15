"""JEEV image OCR/vision analyzer."""
from __future__ import annotations
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS={".png",".jpg",".jpeg",".webp",".gif",".bmp",".tif",".tiff"}

def is_image_file(path:str|Path)->bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS

def analyze_image(image_path:str,instruction:str="",*,client:Any=None,max_tokens:int=3000)->str:
    path=Path(image_path)
    if not path.exists(): return f"Image not found: {path}"
    if not is_image_file(path): return f"Unsupported image type: {path.suffix or 'unknown'}"
    if client is None:
        try:
            from or_client import client as jeev_client
            client=jeev_client
        except Exception as exc:
            return f"OpenRouter client is unavailable: {exc}"
    instruction=str(instruction or "").strip()
    if not instruction:
        instruction=("Read ALL visible text in this image carefully. Preserve order and wording "
                     "as accurately as possible. If it is a screenshot, document, table, form, "
                     "code, receipt, sign, or handwritten text, extract visible text first, then "
                     "briefly explain the image. Do not invent text.")
    else:
        instruction=("First inspect the image carefully and read all visible text relevant to the "
                     "request. Do not invent text.\n\nUser request: "+instruction)
    system=("You are JEEV MARK I's image-reading engine. Read visible text faithfully. Preserve "
            "headings, labels, numbers, URLs, names and code where possible. If text is uncertain, "
            "mark it [unclear] rather than guessing. Then answer the requested analysis.")
    try:
        result=client.vision_from_file(prompt=instruction,image_path=str(path),system=system,max_tokens=max_tokens)
    except Exception as exc:
        return f"Image analysis failed safely: {exc}"
    return str(result).strip() if result else "I could not get a usable vision result from OpenRouter."
