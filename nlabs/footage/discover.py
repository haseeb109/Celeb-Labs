# footage/discover.py — find candidate videos with yt-dlp (metadata only, no download).
# ytsearchN per brain query + searches inside every Tier A channel; then full metadata
# (-J equivalent) for survivors: license, subtitles, formats. Blocklist applied early (F7).
from __future__ import annotations

import random
import time

from ..log import get_logger
from ..paths import cache_dir
from ..util import sha1, read_json, write_json

log = get_logger()


class _Quiet:
    def debug(self, m): pass
    def info(self, m): pass
    def warning(self, m): pass
    def error(self, m): pass


class BotCheck(RuntimeError):
    """YouTube asked to 'confirm you're not a bot' (cloud/VPN IP or rate limit)."""


def _ydl(cfg, extra=None):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True,
            "socket_timeout": 20, "extractor_retries": 2, "logger": _Quiet()}
    if cfg.get("cookies_file"):
        opts["cookiefile"] = cfg.get("cookies_file")
    opts.update(extra or {})
    return yt_dlp.YoutubeDL(opts)


def polite_sleep(cfg):
    lo, hi = (cfg.get("yt_dlp_sleep") or [2, 5])[:2]
    time.sleep(random.uniform(lo, hi))


def search(cfg, query: str, n: int = 15) -> list[dict]:
    p = cache_dir("search") / f"yt_{sha1(query, n)}.json"
    c = read_json(p)
    if c and time.time() - c["t"] < 24 * 3600:
        return c["entries"]
    with _ydl(cfg, {"extract_flat": "in_playlist"}) as y:
        info = y.extract_info(f"ytsearch{n}:{query}", download=False)
    entries = [{k: e.get(k) for k in ("id", "title", "channel", "channel_id", "duration", "view_count",
                                       "description", "url")} for e in info.get("entries", []) if e]
    write_json(p, {"t": time.time(), "entries": entries})
    return entries


def channel_search(cfg, channel_id: str, query: str, n: int = 10) -> list[dict]:
    url = f"https://www.youtube.com/channel/{channel_id}/search?query={query}"
    try:
        with _ydl(cfg, {"extract_flat": "in_playlist", "playlistend": n}) as y:
            info = y.extract_info(url, download=False)
        return [{k: e.get(k) for k in ("id", "title", "channel", "channel_id", "duration")} |
                {"channel": e.get("channel") or info.get("channel"), "channel_id": e.get("channel_id") or channel_id}
                for e in (info.get("entries") or [])[:n] if e]
    except Exception as e:
        log.info(f"channel search failed {channel_id}: {type(e).__name__}")
        return []


def full_info(cfg, video_id: str) -> dict | None:
    p = cache_dir("downloads") / f"info_{video_id}.json"
    c = read_json(p)
    if c and time.time() - c.get("_t", 0) < 6 * 3600:   # stream URLs expire, so short cache
        return c
    try:
        with _ydl(cfg) as y:
            info = y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        keep = {k: info.get(k) for k in ("id", "title", "channel", "channel_id", "channel_follower_count",
                                          "duration", "upload_date", "license", "view_count", "description",
                                          "categories", "width", "height", "language", "webpage_url")}
        keep["description"] = (keep.get("description") or "")[:1500]
        keep["subtitles"] = {k: v for k, v in (info.get("subtitles") or {}).items() if k.startswith("en")}
        keep["automatic_captions"] = {k: v for k, v in (info.get("automatic_captions") or {}).items()
                                      if k in ("en", "en-orig", "en-US")}
        keep["formats"] = [{k: f.get(k) for k in ("format_id", "ext", "height", "width", "vcodec", "acodec", "url",
                                                  "protocol", "http_headers", "tbr", "fps")}
                           for f in info.get("formats", []) if f.get("url")]
        keep["_t"] = time.time()
        write_json(p, keep)
        return keep
    except Exception as e:
        if "not a bot" in str(e) or "Sign in to confirm" in str(e):
            raise BotCheck(str(e)[:200])
        log.warning(f"metadata failed {video_id}: {type(e).__name__}: {str(e)[:160]}")
        return None


def relevance(entry: dict, keywords: list[str], subject: str) -> float:
    text = f"{entry.get('title', '')} {entry.get('description', '') or ''}".lower()
    s = 0.0
    if subject and subject.lower() in text:
        s += 2.0
    for p in subject.lower().split():
        if len(p) > 2 and p in text:
            s += 0.5
    s += sum(0.3 for k in keywords if k and k.lower() in text)
    return s


def filter_entries(entries, blocklist, seen_titles: set, min_d=30, max_d=4 * 3600):
    out, rejected = [], []
    for e in entries:
        reason = blocklist.check(e.get("channel") or "", e.get("channel_id") or "") or \
            blocklist.title_reupload(e.get("title") or "")
        d = e.get("duration") or 0
        if reason:
            rejected.append((e, reason)); continue
        if d and not (min_d <= d <= max_d):
            rejected.append((e, f"duration {d}s outside 30s–4h")); continue
        key = ((e.get("title") or "").lower()[:50], round(d / 5) if d else 0)
        if key in seen_titles:
            rejected.append((e, "duplicate re-upload")); continue
        seen_titles.add(key)
        out.append(e)
    return out, rejected
