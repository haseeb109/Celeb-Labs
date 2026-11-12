# render/overlays.py — global overlays on every frame: source credit for every clip
# ("Footage: X (public domain)"), lower thirds on first appearance, stamps, soundbite
# captions (exact words), chapter tag, progress bar, light vignette. Grain OFF by default.
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from ..constants import W, H, FPS
from . import gfx
from .templates.cards import draw_stamp


NO_CAPTIONS = {"post_card", "statement_card", "quote_card", "comment_prompt", "title", "chapter", "endscreen",
               "subscribe", "doc"}


def lower_third(img, data, t, ctx):
    a = gfx.ease_out(t / 0.4)
    out = gfx.ease_out((t - 3.6) / 0.3)
    if out >= 1:
        return img
    d = ImageDraw.Draw(img)
    x = 90 - (1 - a) * 400 - out * 500
    nf, sf = gfx.font("display", 48), gfx.font("body", 30)
    w = max(gfx.text_w(data.get("name", ""), nf), gfx.text_w(data.get("sub", ""), sf)) + 70
    d.rectangle((x, 760, x + w, 880), fill=ctx.c("panel"))
    d.rectangle((x, 760, x + 12, 880), fill=ctx.c("accent"))
    gfx.draw_text(d, (x + 36, 772), data.get("name", ""), nf, ctx.c("text"))
    gfx.draw_text(d, (x + 36, 832), data.get("sub", ""), sf, ctx.c("muted"))
    return img


def credit(img, text):
    if not text:
        return img
    d = ImageDraw.Draw(img)
    f = gfx.font("body", 24)
    tw = gfx.text_w(text, f)
    d.rectangle((W - tw - 56, 26, W - 24, 66), fill=(0, 0, 0))
    gfx.draw_text(d, (W - 40, 46), text, f, (220, 224, 230), anchor="rm")
    return img


def progress(img, frac, ctx):
    d = ImageDraw.Draw(img)
    d.rectangle((0, H - 8, W, H), fill=(25, 32, 48))
    d.rectangle((0, H - 8, int(W * frac), H), fill=ctx.c("accent"))
    return img


def chapter_tag(img, text, ctx):
    if not text:
        return img
    d = ImageDraw.Draw(img)
    f = gfx.font("display", 26)
    tw = gfx.text_w(text, f)
    d.rectangle((24, 26, 24 + tw + 36, 66), fill=ctx.c("accent"))
    gfx.draw_text(d, (42, 46), text, f, ctx.c("bg"), anchor="lm")
    return img


def soundbite_caption(img, text, ctx):
    d = ImageDraw.Draw(img)
    f, lines = gfx.fit_font("“" + text + "”", "serif", 1500, 170, 56, 30)
    y = 1000 - len(lines) * f.size * 1.2
    for ln in lines:
        gfx.draw_text(d, (W / 2, y), ln, f, ctx.c("text"), stroke=4, anchor="ma")
        y += f.size * 1.2
    return img


def grain(frame: np.ndarray, amount=6, seed=0):
    rng = np.random.default_rng(seed)
    n = rng.integers(-amount, amount + 1, frame.shape[:2], dtype=np.int16)[..., None]
    return np.clip(frame.astype(np.int16) + n, 0, 255).astype(np.uint8)


def apply(frame: np.ndarray, sh: dict, t_shot: float, t_seg: float, seg: dict, ctx, caption_chunks, glob: dict):
    img = Image.fromarray(np.ascontiguousarray(frame))
    if sh.get("overlay", {}).get("stamp"):
        draw_stamp(img, sh["overlay"]["stamp"], t_shot, ctx)
    if sh.get("lower_third"):
        lower_third(img, sh["lower_third"], t_shot, ctx)
    if sh.get("soundbite"):
        soundbite_caption(img, sh["soundbite"]["text"], ctx)
    elif caption_chunks and glob.get("captions_on", True) and sh.get("template") not in NO_CAPTIONS:
        from . import captions
        captions.draw(img, t_seg, caption_chunks, ctx, glob.get("cap_size", 62), glob.get("cap_stroke", 5),
                      glob.get("cap_active", "accent"), sh.get("face_box") if sh.get("subject_present") else None)
    cr = sh.get("credit") or (sh.get("bg") or {}).get("credit")
    if sh.get("second", {}).get("credit"):
        cr = f"{cr} · {sh['second']['credit'].replace('Footage: ', '')}"
    credit(img, cr)
    if seg["kind"] not in ("title", "chapter", "endscreen"):
        chapter_tag(img, glob.get("chapter_tag", ""), ctx)
    progress(img, (glob.get("t0", 0) + t_seg) / max(glob.get("total", 1), 1), ctx)
    out = gfx.vignette(np.asarray(img), 0.28)
    if glob.get("grain") and sh.get("template") == "footage":
        out = grain(out, 5, int(t_seg * FPS))
    return out
