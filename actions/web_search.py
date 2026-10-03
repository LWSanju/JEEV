"""JEEV web research action.

Important: this is background research, not visible browser control.
Visible browser interaction belongs to actions.browser_control.py and should
only be selected when the user explicitly asks to use the browser.
"""
from __future__ import annotations

from urllib.parse import quote
import json
import os
import requests


def _ddg_instant_answer(query: str) -> str:
    url = "https://api.duckduckgo.com/?q=" + quote(query) + "&format=json&no_html=1&skip_disambig=1"
    response = requests.get(url, timeout=8, headers={"User-Agent": "JEEV/1.0"})
    response.raise_for_status()
    data = response.json()

    abstract = str(data.get("AbstractText") or "").strip()
    if abstract:
        source = str(data.get("AbstractSource") or "").strip()
        return f"{abstract} [{source}]" if source else abstract

    related = data.get("RelatedTopics") or []
    snippets = []
    for item in related[:5]:
        if isinstance(item, dict):
            text = str(item.get("Text") or "").strip()
            if text:
                snippets.append(text)

    return "\n".join(snippets)


def _fallback_search(query: str) -> str:
    """Use the installed duckduckgo-search package when available."""
    try:
        from duckduckgo_search import DDGS
        results = list(DDGS().text(query, max_results=5))
        if not results:
            return "No background search results were found."
        lines = []
        for item in results:
            title = str(item.get("title") or "").strip()
            body = str(item.get("body") or "").strip()
            href = str(item.get("href") or "").strip()
            lines.append(f"{title}: {body} ({href})")
        return "\n".join(lines)
    except Exception as exc:
        return f"Background research unavailable: {exc}"


def web_search(parameters=None, player=None):
    parameters = parameters or {}
    query = str(parameters.get("query", "")).strip()
    mode = str(parameters.get("mode", "search")).strip().lower()
    items = parameters.get("items", [])
    aspect = str(parameters.get("aspect", "")).strip()

    if not query and not items:
        return "No search query was provided."

    if mode == "compare" and items:
        query = " vs ".join(str(item) for item in items)
        if aspect:
            query += f" {aspect}"

    try:
        result = _ddg_instant_answer(query)
        if result:
            return f"Background research for: {query}\n{result}"
    except Exception:
        pass

    result = _fallback_search(query)
    return f"Background research for: {query}\n{result}"
