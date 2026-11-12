# render/media.py — streaming footage frames into templates without loading whole videos.
# FootageReader pipes ffmpeg raw RGB frames for [in, in+dur] (crop applied in ffmpeg,
# so removed watermarks never reach the frame). Images are cached decoded RGB arrays.
from __future__ import annotations

import functools
import subprocess

import numpy as np

from ..constants import W, H, FPS
from ..util import ffmpeg_bin


class FootageReader:
    def __init__(self, path: str, t_in: float, dur: float, crop=None, w: int = W, h: int = H, bw=False):
        self.w, self.h = w, h
        vf = []
        if crop:
            x0, y0, x1, y1 = crop
            vf.append(f"crop=iw*{x1 - x0:.4f}:ih*{y1 - y0:.4f}:iw*{x0:.4f}:ih*{y0:.4f}")
        vf += [f"fps={FPS}", f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=bicubic", f"crop={w}:{h}"]
        if bw:
            vf.append("hue=s=0")
        cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-ss", f"{max(t_in, 0):.3f}", "-i", str(path),
               "-t", f"{dur + 0.2:.3f}", "-an", "-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.i = -1
        self.last = np.zeros((h, w, 3), np.uint8)

    def frame(self, idx: int) -> np.ndarray:
        n = self.w * self.h * 3
        while self.i < idx:
            buf = self.p.stdout.read(n) if self.p.stdout else b""
            if len(buf) < n:
                self.i = idx       # source ended: hold last frame
                break
            self.last = np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)
            self.i += 1
        return self.last

    def close(self):
        try:
            if self.p.stdout:
                self.p.stdout.close()
            self.p.kill()
            self.p.wait(timeout=5)
        except Exception:
            pass


@functools.lru_cache(maxsize=32)
def load_image(path: str) -> np.ndarray:
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if max(im.size) > 2600:
        im.thumbnail((2600, 2600))
    return np.asarray(im)


class Ctx:
    """Per-segment render context: style colors + readers keyed by shot id."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.readers: dict[str, FootageReader] = {}
        self.pal = {k: cfg.color(k) for k in (cfg.style.get("palette") or {})}

    def c(self, name):
        return self.pal.get(name, (255, 255, 255))

    def reader(self, key, path, t_in, dur, crop=None, w=W, h=H, bw=False) -> FootageReader:
        if key not in self.readers:
            self.readers[key] = FootageReader(path, t_in, dur, crop, w, h, bw)
        return self.readers[key]

    def close(self):
        for r in self.readers.values():
            r.close()
        self.readers.clear()
