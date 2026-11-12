# footage/download.py — partial downloads only: pull 10–40 s windows straight from the
# stream URL with ffmpeg -ss (full download only for videos < 6 min). Includes the
# yt-dlp self-update (max once per 24 h) and the 403/bot-check fallback chain.
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from ..log import get_logger
from ..paths import cache_dir
from ..util import ffmpeg, sha1

log = get_logger()


def ensure_fresh_ytdlp(force: bool = False) -> str:
    stamp = cache_dir("downloads") / "ytdlp_updated"
    if not force and stamp.exists() and time.time() - stamp.stat().st_mtime < 24 * 3600:
        return "fresh"
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp[default]"],
                       check=True, timeout=300, capture_output=True)
        stamp.write_text(time.ctime())
        return "updated"
    except Exception as e:
        try:  # uv-managed venvs have no pip
            subprocess.run(["uv", "pip", "install", "--python", sys.executable, "-q", "-U", "yt-dlp[default]"],
                           check=True, timeout=300, capture_output=True)
            stamp.write_text(time.ctime())
            return "updated"
        except Exception:
            log.warning(f"yt-dlp update failed: {e}")
            return "failed"


def pick_formats(info: dict, max_h: int = 1080, skip: set | None = None):
    skip = skip or set()
    fmts = [f for f in info.get("formats", []) if f.get("format_id") not in skip]
    vids = [f for f in fmts if f.get("vcodec") not in (None, "none") and (f.get("height") or 0) <= max_h
            and f.get("protocol", "https").startswith("http")]
    # prefer mp4/avc, then height
    vids.sort(key=lambda f: ((f.get("ext") == "mp4"), str(f.get("vcodec", "")).startswith("avc"),
                             f.get("height") or 0), reverse=True)
    v = vids[0] if vids else None
    if v and v.get("acodec") not in (None, "none"):
        return v, None
    auds = [f for f in fmts if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")
            and f.get("protocol", "https").startswith("http")]
    auds.sort(key=lambda f: ((f.get("ext") == "m4a"), f.get("tbr") or 0), reverse=True)
    return v, (auds[0] if auds else None)


def _hdr(f):
    h = f.get("http_headers") or {}
    return ["-headers", "".join(f"{k}: {v}\r\n" for k, v in h.items())] if h else []


def download_window(info: dict, start: float, length: float, out_dir: Path, cfg=None) -> Path | None:
    """Window [start, start+length] → mp4 (H.264/AAC, original size ≤1080p). Cached."""
    start = max(0.0, start)
    out = out_dir / f"{info['id']}_{int(start * 10):06d}_{int(length)}.mp4"
    cached = cache_dir("downloads") / out.name
    if cached.exists() and cached.stat().st_size > 10000:
        return cached
    skip: set = set()
    for attempt in range(4):
        v, a = pick_formats(info, skip=skip)
        if not v:
            return None
        args = ["-ss", f"{start:.2f}"] + _hdr(v) + ["-i", v["url"]]
        if a:
            args += ["-ss", f"{start:.2f}"] + _hdr(a) + ["-i", a["url"], "-map", "0:v:0", "-map", "1:a:0"]
        args += ["-t", f"{length:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                 "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(cached)]
        try:
            ffmpeg(args, timeout=240)
            if cached.exists() and cached.stat().st_size > 10000:
                return cached
        except Exception as e:
            msg = str(e)
            log.warning(f"window {info['id']}@{start:.0f}s attempt {attempt + 1} failed: {msg[-160:]}")
            if "403" in msg and attempt == 0 and cfg is not None and cfg.get("yt_dlp_auto_update", True):
                ensure_fresh_ytdlp(force=True)        # chain: update → retry/sleep → other format → skip
            time.sleep(2 + attempt * 2)
            skip.add(v.get("format_id"))
    return None
