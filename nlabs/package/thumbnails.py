# package/thumbnails.py — 3 thumbnails (1280×720): real cutout of the subject from the
# sharpest high-face-score still (rembg), white/gold outline, bold 2–4 word hook, high contrast.
# Three concepts from ledger themes (consequence, money, question). Never AI faces (L4).
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..render import gfx
from ..images.cutout import cutout

TW, TH = 1280, 720


def outline(rgba: Image.Image, color, width=10) -> Image.Image:
    a = rgba.split()[-1]
    grown = a.filter(ImageFilter.MaxFilter(width * 2 + 1))
    ring = Image.new("RGBA", rgba.size, color + (255,))
    ring.putalpha(grown)
    ring.alpha_composite(rgba)
    return ring


def concepts(ledger, subject) -> list[str]:
    text = " ".join(f["text"].lower() for f in ledger.facts)
    hooks = []
    hooks.append("IT'S OVER" if any(w in text for w in ("resign", "fired", "steps down", "ousted")) else "THE FALL")
    hooks.append("$ BILLIONS GONE" if any(w in text for w in ("billion", "shares", "stock", "market")) else "WHAT IT COST")
    hooks.append("WHAT REALLY HAPPENED?")
    return hooks


def make(still_path: str | None, hook: str, out, accent=(245, 184, 61), bg=(11, 18, 32), variant=0):
    img = gfx.gradient_bg(bg, (40 + 40 * variant, 10, 20)).resize((TW, TH))
    if still_path:
        src = Image.open(still_path).convert("RGB")
        bgimg = src.copy().resize((TW, TH)).filter(ImageFilter.GaussianBlur(18))
        img = Image.blend(img, bgimg, 0.35)
        cut = cutout(src)
        bbox = cut.split()[-1].getbbox()
        if bbox:
            cut = cut.crop(bbox)
        s = TH * 1.02 / max(cut.height, 1)
        cut = cut.resize((max(1, int(cut.width * s)), max(1, int(cut.height * s))))
        cut = outline(cut, (255, 255, 255) if variant % 2 == 0 else accent, 9)
        x = TW - cut.width + 40 if variant != 1 else -40
        img.paste(cut, (x, TH - cut.height + 10), cut)
    d = ImageDraw.Draw(img)
    words = hook.split()
    f, lines = gfx.fit_font(hook, "display", 640, 460, 150, 60, 1.05)
    x0 = 50 if variant != 1 else TW - 700
    y = 90
    for k, ln in enumerate(lines):
        col = accent if k == len(lines) - 1 else (255, 255, 255)
        gfx.draw_text(d, (x0, y), ln, f, col, stroke=8, stroke_fill=(0, 0, 0))
        y += f.size * 1.05
    img.convert("RGB").save(out, quality=92)
    return out


def run(images, ledger, subject, rp, cfg):
    stills = sorted([i for i in images if i.get("source") == "still" and i.get("subject")] or
                    [i for i in images if i.get("subject")] or [i for i in images if i.get("source") == "still"],
                    key=lambda i: i.get("face_score", 0), reverse=True)
    hooks = concepts(ledger, subject)
    outs = []
    for k, h in enumerate(hooks[:3]):
        st = stills[k % len(stills)]["path"] if stills else None
        outs.append(str(make(st, h, rp.o(f"thumbnail_{k + 1}.jpg"), cfg.color("accent"), cfg.color("bg"), k)))
    return outs
