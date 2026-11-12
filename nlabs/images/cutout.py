# images/cutout.py — subject cutout for thumbnails with rembg (u2net); fallback: GrabCut.
# Input: a real still (from footage or a licensed photo). Output: RGBA PIL image.
# Real pixels only — no generated faces (L4).
from PIL import Image
import numpy as np


_session = None


def cutout(img: Image.Image) -> Image.Image:
    global _session
    try:
        from rembg import remove, new_session
        if _session is None:
            _session = new_session("u2net")   # 176 MB model, downloaded once
        return remove(img.convert("RGB"), session=_session).convert("RGBA")
    except Exception:
        import cv2
        bgr = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        rect = (int(w * 0.15), int(h * 0.05), int(w * 0.7), int(h * 0.93))
        bg, fg = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(bgr, mask, rect, bg, fg, 4, cv2.GC_INIT_WITH_RECT)
            m = np.where((mask == 1) | (mask == 3), 255, 0).astype(np.uint8)
        except Exception:
            m = np.full((h, w), 255, np.uint8)
        rgba = np.dstack([np.array(img.convert("RGB")), m])
        return Image.fromarray(rgba, "RGBA")
