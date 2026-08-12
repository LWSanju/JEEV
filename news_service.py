"""JEEV fresh, location-aware and user-relevant news service.

Uses Google News RSS over HTTPS, so no news API key is required. The service
returns current search results and never treats news as permanent memory.
"""
from __future__ import annotations

import html
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta


NEWS_TIMEOUT = float(os.getenv("JEEV_NEWS_TIMEOUT", "8"))
DEFAULT_LIMIT = 8
MAX_LIMIT = 12


def _fetch_rss(query: str, days: int, limit: int) -> list[dict]:
    q = query.strip()
    if not q:
        return []

    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": f"{q} when:{max(1, min(int(days), 30))}d",
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "JEEV/1.0 news-service"})
    with urllib.request.urlopen(req, timeout=NEWS_TIMEOUT) as response:
        raw = response.read()

    root = ET.fromstring(raw)
    results = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))

    for item in root.findall("./channel/item"):
        title = html.unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source = item.findtext("source") or ""
        description = html.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).strip()

        if not title:
            continue

        dt = None
        if pub:
            try:
                dt = parsedate_to_datetime(pub)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt = dt.astimezone(timezone.utc)
            except Exception:
                pass
        if dt and dt < cutoff:
            continue

        results.append({
            "title": title,
            "source": source.strip(),
            "published": dt.isoformat() if dt else pub,
            "link": link,
            "summary": description[:500],
        })
        if len(results) >= limit:
            break

    return results


def _extract_location(location_text: str) -> str:
    text = (location_text or "").strip()
    prefix = "Approximate current location:"
    if prefix in text:
        text = text.split(prefix, 1)[1].split("\n", 1)[0].strip()
    return text


def get_relevant_news(query: str = "", location: str = "", days: int = 3,
                      limit: int = DEFAULT_LIMIT, memory_text: str = "") -> str:
    """Return fresh news based on location, optional query, and remembered interests."""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    days = max(1, min(int(days or 3), 30))

    if not location:
        try:
            from location_service import get_user_location
            location = get_user_location()
        except Exception:
            location = ""

    loc = _extract_location(location)
    user_query = (query or "").strip()

    searches = []
    if user_query:
        searches.append(user_query)
    if loc:
        searches.append(f"{loc} latest news")

    # Pull a small number of remembered topic words. This is deliberately conservative:
    # memory is context, not a command to search private information.
    if memory_text:
        topic_terms = []
        for line in memory_text.splitlines():
            low = line.lower()
            if any(k in low for k in ("interest", "project", "startup", "technology", "career", "education")):
                cleaned = re.sub(r"^[\s\-*•#]+", "", line).strip()
                if cleaned and len(cleaned) < 180:
                    topic_terms.append(cleaned)
        if topic_terms:
            searches.append(f"{loc} {topic_terms[0]} news" if loc else f"{topic_terms[0]} news")

    if not searches:
        searches.append("India latest news")

    seen = set()
    articles = []
    for search in searches:
        try:
            for item in _fetch_rss(search, days, limit):
                key = re.sub(r"\W+", " ", item["title"].lower()).strip()
                if key in seen:
                    continue
                seen.add(key)
                articles.append(item)
                if len(articles) >= limit:
                    break
        except Exception as exc:
            if not articles:
                return f"Fresh news is currently unavailable: {exc}"
        if len(articles) >= limit:
            break

    if not articles:
        return "No fresh relevant news was found in the requested time window."

    lines = [
        "FRESH RELEVANT NEWS",
        "===================",
        f"Location context: {loc or 'not available'}",
        f"Freshness window: last {days} day(s)",
        "",
    ]
    for idx, item in enumerate(articles, 1):
        source = f" — {item['source']}" if item["source"] else ""
        lines.append(f"{idx}. {item['title']}{source}")
        if item["published"]:
            lines.append(f"   Published: {item['published']}")
        if item["summary"]:
            lines.append(f"   {item['summary']}")
        if item["link"]:
            lines.append(f"   Link: {item['link']}")
        lines.append("")

    return "\n".join(lines).strip()