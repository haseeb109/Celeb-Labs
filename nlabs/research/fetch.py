# research/fetch.py — polite page fetching with a 24 h cache.
# Respects robots.txt and HTTP blocks: on 401/403/451/robots-disallow it SKIPS and
# logs the reason (never bypasses). Returns raw HTML; extract.py turns it into text.
from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlparse

from ..paths import cache_dir
from ..util import sha1, read_json, write_json, BROWSER_UA
from ..log import get_logger

log = get_logger()
TTL = 24 * 3600
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


class Skipped(RuntimeError):
    pass


def robots_ok(url: str, client) -> bool:
    u = urlparse(url)
    base = f"{u.scheme}://{u.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = client.get(base + "/robots.txt", timeout=8)
            if r.status_code >= 400:
                _robots[base] = None
            else:
                rp.parse(r.text.splitlines())
                _robots[base] = rp
        except Exception:
            _robots[base] = None
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(BROWSER_UA, url) or rp.can_fetch("*", url)


def fetch(url: str, client=None) -> dict:
    """Return {"url","html","status","fetched"} or raise Skipped(reason)."""
    p = cache_dir("pages") / f"{sha1(url)}.json"
    c = read_json(p)
    if c and time.time() - c["t"] < TTL:
        if c.get("skipped"):
            raise Skipped(c["skipped"])
        return c["page"]
    from ..util import http_client
    own = client is None
    client = client or http_client()
    try:
        if not robots_ok(url, client):
            write_json(p, {"t": time.time(), "skipped": "robots.txt disallows"})
            raise Skipped("robots.txt disallows")
        r = client.get(url)
        if r.status_code in (401, 403, 451) or r.status_code >= 400:
            write_json(p, {"t": time.time(), "skipped": f"HTTP {r.status_code}"})
            raise Skipped(f"HTTP {r.status_code}")
        page = {"url": str(r.url), "html": r.text, "status": r.status_code,
                "fetched": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        write_json(p, {"t": time.time(), "page": page})
        return page
    except Skipped:
        raise
    except Exception as e:
        raise Skipped(f"network: {type(e).__name__}: {str(e)[:120]}")
    finally:
        if own:
            client.close()


def fetch_playwright(url: str) -> dict:
    """Fallback for JS-heavy pages (headless Chromium)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(user_agent=BROWSER_UA)
        resp = pg.goto(url, timeout=30000, wait_until="domcontentloaded")
        if resp and resp.status in (401, 403, 451):
            b.close()
            raise Skipped(f"HTTP {resp.status}")
        pg.wait_for_timeout(1500)
        html = pg.content()
        b.close()
    return {"url": url, "html": html, "status": 200, "fetched": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
