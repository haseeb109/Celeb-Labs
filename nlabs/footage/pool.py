# footage/pool.py — scan windows into scored candidate clips and build footage_pool.json.
# Per window: watermark/OCR scan (F6/F7) on 12 frames; per shot: quality + face match (F8).
# Score = relevance + face + sharpness + uniqueness + tier bonus (A > B > C).
from __future__ import annotations

import numpy as np

from ..constants import MAX_CLIP_SECONDS
from ..log import get_logger
from . import watermark_scan, faces as facemod
from .scenes import detect_shots, split_candidates

log = get_logger()
TIER_BONUS = {"A": 1.5, "B": 1.0, "C": 0.0}


def read_frames(path, times: list[float]) -> list[np.ndarray]:
    import cv2
    cap = cv2.VideoCapture(str(path))
    out = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
        ok, f = cap.read()
        if ok:
            out.append(f)
    cap.release()
    return out


def quality(frames) -> dict:
    import cv2
    if not frames:
        return {"ok": False, "reason": "no frames"}
    h, w = frames[0].shape[:2]
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    sharp = float(np.median([cv2.Laplacian(g, cv2.CV_64F).var() for g in grays]))
    bright = float(np.mean([g.mean() for g in grays]))
    frozen = len(grays) > 1 and all(np.mean(np.abs(a.astype(int) - b.astype(int))) < 0.5
                                    for a, b in zip(grays, grays[1:]))
    q = {"ok": True, "sharpness": round(sharp, 1), "brightness": round(bright, 1), "width": w, "height": h,
         "vertical": h > w}
    if min(h, w) < 480 and h < 480:
        q.update(ok=False, reason=f"source height {h}px < 480")
    elif bright < 18:
        q.update(ok=False, reason="black frames")
    elif sharp < 25:
        q.update(ok=False, reason="heavy blur")
    elif frozen:
        q["frozen"] = True
    return q


def scan_window(win: dict, cfg, reference, backend, blocklist, use_ocr=True) -> tuple[list[dict], dict]:
    """win = {path, video_id, source meta..., start (in source), length}. Returns (clips, window_log)."""
    from ..util import duration
    path = win["path"]
    total = duration(path)
    times = list(np.linspace(0.3, max(total - 0.3, 0.4), 12))
    frames = read_frames(path, times)
    wlog = {"video_id": win["video_id"], "window_start": win.get("start", 0), "n_clips": 0}
    if len(frames) < 4:
        wlog["reject"] = "unreadable"
        return [], wlog
    # face box for the crop must contain the subject: use the biggest face of the middle frame
    fb = None
    if backend.available:
        fs = backend.faces(frames[len(frames) // 2])
        if fs:
            fb = max(fs, key=lambda f: (f[0][2] - f[0][0]) * (f[0][3] - f[0][1]))[0]
    sc = watermark_scan.scan(frames, cfg.crop_min_area, fb, blocklist=blocklist, use_ocr=use_ocr)
    wlog["scan"] = sc.summary()
    if sc.decision == "reject":
        wlog["reject"] = sc.reason
        return [], wlog
    clips = []
    for (a, b) in split_candidates(detect_shots(path, total), 1.5, cfg.max_clip_s):
        fr = read_frames(path, [a + 0.2, (a + b) / 2, b - 0.2])
        q = quality(fr)
        if not q["ok"]:
            continue
        m = facemod.match(fr, reference, backend, cfg.face_threshold) if backend.available else \
            {"score": 0.0, "subject_present": False, "face_box": None, "n_faces": 0}
        if win.get("claims_subject") and reference is not None and not m["subject_present"] and m["n_faces"]:
            continue  # F8: someone else's face in a clip that would be presented as the subject
        clips.append({
            "clip_id": f"{win['video_id']}_{int((win.get('start', 0) + a) * 10)}",
            "path": str(path), "in": a, "out": min(b, a + MAX_CLIP_SECONDS), "src_in": win.get("start", 0) + a,
            "video_id": win["video_id"], "url": win.get("url", ""), "title": win.get("title", ""),
            "channel": win.get("channel", ""), "channel_id": win.get("channel_id", ""), "tier": win["tier"],
            "license": win.get("license", ""), "year": (win.get("upload_date") or "")[:4],
            "crop": sc.crop, "watermark": sc.summary(), "face_score": m["score"],
            "subject_present": m["subject_present"], "face_box": m["face_box"], "n_faces": m["n_faces"],
            "sharpness": q["sharpness"], "vertical": q["vertical"], "frozen": q.get("frozen", False),
            "relevance": win.get("relevance", 0.0), "tags": win.get("tags", []), "soundbite": None,
        })
    wlog["n_clips"] = len(clips)
    return clips, wlog


def score(c: dict) -> float:
    s = c["relevance"] + TIER_BONUS.get(c["tier"], 0) + (2.0 if c["subject_present"] else 0) \
        + min(c["sharpness"], 800) / 800 - (1.0 if c["vertical"] else 0) - (0.5 if c["frozen"] else 0)
    return round(s, 3)


def finalize(clips: list[dict]) -> list[dict]:
    for c in clips:
        c["score"] = score(c)
    clips.sort(key=lambda c: c["score"], reverse=True)
    return clips
