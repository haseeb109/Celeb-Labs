# footage/scenes.py — shot detection inside a downloaded window (PySceneDetect).
# Shots are then split into candidates of 1.5–5.0 s (F2 cap). Fallback without
# PySceneDetect: fixed 4 s pieces.
from __future__ import annotations

from ..constants import MAX_CLIP_SECONDS


def detect_shots(path, total: float) -> list[tuple[float, float]]:
    try:
        from scenedetect import detect, ContentDetector
        scenes = detect(str(path), ContentDetector(threshold=27.0))
        shots = [(s.get_seconds(), e.get_seconds()) for s, e in scenes]
        if shots:
            return shots
    except Exception:
        pass
    return [(0.0, total)]


def split_candidates(shots, min_s: float = 1.5, max_s: float = MAX_CLIP_SECONDS, target: float = 4.0):
    out = []
    for a, b in shots:
        a, b = a + 0.1, b - 0.1          # avoid cut frames
        d = b - a
        if d < min_s:
            continue
        n = max(1, int(round(d / target)))
        step = d / n
        for i in range(n):
            s = a + i * step
            e = min(s + min(step, max_s), b)
            if e - s >= min_s:
                out.append((round(s, 2), round(min(e, s + max_s), 2)))
    return out
