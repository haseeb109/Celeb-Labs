# footage/soundbites.py — real-audio quotes ≤5.0 s (F2) cut on word boundaries.
# Finds ledger quotes (or key phrases) in subtitle words, pads 0.12 s, never exceeds
# MAX_CLIP_SECONDS. Each soundbite keeps its exact words for the on-screen caption.
from __future__ import annotations

import re

from ..constants import MAX_CLIP_SECONDS
from ..research.extract import normalize

PAD = 0.12


def _tok(s):
    return [re.sub(r"[^\w']", "", w.lower()) for w in normalize(s).split() if re.sub(r"[^\w']", "", w)]


def find_phrase(words: list[dict], phrase: str) -> tuple[int, int] | None:
    target = _tok(phrase)
    toks = [re.sub(r"[^\w']", "", w["w"].lower()) for w in words]
    n = len(target)
    if n < 3:
        return None
    for i in range(len(toks) - n + 1):
        if toks[i:i + n] == target:
            return i, i + n - 1
    return None


def cut_soundbite(words: list[dict], i0: int, i1: int, max_s: float = MAX_CLIP_SECONDS) -> dict | None:
    """Shrink from the end until it fits under the cap, on word boundaries."""
    while i1 >= i0:
        start = max(0.0, words[i0]["t"] - PAD)
        end = words[i1]["end"] + PAD
        if end - start <= max_s:
            text = " ".join(w["w"] for w in words[i0:i1 + 1])
            return {"start": round(start, 2), "end": round(end, 2), "text": text, "duration": round(end - start, 2)}
        i1 -= 1
    return None


def find_soundbites(words: list[dict], quotes: list[str], max_s: float = MAX_CLIP_SECONDS) -> list[dict]:
    out = []
    for q in quotes:
        for sent in re.split(r"(?<=[.!?])\s+", q):
            hit = find_phrase(words, sent)
            if hit:
                sb = cut_soundbite(words, hit[0], hit[1], max_s)
                if sb:
                    sb["quote"] = q
                    out.append(sb)
    return out
