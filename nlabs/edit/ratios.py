# edit/ratios.py — Rule F1 measured from the timeline: ≥65 % footage/photos,
# ≤20 % animation, ≤15 % text-only cards. Used by the planner (re-plan) and QC (fail).
# Categories come from constants (CAT_FOOTAGE / CAT_ANIMATION / CAT_TEXT).
from ..constants import CAT_FOOTAGE, CAT_ANIMATION, CAT_TEXT


def measure(segments: list[dict]) -> dict:
    tot = {CAT_FOOTAGE: 0.0, CAT_ANIMATION: 0.0, CAT_TEXT: 0.0}
    for seg in segments:
        for sh in seg["shots"]:
            tot[sh["category"]] = tot.get(sh["category"], 0) + sh["dur"]
    total = sum(tot.values()) or 1.0
    return {"footage": round(tot[CAT_FOOTAGE] / total, 4), "animation": round(tot[CAT_ANIMATION] / total, 4),
            "text": round(tot[CAT_TEXT] / total, 4), "seconds": {k: round(v, 2) for k, v in tot.items()},
            "total": round(total, 2)}


def check(r: dict, footage_min: float, animation_max: float, text_max: float) -> list[str]:
    errs = []
    if r["footage"] < footage_min:
        errs.append(f"F1: footage {r['footage']:.1%} < {footage_min:.0%}")
    if r["animation"] > animation_max:
        errs.append(f"F1: animation {r['animation']:.1%} > {animation_max:.0%}")
    if r["text"] > text_max:
        errs.append(f"F1: text cards {r['text']:.1%} > {text_max:.0%}")
    return errs
