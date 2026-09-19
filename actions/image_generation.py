"""JEEV isolated Hugging Face image generation.

This module deliberately contains no JEEV tool-routing logic. It is a small
adapter around Hugging Face Inference Providers so image generation stays
separate from Gmail, WhatsApp, Spotify, browser, desktop control, and the
other existing JEEV integrations.

The model is executed remotely. Nothing from Qwen/Qwen-Image is downloaded
or loaded into the user's 8 GB RAM / CPU-only machine.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from huggingface_hub import InferenceClient
except Exception as exc:  # pragma: no cover
    InferenceClient = None
    _HF_IMPORT_ERROR = exc
else:
    _HF_IMPORT_ERROR = None


MODEL_ID = os.getenv("JEEV_IMAGE_MODEL", "Qwen/Qwen-Image")


def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _output_dir() -> Path:
    path = _base_dir() / "generated_images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(value: str | None) -> str:
    value = str(value or "").strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    value = value.strip("._-")
    if not value:
        value = f"jeev_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if not value.lower().endswith(".png"):
        value += ".png"
    return value


def _clamp_dimension(value: Any, default: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    value = max(256, min(value, 2048))
    value = (value // 8) * 8
    return max(256, value)


def _get_token() -> str:
    load_dotenv(dotenv_path=_base_dir() / ".env")
    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "HF_TOKEN is not configured. Add your Hugging Face Inference "
            "token to the JEEV project .env file as HF_TOKEN=..."
        )
    return token


def generate_image(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate one image remotely and save it as a PNG."""
    parameters = dict(parameters or {})
    prompt = str(parameters.get("prompt") or "").strip()
    if not prompt:
        return {"ok": False, "error": "An image prompt is required."}

    if InferenceClient is None:
        return {
            "ok": False,
            "error": (
                "huggingface_hub is not available. Install it with "
                "'.venv\\Scripts\\python.exe -m pip install -U huggingface_hub pillow'."
            ),
            "details": str(_HF_IMPORT_ERROR),
        }

    try:
        token = _get_token()

        # Hugging Face executes the model remotely. The local PC does not
        # download/load the Qwen model or require a dedicated GPU.
        client = InferenceClient(
            provider="auto",
            api_key=token,
        )

        width = _clamp_dimension(parameters.get("width"), 1024)
        height = _clamp_dimension(parameters.get("height"), 1024)
        negative_prompt = str(parameters.get("negative_prompt") or "").strip() or None

        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "model": MODEL_ID,
            "width": width,
            "height": height,
        }

        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt

        if parameters.get("seed") not in (None, ""):
            try:
                kwargs["seed"] = int(parameters["seed"])
            except (TypeError, ValueError):
                return {"ok": False, "error": "Seed must be an integer when supplied."}

        print(f"[JEEV] 🎨 Generating image with {MODEL_ID} via Hugging Face...")
        image = client.text_to_image(**kwargs)

        filename = _safe_filename(parameters.get("filename"))
        output_path = _output_dir() / filename
        image.save(output_path, format="PNG")

        return {
            "ok": True,
            "message": "Image generated successfully.",
            "model": MODEL_ID,
            "path": str(output_path),
            "prompt": prompt,
            "width": width,
            "height": height,
        }

    except Exception as exc:
        error = str(exc).strip() or exc.__class__.__name__
        print(f"[JEEV] ❌ Image generation failed: {error}")
        return {"ok": False, "error": error, "model": MODEL_ID}


__all__ = ["generate_image"]
