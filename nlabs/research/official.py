# research/official.py — Station 2: official statements & posts → ledger entries + card specs.
# Verification signals: handle on official_accounts.json allow-list, or linked from an
# official domain. Unverified → not presented as official. Missing → explicit "no comment" fact.
from __future__ import annotations

from ..log import get_logger
from ..util import read_json, write_json
from ..paths import ROOT
from .ledger import Ledger, is_primary, domain
from .posts import find_post_urls, fetch_x_post, is_official_handle, split_statement
from ..constants import STATEMENT_CARD_MAX_CHARS

log = get_logger()


def run_official(topic: str, subject: str, ledger: Ledger, cfg, rp, raw_pages: dict[str, str] | None = None,
                 posts_file=None, fetcher=fetch_x_post) -> dict:
    if rp.is_done("official"):
        return read_json(rp.w("official.json"))
    allow = read_json(ROOT / "official_accounts.json", {}) or {}
    primary = {d for e in allow.values() if isinstance(e, dict) for d in e.get("domains", [])}
    raw_pages = raw_pages or {}
    manual = read_json(posts_file, []) if posts_file else []
    manual = manual if isinstance(manual, list) else manual.get("posts", [])
    needs_manual, cards = [], []

    urls = find_post_urls(list(raw_pages.values()))
    urls += [m["url"] for m in manual if m.get("url") and "status/" in m.get("url", "")]
    for u in dict.fromkeys(urls):
        post = next((m for m in manual if m.get("url") == u and m.get("text")), None)
        if post:
            post = {"type": "post", "platform": post.get("platform", "X"), "url": u, "author": post.get("author", ""),
                    "handle": post.get("handle", u.split("/")[3]), "text": post["text"], "date": post.get("date", ""),
                    "owner_supplied": True}
        else:
            post = fetcher(u)
        if post.get("needs_manual"):
            needs_manual.append(post)
            continue
        post["verified_official"] = is_official_handle(post["handle"], allow) or any(
            u in t and is_primary(pu, primary) for pu, t in raw_pages.items())
        if not post["verified_official"]:
            log.info(f"post {u} not from a verified official account — skipped as 'official'")
            continue
        f = ledger.add({"type": "post", "text": f"@{post['handle']} posted: {post['text'][:200]}",
                        "quote": post["text"], "people": [post["author"]], "date": post["date"],
                        "verified_official": True,
                        "sources": [{"url": u, "outlet": f"X / @{post['handle']}", "verified": True,
                                     "published": post["date"]}]},
                       {u: post["text"]}, primary)
        if f:
            cards.append({"kind": "post", "fact_id": f["fact_id"], "author": post["author"], "handle": post["handle"],
                          "verified": True, "date": post["date"], "text": post["text"],
                          "source_line": f"Source: X / @{post['handle']}"})
    # statements already in the ledger (from newsroom pages) → statement cards
    for f in ledger.facts:
        if f.get("type") == "statement" and f.get("quote"):
            parts = split_statement(f["quote"], STATEMENT_CARD_MAX_CHARS)
            for i, p in enumerate(parts):
                cards.append({"kind": "statement", "fact_id": f["fact_id"], "speaker": (f.get("people") or [""])[0],
                              "text": p, "part": i + 1, "parts": len(parts),
                              "source_line": "Source: " + (f["sources"][0].get("outlet") or domain(f["sources"][0]["url"]))})
    has_official = any(c for c in cards)
    if not has_official:
        nc = next((f for f in ledger.facts if f.get("type") == "no_comment"), None)
        if not nc:
            nc = {"fact_id": ledger.next_id(), "type": "no_comment", "status": "confirmed",
                  "text": f"{subject} has not publicly commented (no official statement found as of "
                          f"{ledger.researched_at} {ledger.tz}).", "sources": [], "people": [subject], "denials": []}
            ledger.facts.append(nc)
    out = {"cards": cards, "needs_manual": needs_manual, "has_official": has_official}
    write_json(rp.w("official.json"), out)
    write_json(rp.o("fact_ledger.json"), ledger.to_json())
    if needs_manual:
        log.warning(f"{len(needs_manual)} posts need manual text — add them to posts_manual.json and resume")
    rp.mark_done("official")
    return out
