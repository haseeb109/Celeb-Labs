# util.py — small shared helpers: JSON IO, hashing, ffmpeg/ffprobe lookup and calls,
# atomic writes, and a polite HTTP client. Kept dependency-light so every station
# (and the self-test) can import it without pulling heavy libraries.
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .paths import BIN


def sha1(*parts) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data, indent=2):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=indent, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def which_tool(name: str) -> str | None:
    """Look in bin/ first (Windows static builds), then PATH."""
    for cand in (BIN / name, BIN / f"{name}.exe"):
        if cand.exists():
            return str(cand)
    return shutil.which(name)


def ffmpeg_bin() -> str:
    p = which_tool("ffmpeg")
    if not p:
        raise RuntimeError("ffmpeg not found. Run Setup.bat / setup.command first.")
    return p


def ffprobe_bin() -> str:
    p = which_tool("ffprobe")
    if not p:
        raise RuntimeError("ffprobe not found. Run Setup.bat / setup.command first.")
    return p


def run(cmd: list[str], check=True, timeout=None, quiet=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, timeout=timeout,
                          stdout=subprocess.PIPE if quiet else None,
                          stderr=subprocess.PIPE if quiet else None)


def ffmpeg(args: list[str], timeout=None) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y"] + args
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:12])} ...\n{p.stderr.decode(errors='ignore')[-1500:]}")
    return p


def probe(path: Path) -> dict:
    p = subprocess.run([ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format",
                        "-show_streams", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {p.stderr.decode(errors='ignore')}")
    return json.loads(p.stdout)


def duration(path: Path) -> float:
    info = probe(path)
    d = info.get("format", {}).get("duration")
    if d:
        return float(d)
    for s in info.get("streams", []):
        if s.get("duration"):
            return float(s["duration"])
    return 0.0


def video_size(path: Path) -> tuple[int, int]:
    for s in probe(path).get("streams", []):
        if s.get("codec_type") == "video":
            return int(s["width"]), int(s["height"])
    raise RuntimeError(f"no video stream in {path}")


def retry(fn, tries=4, base=1.5, exc=Exception, log=None):
    """Call fn() with exponential back-off."""
    last = None
    for i in range(tries):
        try:
            return fn()
        except exc as e:  # noqa
            last = e
            if log:
                log.warning(f"retry {i + 1}/{tries}: {e}")
            time.sleep(base ** i)
    raise last


BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def http_client(timeout=20.0, ua=BROWSER_UA):
    import httpx
    return httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": ua})
