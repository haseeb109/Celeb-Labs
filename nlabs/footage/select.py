# footage/select.py — per-source caps (F4) and reuse rules while picking clips.
# Tier B/C: max N clips and S seconds per source video. Tier A exempt from F4 but every
# clip still ≤ 5.0 s (F2). Also blocks the same source window twice within 60 s.
from __future__ import annotations

from ..constants import LockedRuleError


class SourceBudget:
    def __init__(self, max_clips: int, max_seconds: float, max_clip_s: float):
        self.max_clips, self.max_seconds, self.max_clip_s = max_clips, max_seconds, max_clip_s
        self.used: dict[str, list[float]] = {}
        self.last_use: dict[str, float] = {}   # clip_id -> timeline time

    def can_use(self, clip: dict, seconds: float, at: float | None = None) -> bool:
        if seconds > self.max_clip_s + 1e-6:
            return False
        if at is not None and clip["clip_id"] in self.last_use and at - self.last_use[clip["clip_id"]] < 60:
            return False
        if clip["tier"] == "A":
            return True
        u = self.used.get(clip["video_id"], [])
        return len(u) + 1 <= self.max_clips and sum(u) + seconds <= self.max_seconds + 1e-6

    def use(self, clip: dict, seconds: float, at: float | None = None):
        if not self.can_use(clip, seconds, at):
            raise LockedRuleError(f"F4/F2: cannot use {clip['clip_id']} for {seconds:.2f}s")
        self.used.setdefault(clip["video_id"], []).append(seconds)
        if at is not None:
            self.last_use[clip["clip_id"]] = at


def check_caps(shots: list[dict], max_clips: int, max_seconds: float, max_clip_s: float) -> list[str]:
    """Validator over a finished plan: returns violations (F2, F4)."""
    errs, per = [], {}
    for s in shots:
        if s.get("category") != "footage" or not s.get("video_id"):
            continue
        if s.get("is_third_party", True) and s["dur"] > max_clip_s + 1e-6:
            errs.append(f"F2: shot {s['shot_id']} is {s['dur']:.2f}s > {max_clip_s}s")
        if s.get("tier") in ("B", "C"):
            per.setdefault(s["video_id"], []).append(s["dur"])
    for vid, d in per.items():
        if len(d) > max_clips:
            errs.append(f"F4: {vid} used {len(d)} clips > {max_clips}")
        if sum(d) > max_seconds + 1e-6:
            errs.append(f"F4: {vid} used {sum(d):.1f}s > {max_seconds}s")
    return errs
