# footage/watermark_scan.py — Rule F6: find logos, watermarks, chyrons, tickers, burned captions.
# (a) static-overlay detector (temporal std + persistent edges in corners/top/bottom bands),
# (b) OCR on those bands (brand names → instant F7 reject), (c) largest clean 16:9 crop or REJECT.
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .blocklist import Blocklist

TOP_BAND, BOTTOM_BAND, SIDE = 0.12, 0.22, 0.12


@dataclass
class ScanResult:
    decision: str                       # "clean" | "crop" | "reject"
    boxes: list = field(default_factory=list)   # overlay boxes, normalized (x0,y0,x1,y1)
    crop: tuple | None = None           # normalized (x0,y0,x1,y1) when decision == "crop"
    area: float = 1.0
    reason: str = ""
    ocr_text: list = field(default_factory=list)
    brand: str | None = None

    def summary(self) -> str:
        if self.decision == "crop":
            return f"crop {self.area:.0%} ({len(self.boxes)} overlays)"
        return f"{self.decision}{': ' + self.reason if self.reason else ''}"


_ocr = None


def get_ocr():
    global _ocr
    if _ocr is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
        except Exception:
            _ocr = False
    return _ocr or None


def _scan_mask(h, w):
    m = np.zeros((h, w), bool)
    m[: int(h * TOP_BAND)] = True
    m[int(h * (1 - BOTTOM_BAND)):] = True
    m[:, : int(w * SIDE)] = True
    m[:, int(w * (1 - SIDE)):] = True
    return m


def _distinct_scenes(grays) -> int:
    n = 1
    for a, b in zip(grays, grays[1:]):
        if np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))) > 28:
            n += 1
    return n


def static_overlay_boxes(frames: list[np.ndarray]) -> tuple[list, bool]:
    """Return (boxes, informative). boxes normalized. informative=False when the
    footage itself is static (one tripod shot) so the temporal test can't tell overlay from scene."""
    import cv2
    grays = [cv2.cvtColor(cv2.resize(f, (640, 360)), cv2.COLOR_BGR2GRAY) for f in frames]
    stack = np.stack(grays).astype(np.float32)
    std = stack.std(axis=0)
    h, w = std.shape
    informative = _distinct_scenes(grays) >= 2 or float(np.median(std)) > 12
    if not informative:
        return [], False
    edges = np.mean([cv2.Canny(g, 60, 160) > 0 for g in grays], axis=0)
    persistent = (edges >= 0.75) & (std < 6.0)
    persistent &= _scan_mask(h, w)
    mask = cv2.dilate(persistent.astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    boxes = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 120 or persistent[y:y + bh, x:x + bw].sum() < 40:
            continue
        boxes.append((x / w, y / h, (x + bw) / w, (y + bh) / h))
    return boxes, True


def ocr_boxes(frame: np.ndarray, ocr=None) -> tuple[list, list]:
    """OCR the scan bands of one frame. Returns (boxes normalized, texts)."""
    ocr = ocr or get_ocr()
    if not ocr:
        return [], []
    import cv2
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (960, int(960 * h / w)))
    sh, sw = small.shape[:2]
    try:
        res, _ = ocr(small)
    except Exception:
        return [], []
    boxes, texts = [], []
    for item in res or []:
        pts, text, conf = item
        if conf < 0.5 or len(text.strip()) < 2:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        b = (min(xs) / sw, min(ys) / sh, max(xs) / sw, max(ys) / sh)
        boxes.append(b)
        texts.append(text)
    return boxes, texts


def _intersects(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def best_crop(boxes, min_area=0.70, face=None, step=0.01):
    """Largest 16:9 (same aspect) crop avoiding all boxes and containing the face. Normalized coords."""
    if not boxes:
        return (0.0, 0.0, 1.0, 1.0), 1.0
    pad = 0.006
    boxes = [(b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad) for b in boxes]
    s = 1.0
    min_s = min_area ** 0.5
    while s >= min_s - 1e-9:
        best, best_d = None, 9
        n = int(round((1 - s) / step))
        for i in range(n + 1):
            for j in range(n + 1):
                c = (i * step, j * step, i * step + s, j * step + s)
                if c[2] > 1.0001 or c[3] > 1.0001:
                    continue
                if any(_intersects(c, b) for b in boxes):
                    continue
                if face and not _contains(c, face):
                    continue
                d = abs((c[0] + c[2]) / 2 - 0.5) + abs((c[1] + c[3]) / 2 - 0.5)
                if d < best_d:
                    best, best_d = c, d
        if best:
            return best, s * s
        s -= step
    return None, 0.0


def scan(frames: list[np.ndarray], min_area=0.70, face_box=None, ocr=None, blocklist: Blocklist | None = None,
         use_ocr=True) -> ScanResult:
    """Full F6 decision for one source window (frames sampled across it, BGR)."""
    blocklist = blocklist or Blocklist()
    boxes, informative = static_overlay_boxes(frames)
    texts: list[str] = []
    if use_ocr:
        for f in (frames[0], frames[len(frames) // 2], frames[-1]):
            ob, ot = ocr_boxes(f, ocr)
            texts += ot
            # text anywhere in the scan bands is an overlay; text in the middle repeated = burned captions
            for b in ob:
                cy = (b[1] + b[3]) / 2
                in_band = cy < TOP_BAND or cy > 1 - BOTTOM_BAND - 0.10 or b[0] < SIDE or b[2] > 1 - SIDE
                if in_band:
                    boxes.append(b)
        brand = blocklist.brand_in_text(" ".join(texts))
        if brand:
            return ScanResult("reject", boxes, None, 0.0, f"news brand '{brand}' found by OCR (F7)", texts, brand)
    if not boxes:
        return ScanResult("clean", [], None, 1.0, "" if informative else "static scene: OCR-only check", texts)
    crop, area = best_crop(boxes, min_area, face_box)
    if crop is None:
        return ScanResult("reject", boxes, None, 0.0, f"overlays can't be cropped out with ≥{min_area:.0%} area", texts)
    return ScanResult("crop", boxes, crop, area, "", texts)
