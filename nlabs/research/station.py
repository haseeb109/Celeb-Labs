# research/station.py — Station 1: build queries, search, fetch, extract, extract facts.
# Brain passes: research_queries, extract_facts. Code: dedupe, robots, verify quotes,
# decide status. Writes fact_ledger.json + research_report.md (P1 resumable).
from __future__ import annotations

import json
import datetime as _dt

from ..brain import run_pass, NeedsManual, BrainError
from ..log import get_logger
from ..util import write_json, read_json
from .search import get_search, dedupe, SearchUnavailable, Hit
from .fetch import fetch, Skipped
from .extract import extract
from .ledger import Ledger, domain

log = get_logger()


def load_prompt(cfg, name: str) -> str:
    p = cfg.prompt_path(name)
    return p.read_text(encoding="utf-8") if p.exists() else ""


def fallback_queries(topic: str) -> list[dict]:
    return [{"q": q, "latest": latest} for q, latest in [
        (topic, True), (f"{topic} latest update", True), (f"{topic} official statement", True),
        (f"{topic} press release", True), (f"{topic} reaction", True), (f"{topic} timeline", False),
        (f"{topic} background", False), (f"{topic} site:x.com", True)]]


def validate_queries(d) -> list[str]:
    if not isinstance(d, dict) or not isinstance(d.get("queries"), list):
        return ['Expected {"queries":[{"q":"...","latest":true}, ...]}']
    errs = []
    if not 8 <= len(d["queries"]) <= 15:
        errs.append(f"Need 8-15 queries, got {len(d['queries'])}")
    for i, q in enumerate(d["queries"]):
        if not isinstance(q, dict) or not q.get("q"):
            errs.append(f"queries[{i}] needs a non-empty 'q'")
    return errs


def validate_facts(d) -> list[str]:
    if not isinstance(d, dict) or not isinstance(d.get("facts"), list):
        return ['Expected {"facts":[...]}']
    errs = []
    for i, f in enumerate(d["facts"]):
        if not f.get("text"):
            errs.append(f"facts[{i}] missing text")
        if not f.get("sources"):
            errs.append(f"facts[{i}] needs sources[] with url")
        if f.get("status") and f["status"] not in ("confirmed", "reported", "alleged", "denied", "unknown"):
            errs.append(f"facts[{i}] bad status {f['status']}")
    return errs


def run_research(topic: str, cfg, rp, brain, usage, search=None, primary_domains: set[str] | None = None,
                 fetcher=None) -> Ledger:
    if rp.is_done("research"):
        log.info("research: already done (resume)")
        return Ledger.from_json(read_json(rp.o("fact_ledger.json")))
    report = {"topic": topic, "queries": [], "pages": [], "skipped": [], "errors": []}
    primary_domains = set(primary_domains or [])
    import re as _re
    for w in _re.findall(r"\b[A-Z][A-Za-z0-9]{3,}\b", topic):   # company names in the topic: 'Nvidia' -> label:nvidia
        primary_domains.add("label:" + w.lower())
    official = read_json(cfg.style_dir.parent.parent / "official_accounts.json", {}) or {}
    for ent in official.values() if isinstance(official, dict) else []:
        for d in (ent.get("domains", []) if isinstance(ent, dict) else []):
            primary_domains.add(d)

    # 1. queries
    try:
        q = run_pass(brain, "research_queries", [
            {"role": "system", "content": load_prompt(cfg, "research.md")},
            {"role": "user", "content": json.dumps({"topic": topic, "today": _dt.date.today().isoformat()})}],
            validate_queries, cfg.get("brain_attempts", 3), cfg.get("max_repair_rounds", 3), 1500)
        queries = q["queries"]
    except NeedsManual:
        raise
    except Exception as e:
        log.warning(f"research_queries brain pass failed ({e}); using template queries")
        report["errors"].append(f"research_queries: {e}")
        queries = fallback_queries(topic)
    report["queries"] = queries

    # 2. search
    hits: list[Hit] = []
    try:
        s = search or get_search(cfg, usage)
        for qq in queries:
            try:
                hits += s.search(qq["q"], cfg.get("recency_hours", 72) if qq.get("latest") else None, 10)
            except Exception as e:
                report["errors"].append(f"search '{qq['q']}': {e}")
    except SearchUnavailable as e:
        report["errors"].append(str(e))
        log.error(str(e))
    hits = dedupe(hits)

    # 3. fetch + extract
    pages: dict[str, dict] = {}
    for h in hits:
        if len(pages) >= cfg.get("max_pages", 25):
            break
        try:
            pg = (fetcher or fetch)(h.url)
            ex = extract(pg)
            if len(ex["text"]) < 300 and fetcher is None:
                try:
                    from .fetch import fetch_playwright
                    ex = extract(fetch_playwright(h.url))
                except Exception:
                    pass
            if len(ex["text"]) >= 200:
                from .posts import find_post_urls
                ex["x_links"] = find_post_urls([pg.get("html", "")])
                ex["published"] = ex["date"] or h.published
                pages[h.url] = ex
        except Skipped as e:
            report["skipped"].append({"url": h.url, "reason": str(e)})
    report["pages"] = [{"url": u, "title": p["title"], "domain": p["domain"]} for u, p in pages.items()]

    # 4. extract facts
    ledger = Ledger(meta={"topic": topic})
    texts = {u: p["text"] for u, p in pages.items()}
    if pages:
        batch, size = [], 0
        batches = []
        for u, p in pages.items():
            chunk = {"url": u, "outlet": p["domain"], "title": p["title"], "published": p["published"],
                     "text": p["text"][:9000]}
            if size + len(chunk["text"]) > 30000 and batch:
                batches.append(batch); batch, size = [], 0
            batch.append(chunk); size += len(chunk["text"])
        if batch:
            batches.append(batch)
        for b in batches:
            try:
                d = run_pass(brain, "extract_facts", [
                    {"role": "system", "content": load_prompt(cfg, "extract_facts.md")},
                    {"role": "user", "content": json.dumps({"topic": topic, "pages": b})}],
                    validate_facts, cfg.get("brain_attempts", 3), cfg.get("max_repair_rounds", 3), 8000, 0.2)
                for f in d["facts"]:
                    for s_ in f.get("sources", []):
                        s_.setdefault("fetched", pages.get(s_.get("url"), {}).get("fetched", ""))
                        s_.setdefault("outlet", domain(s_.get("url", "")))
                    ledger.add(f, texts, primary_domains)
            except NeedsManual:
                raise
            except Exception as e:
                report["errors"].append(f"extract_facts: {e}")
    write_json(rp.o("fact_ledger.json"), ledger.to_json())
    write_report(rp, ledger, report)
    write_json(rp.w("research_raw.json"), report)
    write_json(rp.w("pages.json"), {u: p["text"] + "\n" + " ".join(p.get("x_links", [])) for u, p in pages.items()})
    if not ledger.facts:
        log.error("research produced 0 facts — see research_report.md")
    else:
        rp.mark_done("research")
    return ledger


def write_report(rp, ledger: Ledger, report: dict):
    L = [f"# Research report — {report['topic']}", "", f"Researched at {ledger.researched_at} {ledger.tz}", ""]
    L += ["## Timeline", "", "| Date | Fact | Status |", "|---|---|---|"]
    for f in sorted(ledger.facts, key=lambda f: f.get("date") or ""):
        L.append(f"| {f.get('date', '')} | {f['text'][:120]} ({f['fact_id']}) | {f['status']} |")
    for st in ("confirmed", "reported", "alleged", "denied"):
        L += ["", f"## {st.title()}", ""] + [f"- {f['fact_id']}: {f['text']}" for f in ledger.facts if f["status"] == st]
    L += ["", "## Official statements & posts", ""]
    L += [f"- {f['fact_id']} ({f.get('type')}): \"{(f.get('quote') or f['text'])[:160]}\"" for f in ledger.facts
          if f.get("type") in ("statement", "post")] or ["- none found"]
    L += ["", "## Quotes dropped (not verbatim in source)", ""] + \
         [f"- {d['fact_id']}: {d['quote'][:120]}" for d in ledger.dropped_quotes] + ["", "## Sources used", ""]
    L += [f"- {p['domain']}: {p['url']}" for p in report["pages"]]
    L += ["", "## Skipped sources", ""] + [f"- {s['url']} — {s['reason']}" for s in report["skipped"]]
    L += ["", "## Errors", ""] + [f"- {e}" for e in report["errors"]]
    rp.o("research_report.md").write_text("\n".join(L), encoding="utf-8")
