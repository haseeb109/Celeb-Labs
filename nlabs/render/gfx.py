# render/gfx.py — the drawing toolkit used by every template: fonts with per-glyph
# fallback, text boxes, rounded panels, easing, image fitting, blur, vignette.
# Frames are RGB numpy arrays (H, W, 3) uint8; PIL is used for text and shapes.
from __future__ import annotations

import functools
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..constants import W, H

FONT_DIRS = [Path(__file__).resolve().parents[2] / "styles", Path("/usr/share/fonts"), Path("/Library/Fonts"),
             Path("/System/Library/Fonts"), Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
             Path.home() / ".fonts", Path.home() / "Library/Fonts"]
CANDIDATES = {
    "display": ["InterDisplay-Black.otf", "Inter-Black.otf", "InterDisplay-ExtraBold.otf", "Inter-ExtraBold.otf",
                "Oswald-Bold.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"],
    "body": ["Inter-SemiBold.otf", "Inter-SemiBold.ttf", "InterDisplay-SemiBold.otf", "DejaVuSans.ttf",
             "segoeuisb.ttf", "arial.ttf", "Arial.ttf"],
    "mono": ["IBMPlexMono-Regular.ttf", "DejaVuSansMono.ttf", "consola.ttf", "Menlo.ttc"],
    "serif": ["SourceSerif4-Semibold.ttf", "DejaVuSerif-Bold.ttf", "georgiab.ttf", "Georgia Bold.ttf"],
    "fallback": ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "NotoSans-Regular.ttf", "seguisym.ttf", "arial.ttf"],
}
TEST_GLYPHS = "×✓→—“”"


@functools.lru_cache(maxsize=None)
def find_font_file(role: str) -> str | None:
    for name in CANDIDATES.get(role, []):
        for d in FONT_DIRS:
            if not d.exists():
                continue
            hits = list(d.rglob(name)) if d.is_dir() else []
            if hits:
                return str(hits[0])
    return None


@functools.lru_cache(maxsize=256)
def font(role: str, size: int) -> ImageFont.FreeTypeFont:
    f = find_font_file(role) or find_font_file("fallback")
    if f:
        return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


@functools.lru_cache(maxsize=4096)
def _has(path: str, cp: int) -> bool:
    try:
        tt = _tt(path)
        return any(cp in t.cmap for t in tt["cmap"].tables if t.isUnicode())
    except Exception:
        return True   # no fontTools: assume present


def has_glyph(fnt: ImageFont.FreeTypeFont, ch: str) -> bool:
    return _has(getattr(fnt, "path", ""), ord(ch))


@functools.lru_cache(maxsize=16)
def _tt(path):
    from fontTools.ttLib import TTFont
    return TTFont(path, lazy=True)


def glyph_report() -> dict:
    out = {}
    for role in ("display", "body", "mono"):
        f = font(role, 40)
        out[role] = {"file": getattr(f, "path", "default"),
                     "missing": [c for c in TEST_GLYPHS if not has_glyph(f, c)]}
    return out


def draw_text(d: ImageDraw.ImageDraw, xy, text, fnt, fill, stroke=0, stroke_fill=(0, 0, 0), anchor="la"):
    """Draw text; characters missing from the font are drawn with the fallback font (per glyph)."""
    missing = [c for c in set(text) if ord(c) > 127 and not has_glyph(fnt, c)]
    if not missing:
        d.text(xy, text, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill, anchor=anchor)
        return
    fb = ImageFont.truetype(find_font_file("fallback"), fnt.size) if find_font_file("fallback") else fnt
    x, y = xy
    if anchor[0] == "m":
        x -= text_w(text, fnt) / 2
    for ch in text:
        f = fb if ch in missing else fnt
        d.text((x, y), ch, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill, anchor="l" + anchor[1])
        x += d.textlength(ch, font=f)


def text_w(text, fnt) -> float:
    return fnt.getlength(text)


def wrap(text: str, fnt, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if text_w(t, fnt) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_font(text, role, max_w, max_h, start=96, min_size=28, line_gap=1.2):
    s = start
    while s > min_size:
        f = font(role, s)
        lines = wrap(text, f, max_w)
        if len(lines) * s * line_gap <= max_h:
            return f, lines
        s -= 4
    f = font(role, min_size)
    return f, wrap(text, f, max_w)


def ease_out(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    t = min(max(t, 0.0), 1.0)
    return 3 * t * t - 2 * t * t * t


def canvas(color=(11, 18, 32)) -> Image.Image:
    return Image.new("RGB", (W, H), color)


def gradient_bg(c1, c2, vertical=True) -> Image.Image:
    a = np.linspace(0, 1, H if vertical else W)[:, None] if vertical else np.linspace(0, 1, W)[None, :]
    c1, c2 = np.array(c1, np.float32), np.array(c2, np.float32)
    if vertical:
        g = (c1[None, None, :] * (1 - a[..., None]) + c2[None, None, :] * a[..., None])
        g = np.repeat(g, W, axis=1)
    else:
        g = (c1[None, None, :] * (1 - a[..., None]) + c2[None, None, :] * a[..., None])
        g = np.repeat(g, H, axis=0)
    return Image.fromarray(g.astype(np.uint8))


def panel(d, box, fill, radius=24, outline=None, width=0):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def fit_cover(img: np.ndarray, w: int, h: int, zoom: float = 1.0, cx=0.5, cy=0.5) -> np.ndarray:
    """Resize+crop an RGB/BGR array to exactly (h, w), with optional zoom around (cx, cy)."""
    import cv2
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih) * zoom
    nw, nh = max(int(iw * s + 0.5), w), max(int(ih * s + 0.5), h)
    r = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    x0 = int(min(max(cx * nw - w / 2, 0), nw - w))
    y0 = int(min(max(cy * nh - h / 2, 0), nh - h))
    return r[y0:y0 + h, x0:x0 + w]


def fit_contain(img: np.ndarray, w: int, h: int) -> np.ndarray:
    import cv2
    ih, iw = img.shape[:2]
    s = min(w / iw, h / ih)
    return cv2.resize(img, (max(1, int(iw * s)), max(1, int(ih * s))), interpolation=cv2.INTER_AREA)


def blur(img: np.ndarray, k=41) -> np.ndarray:
    import cv2
    small = cv2.resize(img, (img.shape[1] // 4, img.shape[0] // 4))
    small = cv2.GaussianBlur(small, (0, 0), k / 8)
    return cv2.resize(small, (img.shape[1], img.shape[0]))


def darken(img: np.ndarray, f=0.55) -> np.ndarray:
    return (img.astype(np.float32) * f).astype(np.uint8)


@functools.lru_cache(maxsize=2)
def vignette_mask(strength=0.35) -> np.ndarray:
    y, x = np.ogrid[:H, :W]
    d = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    return (1 - strength * np.clip(d - 0.55, 0, 1) ** 1.5)[..., None].astype(np.float32)


def vignette(frame: np.ndarray, strength=0.35) -> np.ndarray:
    return (frame.astype(np.float32) * vignette_mask(strength)).astype(np.uint8)


def paste_rgba(base: Image.Image, overlay: Image.Image, xy=(0, 0)):
    base.paste(overlay, xy, overlay)


def shadow_box(base: Image.Image, box, radius=24, offset=14, blur_r=22, alpha=150):
    sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(sh)
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0 + offset, y0 + offset, x1 + offset, y1 + offset), radius=radius, fill=(0, 0, 0, alpha))
    sh = sh.filter(ImageFilter.GaussianBlur(blur_r))
    base.paste(sh, (0, 0), sh)


def to_np(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB"))


def to_pil(a: np.ndarray) -> Image.Image:
    return Image.fromarray(a)
