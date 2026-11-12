# research/extract.py — turn HTML into clean article text + metadata.
# trafilatura first; a simple tag-strip fallback keeps tests dependency-free.
# Also exposes `normalize()` used by quote verification (Rule S3).
from __future__ import annotations

import html as _html
import re
from urllib.parse import urlparse


def normalize(text: str) -> str:
    """Normalize whitespace, quote marks and dashes so verbatim checks are fair."""
    t = _html.unescape(text or "")
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("—", "-").replace("–", "-").replace(" ", " ").replace("…", "...")
    return re.sub(r"\s+", " ", t).strip()


def extract(page: dict) -> dict:
    html = page.get("html", "")
    text, title, date = "", "", ""
    try:
        import trafilatura
        text = trafilatura.extract(html, include_comments=False, include_tables=False, favor_recall=True) or ""
        meta = trafilatura.extract_metadata(html)
        if meta:
            title, date = meta.title or "", meta.date or ""
    except Exception:
        pass
    if len(text) < 200:
        body = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
        body = re.sub(r"(?s)<[^>]+>", " ", body)
        text = normalize(body) if len(normalize(body)) > len(text) else text
    if not title:
        m = re.search(r"(?is)<title>(.*?)</title>", html)
        title = normalize(m.group(1)) if m else ""
    return {"url": page["url"], "domain": urlparse(page["url"]).netloc.replace("www.", ""),
            "title": title, "date": date, "text": text, "fetched": page.get("fetched", "")}
