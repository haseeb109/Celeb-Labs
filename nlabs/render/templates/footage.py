# render/templates/footage.py — real-footage templates: footage (all F5 treatments),
# photo_card, kb_image (Ken Burns), split. Footage is the show (F1); these templates
# only frame it. Every frame index i maps to time i/FPS inside the shot.
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from ...constants import W, H, FPS
from .. import gfx
from ..media import load_image


def _clip_frame(ctx, sh, i, key="main", src=None, w=W, h=H, bw=False):
    src = src or sh
    r = ctx.reader(f"{sh['shot_id']}_{key}_{w}x{h}_{bw}", src["path"], src["in"], sh["dur"], src.get("crop"), w, h, bw)
    return r.frame(i)


def footage(sh, i, ctx):
    t = i / FPS
    p = min(t / max(sh["dur"], 0.01), 1.0)
    treat = sh.get("treatment", "full")
    if treat in ("full", "bw", "text_over"):
        f = _clip_frame(ctx, sh, i, bw=treat == "bw")
        if treat == "text_over" and sh.get("text_over"):
            img = Image.fromarray(gfx.darken(f, 0.78))
            d = ImageDraw.Draw(img)
            fnt = gfx.font("display", 92)
            txt = sh["text_over"]
            tw = gfx.text_w(txt, fnt)
            a = gfx.ease_out(t / 0.35)
            x0 = 110
            gfx.panel(d, (x0 - 30, 760, x0 + (tw + 60) * a, 880), ctx.c("accent"), radius=8)
            if a > 0.6:
                gfx.draw_text(d, (x0, 820), txt, fnt, ctx.c("bg"), anchor="lm")
            return gfx.to_np(img)
        return f
    if treat == "punch_in":
        f = _clip_frame(ctx, sh, i)
        z = 1.0 + 0.08 * gfx.ease_in_out(p)
        return gfx.fit_cover(f, W, H, z)
    if treat == "framed":
        bgf = _clip_frame(ctx, sh, i)
        bg = gfx.darken(gfx.blur(bgf), 0.5)
        img = Image.fromarray(bg)
        fw, fh = 1500, 844
        x0, y0 = (W - fw) // 2, (H - fh) // 2 - 20
        gfx.shadow_box(img, (x0, y0, x0 + fw, y0 + fh), 18)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((x0 - 8, y0 - 8, x0 + fw + 8, y0 + fh + 8), radius=20, fill=ctx.c("panel"))
        inner = gfx.fit_cover(bgf, fw, fh)
        img.paste(Image.fromarray(np.ascontiguousarray(inner)), (x0, y0))
        d.rectangle((x0, y0 + fh - 6, x0 + int(fw * p), y0 + fh), fill=ctx.c("accent"))
        return gfx.to_np(img)
    if treat == "pip":
        bgf = _clip_frame(ctx, sh, i)
        bg = gfx.darken(gfx.blur(bgf), 0.45)
        img = Image.fromarray(bg)
        pw, ph = 1180, 664
        x0, y0 = W - pw - 110, (H - ph) // 2
        gfx.shadow_box(img, (x0, y0, x0 + pw, y0 + ph), 12)
        img.paste(Image.fromarray(np.ascontiguousarray(gfx.fit_cover(bgf, pw, ph))), (x0, y0))
        d = ImageDraw.Draw(img)
        d.rectangle((x0 - 6, y0, x0, y0 + ph), fill=ctx.c("accent"))
        return gfx.to_np(img)
    if treat == "split":
        img = gfx.canvas(ctx.c("bg"))
        half = (W - 36) // 2
        a = _clip_frame(ctx, sh, i, "L", w=half, h=H - 200)
        img.paste(Image.fromarray(np.ascontiguousarray(a)), (12, 100))
        if sh.get("second"):
            b = _clip_frame(ctx, sh, i, "R", src=sh["second"], w=half, h=H - 200)
        else:
            b = gfx.darken(a, 0.6)
        img.paste(Image.fromarray(np.ascontiguousarray(b)), (24 + half, 100))
        d = ImageDraw.Draw(img)
        d.rectangle((12 + half, 100, 24 + half, H - 100), fill=ctx.c("accent"))
        return gfx.to_np(img)
    return _clip_frame(ctx, sh, i)


def kb_image(sh, i, ctx):
    im = load_image(sh["image"])
    p = i / max(sh["dur"] * FPS, 1)
    z = 1.04 + 0.10 * gfx.ease_in_out(p)
    cx = 0.45 + 0.1 * p
    return gfx.fit_cover(im, W, H, z, cx, 0.42)


def photo_card(sh, i, ctx):
    im = load_image(sh["image"])
    t = i / FPS
    bg = gfx.darken(gfx.blur(gfx.fit_cover(im, W, H)), 0.45)
    img = Image.fromarray(bg)
    inner = gfx.fit_contain(im, 1400, 820)
    ih, iw = inner.shape[:2]
    s = 0.94 + 0.06 * gfx.ease_out(t / 0.5)
    import cv2
    inner = cv2.resize(inner, (int(iw * s), int(ih * s)))
    ih, iw = inner.shape[:2]
    x0, y0 = (W - iw) // 2, (H - ih) // 2 - 10
    gfx.shadow_box(img, (x0, y0, x0 + iw, y0 + ih), 8)
    d = ImageDraw.Draw(img)
    d.rectangle((x0 - 10, y0 - 10, x0 + iw + 10, y0 + ih + 10), fill=(245, 245, 245))
    img.paste(Image.fromarray(np.ascontiguousarray(inner)), (x0, y0))
    return gfx.to_np(img)


def bg_layer(sh, i, ctx, dim=0.5, blur_it=False):
    """Real media behind/beside a card (title/chapter/post over footage)."""
    bg = sh.get("bg")
    if not bg:
        return None
    if bg["kind"] == "clip":
        f = ctx.reader(f"{sh['shot_id']}_bg", bg["path"], bg["in"], sh["dur"], bg.get("crop")).frame(i)
    else:
        p = i / max(sh["dur"] * FPS, 1)
        f = gfx.fit_cover(load_image(bg["path"]), W, H, 1.04 + 0.06 * p)
    if blur_it:
        f = gfx.blur(f)
    return gfx.darken(f, dim)
