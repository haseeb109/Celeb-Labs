# footage/subtitles.py — subtitle mining: word-level timestamps from YouTube captions.
# Parses json3 (word offsets) or VTT (cue level, words spread evenly). Used to find
# the exact seconds where the subject is named/speaking or a ledger quote is said.
from __future__ import annotations

import re

from ..paths import cache_dir
from ..util import sha1


def pick_track(info: dict) -> dict | None:
    for src in ("subtitles", "automatic_captions"):
        for lang in ("en", "en-US", "en-orig"):
            for t in (info.get(src) or {}).get(lang, []) or []:
                if t.get("ext") == "json3":
                    return t | {"kind": src}
        for lang, tracks in (info.get(src) or {}).items():
            for t in tracks or []:
                if t.get("ext") in ("json3", "vtt"):
                    return t | {"kind": src}
    return None


def parse_json3(d: dict) -> list[dict]:
    words = []
    for ev in d.get("events", []):
        t0 = ev.get("tStartMs", 0)
        for s in ev.get("segs", []) or []:
            w = (s.get("utf8") or "").strip()
            if not w or w == "\n":
                continue
            for i, part in enumerate(w.split()):
                words.append({"t": (t0 + s.get("tOffsetMs", 0)) / 1000 + i * 0.05, "w": part})
    for i, w in enumerate(words):
        w["end"] = words[i + 1]["t"] if i + 1 < len(words) else w["t"] + 0.4
        w["end"] = min(w["end"], w["t"] + 1.2)
    return words


def _ts(s):
    h, m, rest = s.split(":") if s.count(":") == 2 else ("0", *s.split(":"))
    return int(h) * 3600 + int(m) * 60 + float(rest.replace(",", "."))


def parse_vtt(text: str) -> list[dict]:
    words = []
    for m in re.finditer(r"([\d:.,]+)\s+-->\s+([\d:.,]+)[^\n]*\n(.*?)(?:\n\n|\Z)", text, re.S):
        a, b = _ts(m.group(1)), _ts(m.group(2))
        body = re.sub(r"<[^>]+>", "", m.group(3)).split()
        for i, w in enumerate(body):
            t = a + (b - a) * i / max(len(body), 1)
            words.append({"t": t, "end": t + (b - a) / max(len(body), 1), "w": w})
    return words


def fetch_words(info: dict, client=None) -> list[dict]:
    t = pick_track(info)
    if not t:
        return []
    p = cache_dir("subs") / f"{info['id']}_{sha1(t['url'])[:8]}.{t['ext']}"
    if not p.exists():
        from ..util import http_client
        own = client is None
        client = client or http_client()
        try:
            r = client.get(t["url"])
            if r.status_code != 200:
                return []
            p.write_bytes(r.content)
        finally:
            if own:
                client.close()
    raw = p.read_text(encoding="utf-8", errors="ignore")
    if t["ext"] == "json3":
        import json
        return parse_json3(json.loads(raw))
    return parse_vtt(raw)


def find_mentions(words: list[dict], terms: list[str]) -> list[float]:
    terms = [t.lower() for t in terms if t]
    hits = []
    for i, w in enumerate(words):
        low = re.sub(r"[^\w']", "", w["w"].lower())
        if any(low == t or (len(t) > 4 and low.startswith(t)) for t in terms):
            if not hits or w["t"] - hits[-1] > 15:
                hits.append(w["t"])
    return hits
