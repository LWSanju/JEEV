"""JEEV background research policy.

This module only classifies research intent. It does not open a browser.
"""
from __future__ import annotations

import re


class ResearchPolicy:
    EXPLICIT_BROWSER_PATTERNS = (
        r"\bsearch (?:this|that|it|the web|online) in (?:the )?browser\b",
        r"\bsearch (?:this|that|it) in (?:the )?browser\b",
        r"\buse (?:the )?browser\b",
        r"\bbrowse (?:the )?web\b",
        r"\bopen (?:the )?browser\b",
        r"\bsearch (?:it|this|that) on google\b",
        r"\blook (?:it|this|that) up in (?:the )?browser\b",
        r"\bgo to https?://",
    )

    FRESHNESS_PATTERNS = (
        r"\b(latest|current|today|tonight|this week|right now|recent|newest)\b",
        r"\b(as of|updated|update|verify|fact[- ]check|check whether)\b",
        r"\b(price|stock|weather|news|score|schedule|availability)\b",
        r"\bwhat happened\b",
        r"\bis .+ still\b",
    )

    @classmethod
    def wants_visible_browser(cls, text: str) -> bool:
        value = str(text or "").strip().lower()
        return any(re.search(p, value) for p in cls.EXPLICIT_BROWSER_PATTERNS)

    @classmethod
    def needs_fresh_research(cls, text: str) -> bool:
        value = str(text or "").strip().lower()
        if cls.wants_visible_browser(value):
            return False
        return any(re.search(p, value) for p in cls.FRESHNESS_PATTERNS)

    @classmethod
    def classify(cls, text: str) -> str:
        if cls.wants_visible_browser(text):
            return "visible_browser"
        if cls.needs_fresh_research(text):
            return "background_research"
        return "own_knowledge"

    @classmethod
    def instruction(cls) -> str:
        return (
            "[RESEARCH ROUTING] "
            "Use own knowledge for ordinary questions. "
            "Use background_research for freshness/verification without opening "
            "a visible browser. Use browser_control only when the user explicitly "
            "requests browser use or a browser interaction."
        )
