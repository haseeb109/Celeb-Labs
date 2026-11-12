# package/contact_sheets.py — contact sheets for human review: the pool (thumbnails with
# tier/score/source), the edit plan (one frame per shot, labeled segment/tier/treatment)
# and the final video (frames sampled from video.mp4).
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from ..render import gfx
from ..util import ffmpeg

TW, TH, COLS = 320, 180, 6
TIER_COL = {"A": (64, 200, 120), "B": (46, 196, 182), "C": (245, 184, 61)}


def _grab(path, t):
    import cv2
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0, t) * 1000)
    ok, f = cap.read()
    cap.release()
    return cv2.cvtColor(f, cv2.COLOR_BGR2RGB) if ok else np.zeros((TH, TW, 3), np.uint8)


def sheet(tiles: list[tuple[np.ndarray, list[str], tuple]], out, title=""):
    rows = max(1, (len(tiles) + COLS - 1) // COLS)
    img = Image.new("RGB", (COLS * TW + (COLS + 1) * 8, rows * (TH + 58) + 70), (11, 18, 32))
    d = ImageDraw.Draw(img)
    gfx.draw_text(d, (12, 18), title, gfx.font("display", 30), (242, 244, 248))
    for k, (a, labels, col) in enumerate(tiles):
        x = 8 + (k % COLS) * (TW + 8)
        y = 60 + (k // COLS) * (TH + 58)
        img.paste(Image.fromarray(np.ascontiguousarray(gfx.fit_cover(a, TW, TH))), (x, y))
        d.rectangle((x, y, x + 8, y + TH), fill=col)
        for j, lb in enumerate(labels[:2]):
            gfx.draw_text(d, (x + 2, y + TH + 4 + j * 24), lb[:44], gfx.font("body", 18), (200, 205, 215))
    img.save(out, quality=88)
    return out


def pool_sheet(pool, out, limit=60):
    tiles = []
    for c in pool.get("clips", [])[:limit]:
        a = _grab(c["path"], (c["in"] + c["out"]) / 2)
        if c.get("crop"):
            h, w = a.shape[:2]
            x0, y0, x1, y1 = c["crop"]
            a = a[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
        tiles.append((a, [f"{c['tier']} {c['score']:.1f} face {c.get('face_score', 0):.2f}", c["channel"]],
                      TIER_COL.get(c["tier"], (200, 200, 200))))
    return sheet(tiles, out, f"FOOTAGE POOL — {len(pool.get('clips', []))} clips")


def plan_sheet(plan, out, render_frame=None):
    tiles = []
    for seg in plan["segments"]:
        for sh in seg["shots"]:
            if sh["template"] == "footage":
                a = _grab(sh["path"], sh["in"] + min(sh["dur"] / 2, 2.0))
                if sh.get("crop"):
                    h, w = a.shape[:2]
                    x0, y0, x1, y1 = sh["crop"]
                    a = a[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
                lab = [f"{seg['seg_id']} {sh['shot_id']} T{sh['tier']} {sh['dur']:.1f}s", f"{sh['treatment']} · {sh['channel']}"]
                col = TIER_COL.get(sh["tier"], (200, 200, 200))
            elif render_frame is not None:
                a = render_frame(sh)
                lab = [f"{seg['seg_id']} {sh['shot_id']} {sh['dur']:.1f}s", f"{sh['template']} ({sh['category']})"]
                col = (138, 148, 166)
            else:
                from ..render.media import load_image
                a = load_image(sh["image"]) if sh.get("image") else np.full((TH, TW, 3), 40, np.uint8)
                lab = [f"{seg['seg_id']} {sh['shot_id']} {sh['dur']:.1f}s", f"{sh['template']} ({sh['category']})"]
                col = (138, 148, 166)
            tiles.append((a, lab, col))
    return sheet(tiles, out, f"EDIT PLAN — {plan['shots']} shots · F1 footage {plan['ratios']['footage']:.0%} "
                            f"anim {plan['ratios']['animation']:.0%} text {plan['ratios']['text']:.0%}")


def final_sheet(video, out, n=24):
    from ..util import duration
    d = duration(video)
    tiles = [(_grab(video, d * (k + 0.5) / n), [f"{d * (k + 0.5) / n:6.1f}s"], (245, 184, 61)) for k in range(n)]
    return sheet(tiles, out, "FINAL VIDEO")
