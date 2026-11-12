# research/ledger.py — the fact ledger (Rule L1) with code-decided status and verified quotes.
# The brain PROPOSES facts; this module decides status (S/L rules) and drops any quote
# that is not found verbatim in a fetched page (S3). Saved as fact_ledger.json.
from __future__ import annotations

import datetime as _dt
import re
from urllib.parse import urlparse

from .extract import normalize

REPUTABLE = {
    "reuters.com", "apnews.com", "bloomberg.com", "wsj.com", "nytimes.com", "washingtonpost.com",
    "ft.com", "theguardian.com", "bbc.com", "bbc.co.uk", "cnbc.com", "cnn.com", "nbcnews.com",
    "cbsnews.com", "abcnews.go.com", "npr.org", "axios.com", "politico.com", "theverge.com",
    "techcrunch.com", "economist.com", "fortune.com", "forbes.com", "businessinsider.com",
    "latimes.com", "usatoday.com", "aljazeera.com", "theinformation.com", "semafor.com",
    "marketwatch.com", "barrons.com", "arstechnica.com", "wired.com", "time.com", "pbs.org",
}
STRENGTH = {"confirmed": 4, "reported": 3, "alleged": 2, "denied": 1, "unknown": 0}
ALLEGE_RE = re.compile(r"\balleg\w*|\baccus\w*|\bclaim(s|ed)? that\b", re.I)


def domain(url: str) -> str:
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def root_domain(d: str) -> str:
    parts = d.split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "go") and len(parts[-1]) <= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_primary(url: str, primary_domains: set[str]) -> bool:
    """Primary = government site, an allow-listed official domain, or a domain whose root label is an
    entity named in the topic (entries written as 'label:nvidia' match nvidia.com, nvidianews.nvidia.com)."""
    d = domain(url)
    if d.endswith(".gov") or ".gov." in d or d.endswith(".mil"):
        return True
    root_label = root_domain(d).split(".")[0]
    for p in primary_domains:
        if p.startswith("label:"):
            if root_label == p[6:]:
                return True
        elif d == p or d.endswith("." + p):
            return True
    return False


def compute_status(fact: dict, primary_domains: set[str]) -> str:
    """Status logic (Section 5.1 step 5), decided in code."""
    srcs = fact.get("sources", [])
    if fact.get("type") in ("post", "statement") and fact.get("verified_official"):
        computed = "confirmed"
    elif any(is_primary(s["url"], primary_domains) for s in srcs):
        computed = "confirmed"
    else:
        reputable = {root_domain(domain(s["url"])) for s in srcs if root_domain(domain(s["url"])) in REPUTABLE}
        others = {root_domain(domain(s["url"])) for s in srcs}
        if len(reputable) >= 2:
            computed = "confirmed"
        elif reputable or others:
            computed = "reported"
        else:
            computed = "unknown"
    proposed = (fact.get("status") or computed).lower()
    if proposed not in STRENGTH:
        proposed = computed
    if ALLEGE_RE.search(fact.get("text", "")) and computed != "confirmed":
        proposed = "alleged"
    if proposed == "denied":
        return "denied"
    # never let the brain make a fact STRONGER than the evidence
    return proposed if STRENGTH[proposed] <= STRENGTH[computed] else computed


def verify_quote(quote: str, page_texts: list[str]) -> bool:
    q = normalize(quote).strip(' "\'')
    if len(q) < 8:
        return False
    return any(q.lower() in normalize(t).lower() for t in page_texts)


class Ledger:
    def __init__(self, facts: list[dict] | None = None, researched_at: str | None = None, tz: str = "UTC",
                 meta: dict | None = None):
        self.facts = facts or []
        self.researched_at = researched_at or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
        self.tz = tz
        self.meta = meta or {}
        self.dropped_quotes: list[dict] = []

    @classmethod
    def from_json(cls, d: dict) -> "Ledger":
        lg = cls(d.get("facts", []), d.get("researched_at"), d.get("timezone", "UTC"), d.get("meta", {}))
        lg.dropped_quotes = d.get("dropped_quotes", [])
        return lg

    def to_json(self) -> dict:
        return {"researched_at": self.researched_at, "timezone": self.tz, "meta": self.meta,
                "facts": self.facts, "dropped_quotes": self.dropped_quotes}

    def by_id(self) -> dict[str, dict]:
        return {f["fact_id"]: f for f in self.facts}

    def next_id(self) -> str:
        nums = [int(f["fact_id"][1:]) for f in self.facts if re.fullmatch(r"F\d+", f.get("fact_id", ""))]
        return f"F{(max(nums) + 1 if nums else 1):03d}"

    def add(self, fact: dict, pages_by_url: dict[str, str], primary_domains: set[str]) -> dict | None:
        """Add a proposed fact after code checks. Returns the stored fact, or None if rejected."""
        fact = dict(fact)
        fact.setdefault("fact_id", self.next_id())
        if fact["fact_id"] in self.by_id():
            fact["fact_id"] = self.next_id()
        fact.setdefault("sources", [])
        fact.setdefault("people", [])
        fact.setdefault("denials", [])
        fact.setdefault("private_people", [])
        fact.setdefault("type", "fact")
        # sources must be pages we actually fetched (no invented URLs)
        fact["sources"] = [s for s in fact["sources"] if s.get("url") in pages_by_url or s.get("verified")]
        if not fact["sources"]:
            return None
        if fact.get("quote"):
            texts = [pages_by_url.get(s["url"], "") for s in fact["sources"]]
            if not verify_quote(fact["quote"], texts):
                self.dropped_quotes.append({"fact_id": fact["fact_id"], "quote": fact["quote"],
                                            "reason": "not found verbatim in fetched source text"})
                fact["quote"] = None
        fact["status"] = compute_status(fact, primary_domains)
        self.facts.append(fact)
        return fact

    def private_names(self) -> set[str]:
        out = set()
        for f in self.facts:
            for n in f.get("private_people", []):
                out.add(n)
        return out

    def quotes(self) -> list[str]:
        return [f["quote"] for f in self.facts if f.get("quote")]
