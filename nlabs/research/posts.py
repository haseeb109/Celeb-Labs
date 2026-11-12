# research/posts.py — official social posts (X/Twitter etc.) as exact text (Rules S1–S3).
# X posts are read through the free oEmbed endpoint (no API key). Anything that fails
# is marked needs_manual; the owner can paste URLs/text into posts_manual.json.
from __future__ import annotations

import html as _html
import re

from .extract import normalize
from ..log import get_logger

log = get_logger()
OEMBED = "https://publish.twitter.com/oembed"
POST_RE = re.compile(r"https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/(\d+)")


def find_post_urls(texts: list[str]) -> list[str]:
    out = []
    for t in texts:
        for m in POST_RE.finditer(t or ""):
            u = f"https://x.com/{m.group(1)}/status/{m.group(2)}"
            if u not in out:
                out.append(u)
    return out


def parse_oembed(d: dict, url: str) -> dict:
    """oEmbed html looks like <blockquote><p>TEXT</p>&mdash; Name (@handle) <a>Date</a></blockquote>."""
    h = d.get("html", "")
    pm = re.search(r"<p[^>]*>(.*?)</p>", h, re.S)
    text = pm.group(1) if pm else ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<a[^>]*>(.*?)</a>", r"\1", text, flags=re.S)
    text = _html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
    dm = re.findall(r"<a[^>]*>([^<]+)</a>\s*</blockquote>", h)
    m = POST_RE.search(url)
    return {"type": "post", "platform": "X", "url": url, "author": d.get("author_name", ""),
            "handle": m.group(1) if m else d.get("author_url", "").rstrip("/").split("/")[-1],
            "text": text, "date": dm[-1] if dm else "", "verified_official": False}


def fetch_x_post(url: str, client=None) -> dict:
    from ..util import http_client
    own = client is None
    client = client or http_client(timeout=15)
    try:
        r = client.get(OEMBED, params={"url": url, "omit_script": 1, "dnt": "true"})
        if r.status_code != 200:
            return {"url": url, "needs_manual": True, "reason": f"oEmbed HTTP {r.status_code}"}
        return parse_oembed(r.json(), url)
    except Exception as e:
        return {"url": url, "needs_manual": True, "reason": f"oEmbed failed: {type(e).__name__}"}
    finally:
        if own:
            client.close()


def is_official_handle(handle: str, allow: dict) -> bool:
    h = handle.lower().lstrip("@")
    for ent in allow.values() if isinstance(allow, dict) else []:
        if isinstance(ent, dict) and h in [x.lower() for x in ent.get("x", [])]:
            return True
    return False


def split_statement(text: str, max_chars: int = 220) -> list[str]:
    """Split long statements into 2–3 cards on sentence boundaries (S1)."""
    text = normalize(text)
    if len(text) <= max_chars:
        return [text]
    sents = re.split(r"(?<=[.!?])\s+", text)
    cards, cur = [], ""
    for s in sents:
        if cur and len(cur) + 1 + len(s) > max_chars:
            cards.append(cur); cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        cards.append(cur)
    if len(cards) > 3:  # keep the first three cards only; rest is narrated
        cards = cards[:3]
    return cards
