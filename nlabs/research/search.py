# research/search.py — web search provider interface: SearXNG, Brave, Tavily.
# `get_search(cfg)` picks by config ("auto" = SearXNG if URL set, else Brave, else Tavily).
# Results are cached 24 h in cache/search/ and de-duplicated by URL.
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

from ..paths import cache_dir
from ..util import sha1, read_json, write_json
from ..log import get_logger

log = get_logger()
TTL = 24 * 3600


@dataclass
class Hit:
    url: str
    title: str = ""
    snippet: str = ""
    published: str = ""
    source: str = ""


class SearchUnavailable(RuntimeError):
    pass


class Search:
    name = "base"

    def __init__(self, cfg, usage=None):
        self.cfg, self.usage = cfg, usage

    def _query(self, q: str, recency_hours: int | None, n: int) -> list[Hit]:
        raise NotImplementedError

    def search(self, q: str, recency_hours: int | None = None, n: int = 10) -> list[Hit]:
        key = sha1(self.name, q, recency_hours, n)
        p = cache_dir("search") / f"{key}.json"
        c = read_json(p)
        if c and time.time() - c["t"] < TTL:
            return [Hit(**h) for h in c["hits"]]
        hits = self._query(q, recency_hours, n)
        if self.usage:
            self.usage.search(self.name)
        write_json(p, {"t": time.time(), "q": q, "hits": [asdict(h) for h in hits]})
        return hits


class SearXNG(Search):
    name = "searxng"

    def _query(self, q, recency_hours, n):
        import httpx
        params = {"q": q, "format": "json"}
        if recency_hours:
            params["time_range"] = "day" if recency_hours <= 24 else ("week" if recency_hours <= 168 else "month")
        r = httpx.get(self.cfg.get("searxng_url").rstrip("/") + "/search", params=params, timeout=20)
        r.raise_for_status()
        return [Hit(url=x["url"], title=x.get("title", ""), snippet=x.get("content", ""),
                    published=x.get("publishedDate") or "", source="searxng")
                for x in r.json().get("results", [])[:n]]


class Brave(Search):
    name = "brave"

    def _query(self, q, recency_hours, n):
        import httpx
        params = {"q": q, "count": min(n, 20)}
        if recency_hours:
            params["freshness"] = "pd" if recency_hours <= 24 else ("pw" if recency_hours <= 168 else "pm")
        r = httpx.get("https://api.search.brave.com/res/v1/web/search", params=params, timeout=20,
                      headers={"X-Subscription-Token": self.cfg.keys["brave"], "Accept": "application/json"})
        r.raise_for_status()
        return [Hit(url=x["url"], title=x.get("title", ""), snippet=x.get("description", ""),
                    published=x.get("page_age") or x.get("age") or "", source="brave")
                for x in r.json().get("web", {}).get("results", [])[:n]]


class Tavily(Search):
    name = "tavily"

    def _query(self, q, recency_hours, n):
        import httpx
        body = {"api_key": self.cfg.keys["tavily"], "query": q, "max_results": min(n, 20),
                "topic": "news" if recency_hours else "general"}
        if recency_hours:
            body["days"] = max(1, recency_hours // 24)
        r = httpx.post("https://api.tavily.com/search", json=body, timeout=30)
        r.raise_for_status()
        return [Hit(url=x["url"], title=x.get("title", ""), snippet=x.get("content", ""),
                    published=x.get("published_date") or "", source="tavily")
                for x in r.json().get("results", [])[:n]]


class OfflineSearch(Search):
    """Fixture search for tests: returns canned hits by query substring."""
    name = "offline"

    def __init__(self, cfg=None, hits: list[Hit] | None = None, usage=None):
        super().__init__(cfg, usage)
        self.hits = hits or []

    def search(self, q, recency_hours=None, n=10):
        return self.hits[:n]


def get_search(cfg, usage=None) -> Search:
    want = (cfg.get("search_provider") or "auto").lower()
    if want in ("searxng", "auto") and cfg.get("searxng_url"):
        return SearXNG(cfg, usage)
    if want in ("brave", "auto") and cfg.keys.get("brave"):
        return Brave(cfg, usage)
    if want in ("tavily", "auto") and cfg.keys.get("tavily"):
        return Tavily(cfg, usage)
    raise SearchUnavailable("No search provider configured: set searxng_url in config.json, or add a key "
                            "to ~/.config/umf/brave.env or tavily.env")


def dedupe(hits: list[Hit]) -> list[Hit]:
    seen, out = set(), []
    for h in hits:
        k = h.url.split("#")[0].rstrip("/").replace("://www.", "://")
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out
