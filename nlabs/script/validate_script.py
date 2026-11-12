# script/validate_script.py — the code validator for script.json (Section 5.5).
# Checks schema, word counts, fact_ids (L1), attribution (L2), exact quotes (S3),
# private names (L3), banned phrases, retention beats, official statements (S1), length.
from __future__ import annotations

import re

from ..research.extract import normalize

KINDS = {"vo", "soundbite", "post", "statement", "chapter", "title", "endscreen"}
RETENTION = {"hook", "open_loop", "comment_prompt", "recap", "teaser", "none"}
ATTRIBUTION_RE = re.compile(
    r"\b(according to|reportedly|reported(ly)?|reports?|said|says|told|wrote|writes|claims?|claimed|"
    r"alleg\w*|per |sources? (say|said)|it is reported|stated|announced|in (a|an|his|her|their) "
    r"(statement|post|email|filing|letter)|in (his|her|their) words)\b", re.I)
HYPO_RE = re.compile(r"\b(hypothetical(ly)?|estimate[sd]?|could|might|would|if )\b", re.I)
QUOTE_RE = re.compile(r"[\"“]([^\"”]{6,})[\"”]")
COLON_QUOTE_RE = re.compile(r"\b(?:said|wrote|writes|says|in (?:his|her|their) words)\s*:\s*(.+)$", re.I)
FACTUAL_HINT = re.compile(r"\b(\d|is|was|were|has|had|resign\w*|announc\w*|said|report\w*|confirm\w*|"
                          r"according|filed|sued|admit\w*|denied|shares?|stock|billion|million|percent)\b", re.I)


def words(t: str) -> int:
    return len(re.findall(r"\b[\w'’-]+\b", t))


def est_seconds(seg: dict, chars_per_sec: float, pacing: dict) -> float:
    k = seg["kind"]
    if k == "chapter":
        return pacing.get("chapter_card_s", 3.4)
    if k == "title":
        return pacing.get("title_s", 4.2)
    if k == "endscreen":
        return 6.0
    if k == "soundbite":
        return min(5.0, float(seg.get("duration") or 4.0)) + 0.3
    return pacing.get("lead", 0.1) + len(seg.get("text", "")) / chars_per_sec + pacing.get("tail", 0.4)


def quoted_strings(text: str) -> list[str]:
    out = [m.group(1) for m in QUOTE_RE.finditer(text)]
    m = COLON_QUOTE_RE.search(text)
    if m and not out:
        out.append(m.group(1))
    return out


def validate_script(script: dict, ledger, official_cards: list[dict] | None = None, target_s: float = 1200,
                    tolerance: float = 0.03, chars_per_sec: float = 15.0, pacing: dict | None = None,
                    banned: list[str] | None = None, retention_cfg: dict | None = None,
                    check_length: bool = True) -> list[str]:
    pacing = pacing or {}
    errs: list[str] = []
    if not isinstance(script, dict) or not isinstance(script.get("segments"), list):
        return ['script must be {"segments":[...]}']
    segs = script["segments"]
    facts = ledger.by_id()
    ledger_quotes = [normalize(q).lower().strip(' "\'') for q in ledger.quotes()]
    private = {n.lower() for n in ledger.private_names()}
    ids = set()
    for i, s in enumerate(segs):
        tag = f"segment {s.get('id', i)}"
        for key in ("id", "kind"):
            if key not in s:
                errs.append(f"{tag}: missing '{key}'")
        if s.get("id") in ids:
            errs.append(f"{tag}: duplicate id")
        ids.add(s.get("id"))
        k = s.get("kind")
        if k not in KINDS:
            errs.append(f"{tag}: kind must be one of {sorted(KINDS)}")
            continue
        if s.get("retention", "none") not in RETENTION:
            errs.append(f"{tag}: retention must be one of {sorted(RETENTION)}")
        text = s.get("text", "") or ""
        if k == "vo":
            n = words(text)
            if not 12 <= n <= 75:
                errs.append(f"{tag}: vo segments need 12-75 words (has {n})")
        for fid in s.get("fact_ids", []) or []:
            if fid not in facts:
                errs.append(f"{tag}: fact_id {fid} not in ledger")
        if k in ("vo", "soundbite", "post", "statement"):
            sents = [x for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
            factual = any(FACTUAL_HINT.search(x) for x in sents)
            is_framing = s.get("retention") in ("comment_prompt", "teaser", "open_loop") and not s.get("fact_ids")
            if factual and not s.get("fact_ids") and not is_framing and not s.get("opinion"):
                errs.append(f"{tag}: factual sentence(s) need at least one fact_id (L1)")
            if k in ("post", "statement", "soundbite") and not s.get("fact_ids"):
                errs.append(f"{tag}: {k} segments must reference the ledger fact they show")
            # L2 attribution for reported/alleged
            for fid in s.get("fact_ids", []) or []:
                f = facts.get(fid)
                if not f:
                    continue
                if f["status"] in ("reported", "alleged") and k == "vo" and not ATTRIBUTION_RE.search(text):
                    errs.append(f"{tag}: fact {fid} is '{f['status']}' — narration needs attribution "
                                f"('according to…', 'reportedly', 'X said') (L2)")
                if f.get("denials"):
                    all_text = " ".join(x.get("text", "") for x in segs).lower()
                    if not re.search(r"\bden(y|ies|ied|ial)\b", all_text):
                        errs.append(f"{tag}: fact {fid} has a denial in the ledger — the script must include it (L2)")
                if f.get("hypothetical") and not HYPO_RE.search(text):
                    errs.append(f"{tag}: fact {fid} is speculative — narrate it as hypothetical/estimate (L5)")
            # S3 verbatim quotes
            for q in quoted_strings(text):
                nq = normalize(q).lower().strip(' "\'.,')
                if len(nq) < 6:
                    continue
                if not any(nq in lq or lq in nq and len(lq) > 0.9 * len(nq) for lq in ledger_quotes):
                    errs.append(f'{tag}: quote "{q[:60]}" does not exactly match any ledger quote (S3)')
            # L3 private names
            low = text.lower()
            for name in private:
                parts = [name] + [p for p in name.split() if len(p) > 3]
                if any(re.search(r"\b" + re.escape(p) + r"\b", low) for p in parts):
                    errs.append(f"{tag}: names a private individual ('{name}') — describe by role instead (L3)")
            for b in banned or []:
                if b and b.lower() in low:
                    errs.append(f"{tag}: banned phrase '{b}'")
    # S1: every official card must appear
    used = {fid for s in segs for fid in (s.get("fact_ids") or [])}
    for c in official_cards or []:
        if c["fact_id"] not in used:
            errs.append(f"official {c['kind']} {c['fact_id']} must appear in the script (S1)")
    nc = [f for f in ledger.facts if f.get("type") == "no_comment"]
    if nc and not official_cards and nc[0]["fact_id"] not in used:
        errs.append(f"no official statement exists — the script must say so using fact {nc[0]['fact_id']} (S1)")
    # retention beats
    errs += check_retention(segs, chars_per_sec, pacing, retention_cfg or {}, target_s)
    # length
    if check_length:
        total = sum(est_seconds(s, chars_per_sec, pacing) for s in segs if s.get("kind") in KINDS)
        if abs(total - target_s) > tolerance * target_s:
            diff = target_s - total
            errs.append(f"runtime estimate {total:.0f}s vs target {target_s:.0f}s (±{tolerance * 100:.0f}%): "
                        f"{'add' if diff > 0 else 'remove'} about {abs(diff) * chars_per_sec:.0f} characters of "
                        f"whole segments (no filler)")
    return errs


def check_retention(segs, cps, pacing, rc, target_s) -> list[str]:
    errs, t = [], 0.0
    times = []
    for s in segs:
        times.append(t)
        t += est_seconds(s, cps, pacing) if s.get("kind") in KINDS else 0
    scale = target_s / 1200.0  # beats scale with video length
    def first(beat):
        for s, st in zip(segs, times):
            if s.get("retention") == beat:
                return st
        return None
    h = first("hook")
    if h is None or h > rc.get("hook_s", 15):
        errs.append(f"retention: a 'hook' segment must start in the first {rc.get('hook_s', 15)}s")
    tz = [st for s, st in zip(segs, times) if s.get("retention") in ("open_loop", "teaser")]
    if not tz or min(tz) > max(rc.get("teaser_by_min", 3) * 60 * scale, rc.get("hook_s", 15) + 15):
        errs.append("retention: need an 'open_loop'/'teaser' by minute "
                    f"{rc.get('teaser_by_min', 3) * scale:.1f}")
    cp = first("comment_prompt")
    if cp is None or cp > max((rc.get("comment_prompt_min", 7) + 1.5) * 60 * scale, 30):
        errs.append(f"retention: need a 'comment_prompt' around minute {rc.get('comment_prompt_min', 7) * scale:.1f}")
    elif not any(s.get("answers_comment_prompt") or (s.get("retention") == "comment_prompt" and st > 0.8 * t)
                 for s, st in zip(segs, times)):
        errs.append("retention: the comment prompt must be answered in the outro (mark a late segment "
                    "with answers_comment_prompt:true)")
    for frac in rc.get("recaps", [0.4, 0.7]):
        if not any(s.get("retention") == "recap" and abs(st - frac * t) < 0.12 * t for s, st in zip(segs, times)):
            errs.append(f"retention: need a 'recap' near {int(frac * 100)}% of runtime")
    chapters = {s.get("chapter") for s in segs if s.get("kind") == "vo" and s.get("chapter")}
    cards = {s.get("chapter") for s in segs if s.get("kind") == "chapter"}
    missing = sorted(c for c in chapters - cards if c)
    if missing:
        errs.append(f"retention: chapter card missing for chapters {missing}")
    return errs
