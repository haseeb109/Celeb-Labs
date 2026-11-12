# render/encode.py — encoder auto-pick (h264_nvenc → h264_videotoolbox → libx264, each
# test-encoded once), identical per-segment params so concat can stream-copy, the final
# mux with AAC 48 kHz + faststart, and the size cap (re-encode lower until ≤ max_output_gb).
from __future__ import annotations

import functools
import subprocess
from pathlib import Path

from ..constants import FPS, W, H
from ..util import ffmpeg, ffmpeg_bin, duration
from ..log import get_logger

log = get_logger()


@functools.lru_cache(maxsize=4)
def pick_encoder(pref: str = "auto") -> str:
    order = [pref] if pref not in ("auto", "") else ["h264_nvenc", "h264_videotoolbox", "libx264"]
    for enc in order:
        try:
            p = subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                "color=c=black:s=256x144:d=0.2", "-c:v", enc, "-f", "null", "-"],
                               capture_output=True, timeout=30)
            if p.returncode == 0:
                return enc
        except Exception:
            continue
    return "libx264"


def video_args(enc: str, maxrate_mbps: float = 8.0) -> list[str]:
    if enc == "libx264":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-maxrate", f"{min(maxrate_mbps, 6):.1f}M",
                "-bufsize", f"{min(maxrate_mbps, 6) * 2:.0f}M", "-pix_fmt", "yuv420p", "-profile:v", "high",
                "-g", str(FPS * 2), "-r", str(FPS)]
    b = maxrate_mbps * 0.75
    return ["-c:v", enc, "-b:v", f"{b:.1f}M", "-maxrate", f"{maxrate_mbps:.1f}M", "-bufsize", f"{maxrate_mbps * 2:.0f}M",
            "-pix_fmt", "yuv420p", "-g", str(FPS * 2), "-r", str(FPS)]


def raw_pipe_cmd(out: Path, enc: str, maxrate=8.0) -> list[str]:
    return [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-an"] + video_args(enc, maxrate) + [str(out)]


def concat(seg_files: list[Path], out: Path):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in seg_files), encoding="utf-8")
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])


def mux(video: Path, audio: Path, out: Path, grain=False):
    ffmpeg(["-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(out)])


def enforce_size(path: Path, max_gb: float, enc: str) -> dict:
    """Re-encode with a lower maxrate until the file fits (Section 11 fallback)."""
    size = path.stat().st_size / 1e9
    info = {"size_gb": round(size, 4), "reencodes": 0}
    rate = 8.0
    while size > max_gb and rate > 1.0:
        dur = duration(path)
        rate = min(rate * 0.75, max_gb * 8e3 / max(dur, 1) * 0.92)
        tmp = path.with_suffix(".small.mp4")
        ffmpeg(["-i", str(path)] + video_args(enc, rate) + ["-c:a", "copy", "-movflags", "+faststart", str(tmp)])
        tmp.replace(path)
        size = path.stat().st_size / 1e9
        info.update(size_gb=round(size, 4), reencodes=info["reencodes"] + 1, maxrate_mbps=round(rate, 2))
    info["ok"] = size <= max_gb
    return info
