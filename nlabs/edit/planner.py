# edit/planner.py — Station 7: turn script + voice + pool into edit_plan.json.
# Audio drives the timeline; each segment is filled with ≤5 s footage shots (F2), photos,
# cards and graphics; F1 ratios measured and re-planned; F2/F4 validated. Overrides supported.
from __future__ import annotations

import math

from ..constants import CAT_FOOTAGE, CAT_ANIMATION, CAT_TEXT, FPS, LockedRuleError
from ..footage.select import SourceBudget, check_caps
from ..log import get_logger
from ..util import write_json, read_json
from ..script.validate_script import est_seconds
from . import ratios
from .treatments import Rotator

log = get_logger()

TEXT_TEMPLATES = {"title", "chapter", "quote_card", "statement_card", "post_card", "list", "comment_prompt",
                  "subscribe", "recap", "endscreen", "doc", "calendar", "stamp", "names"}
ANIM_TEMPLATES = {"counter", "timeline", "chart_line", "bars", "map"}
GRAPHIC_KINDS = {"chart_line", "bars", "counter", "timeline"}


def q(t: float) -> float:
    """Quantize to whole frames so segment concat stays in sync."""
    return round(t * FPS) / FPS


class Planner:
    def __init__(self, script, voice, pool, images, ledger, official, cfg):
        self.script, self.voice, self.cfg = script, voice or {"segments": {}}, cfg
        self.pool = [c for c in (pool or {}).get("clips", [])]
        self.photos = [i for i in (images or []) if i.get("path")]
        self.ledger = ledger
        self.official = {c["fact_id"]: c for c in (official or {}).get("cards", [])}
        self.pacing = cfg.style.get("pacing", {})
        self.budget = SourceBudget(cfg.per_src_clips, cfg.per_src_secs, cfg.max_clip_s)
        self.rot = Rotator()
        self.n = 0
        self.photo_i = 0
        self.seen_people: set[str] = set()
        self.subject = script.get("subject", "")
        self.cards_over_footage = False

    # ---------- helpers
    def sid(self):
        self.n += 1
        return f"sh{self.n:04d}"

    def seg_duration(self, s) -> float:
        p = self.pacing
        if s["kind"] in ("vo", "post", "statement"):
            v = self.voice["segments"].get(s["id"])
            vo = v["duration"] if v else len(s.get("text", "")) / 15.0
            return q(p.get("lead", 0.1) + vo + p.get("tail", 0.4))
        if s["kind"] == "soundbite":
            sb = self._soundbite_clip(s)
            return q((sb[1]["duration"] if sb else 4.0) + 0.3)
        return q(est_seconds(s, 15.0, p))

    def _soundbite_clip(self, s):
        want = (s.get("text") or "").lower()
        for c in self.pool:
            for sb in c.get("soundbite_candidates", []) or []:
                if want and (want[:40] in sb.get("quote", "").lower() or want[:40] in sb["text"].lower()):
                    return c, sb
        return None

    def pick_clip(self, seg, dur, at, need_subject=False):
        kws = [k.lower() for k in (seg.get("visual", {}) or {}).get("keywords", [])]
        best, best_s = None, -1e9
        for c in self.pool:
            if c.get("_used_at") is not None and at - c["_used_at"] < 60:
                continue
            d = min(dur, c["out"] - c["in"], self.cfg.max_clip_s)
            if d < 1.5 or not self.budget.can_use(c, d, at):
                continue
            s = c["score"] - 3.0 * c.get("_uses", 0) - (4.0 if d + 1e-6 < dur else 0.0)   # prefer clips covering the slot
            text = (c.get("title", "") + " " + " ".join(c.get("tags", []))).lower()
            s += sum(0.6 for k in kws if k in text)
            if need_subject and c.get("subject_present"):
                s += 2.5
            if s > best_s:
                best, best_s = c, s
        return best

    def footage_shot(self, seg, c, dur, at, dramatic=False, overlay=None):
        d = q(min(dur, c["out"] - c["in"], self.cfg.max_clip_s))
        self.budget.use(c, d, at)
        c["_used_at"] = at
        c["_uses"] = c.get("_uses", 0) + 1
        treat = self.rot.next(c["video_id"], dramatic, c["tier"], allow_split=len(self.pool) > 3)
        sh = {"shot_id": self.sid(), "template": "footage", "category": CAT_FOOTAGE, "dur": d, "treatment": treat,
              "clip_id": c["clip_id"], "video_id": c["video_id"], "path": c["path"], "in": c["in"],
              "src_in": c["src_in"], "crop": c.get("crop"), "tier": c["tier"], "channel": c["channel"],
              "channel_id": c.get("channel_id", ""), "url": c["url"], "license": c.get("license", ""),
              "watermark": c.get("watermark"), "face_score": c.get("face_score"), "is_third_party": True,
              "credit": self.credit(c), "subject_present": c.get("subject_present", False)}
        if treat == "split":
            other = self.pick_clip(seg, d, at)
            if other and other["clip_id"] != c["clip_id"] and self.budget.can_use(other, d, at):
                self.budget.use(other, d, at)
                other["_used_at"] = at
                sh["second"] = {k: other.get(k) for k in ("clip_id", "video_id", "path", "in", "crop", "tier",
                                                          "channel", "url", "src_in", "license", "watermark", "face_score")}
                sh["second"]["credit"] = self.credit(other)
            else:
                sh["treatment"] = "framed"
        if treat == "text_over":
            kws = (seg.get("visual", {}) or {}).get("keywords", [])
            sh["text_over"] = (kws[0] if kws else self.subject).upper()[:28]
        if overlay:
            sh["overlay"] = overlay
        if c.get("subject_present") and self.subject not in self.seen_people:
            self.seen_people.add(self.subject)
            sh["lower_third"] = {"name": self.subject, "sub": c.get("title", "")[:60]}
        return sh

    def photo_shot(self, seg, dur):
        if not self.photos:
            return None
        im = self.photos[self.photo_i % len(self.photos)]
        self.photo_i += 1
        tmpl = "kb_image" if self.photo_i % 2 else "photo_card"
        credit = (f"Image: {im.get('author') or im.get('source')} ({im.get('license')})" if im.get("source") != "still"
                  else f"Footage still: {im['channel']}" + (" (public domain)" if im.get("tier") == "A" else ""))
        return {"shot_id": self.sid(), "template": tmpl, "category": CAT_FOOTAGE, "dur": q(min(max(dur, 3.0), 6.0)),
                "image": im["path"], "credit": credit, "is_third_party": False, "image_source": im.get("source"),
                "subject_present": bool(im.get("subject"))}

    def credit(self, c):
        if c["tier"] == "A":
            return f"Footage: {c['channel']} (public domain)"
        if c["tier"] == "B":
            return f"Footage: {c['channel']} ({c.get('license') or 'licensed'})"
        return f"Footage: {c['channel']} (short excerpt)"

    def card_shot(self, template, dur, data, category=CAT_TEXT, bg=None):
        sh = {"shot_id": self.sid(), "template": template, "category": category, "dur": q(dur), "data": data}
        if bg:
            sh["bg"] = bg
            sh["category"] = CAT_FOOTAGE
            sh["credit"] = bg.get("credit", "")
        return sh

    def bg_media(self, seg, dur, at):
        """Real footage/photo used behind/beside a card (counts as footage: 'text over footage')."""
        c = self.pick_clip(seg, dur, at, need_subject=True) if dur <= self.cfg.max_clip_s else None
        if c:
            d = q(min(dur, c["out"] - c["in"], self.cfg.max_clip_s))
            if d >= dur - 1e-6:
                self.budget.use(c, d, at)
                c["_used_at"] = at
                c["_uses"] = c.get("_uses", 0) + 1
                return {"kind": "clip", "path": c["path"], "in": c["in"], "crop": c.get("crop"), "clip_id": c["clip_id"],
                        "video_id": c["video_id"], "tier": c["tier"], "channel": c["channel"], "url": c["url"],
                        "src_in": c["src_in"], "license": c.get("license", ""), "watermark": c.get("watermark"),
                        "face_score": c.get("face_score"), "credit": self.credit(c)}
        if self.photos:
            im = self.photos[self.photo_i % len(self.photos)]
            self.photo_i += 1
            return {"kind": "image", "path": im["path"],
                    "credit": f"Image: {im.get('author') or im.get('channel') or im.get('source')}"}
        return None

    # ---------- per segment
    def fill(self, seg, start, dur):
        shots, t = [], 0.0
        intent = (seg.get("visual", {}) or {}).get("intent", "")
        dramatic = seg.get("retention") == "hook" or any(
            self.ledger.by_id().get(f, {}).get("status") == "alleged" for f in seg.get("fact_ids", []))
        stamp = None
        for fid in seg.get("fact_ids", []):
            st = self.ledger.by_id().get(fid, {}).get("status")
            if st in ("alleged", "denied", "reported") or self.ledger.by_id().get(fid, {}).get("hypothetical"):
                stamp = "HYPOTHETICAL" if self.ledger.by_id()[fid].get("hypothetical") else st.upper()
                break
        graphic = (seg.get("visual", {}) or {}).get("graphic")
        if graphic and graphic.get("type") in GRAPHIC_KINDS and dur > 6:
            gd = q(min(8.0, dur * 0.5))
            shots.append(self.card_shot(graphic["type"], gd, graphic, CAT_ANIMATION))
            t += gd
        target = 3.6
        while dur - t > 0.05:
            remaining = dur - t
            if remaining <= self.cfg.max_clip_s:
                want = remaining
            elif remaining <= self.cfg.max_clip_s + 2.0:
                want = remaining / 2            # two even shots instead of a long one + a flash
            else:
                want = min(target, remaining - 2.0)
            want = max(want, min(remaining, 1.5))
            c = self.pick_clip(seg, want, start + t, need_subject=intent.startswith("subject"))
            if c:
                sh = self.footage_shot(seg, c, want, start + t, dramatic)
            else:
                sh = self.photo_shot(seg, want)
                if sh is None:  # nothing real left: plain text card of the narration keywords
                    kw = (seg.get("visual", {}) or {}).get("keywords", []) or [self.subject]
                    sh = self.card_shot("list", min(remaining, 4.0), {"items": kw[:4]})
                sh["dur"] = q(min(sh["dur"], remaining))
            if stamp and not any(s.get("overlay", {}).get("stamp") for s in shots):
                sh["overlay"] = {"stamp": stamp}
            shots.append(sh)
            t += sh["dur"]
        # absorb rounding: last shot ends exactly at segment end (never extending footage past the cap)
        diff = q(dur - sum(s["dur"] for s in shots))
        if abs(diff) > 1e-6 and shots:
            last = shots[-1]
            if last["category"] != CAT_FOOTAGE or last["template"] != "footage" or last["dur"] + diff <= self.cfg.max_clip_s:
                last["dur"] = q(last["dur"] + diff)
            else:
                shots.append(self.photo_shot(seg, diff) or self.card_shot("list", diff, {"items": [self.subject]}))
                shots[-1]["dur"] = q(diff)
        return shots

    def segment_shots(self, seg, start, dur):
        k = seg["kind"]
        if k == "title":
            bg = self.bg_media(seg, dur, start) if self.cards_over_footage else None
            return [self.card_shot("title", dur, {"title": seg.get("text", ""), "sub": self.script.get("topic", "")}, bg=bg)]
        if k == "chapter":
            bg = self.bg_media(seg, dur, start) if self.cards_over_footage else None
            return [self.card_shot("chapter", dur, {"n": seg.get("chapter"), "title": seg.get("text", "")}, bg=bg)]
        if k == "endscreen":
            bg = self.bg_media(seg, dur, start) if self.cards_over_footage else None
            return [self.card_shot("endscreen", dur, {"text": seg.get("text", "")}, bg=bg)]
        if k == "soundbite":
            hit = self._soundbite_clip(seg)
            if hit:
                c, sb = hit
                d = q(min(sb["duration"], self.cfg.max_clip_s))
                self.budget.use(c, d, start)
                sh = {"shot_id": self.sid(), "template": "footage", "category": CAT_FOOTAGE, "dur": d,
                      "treatment": "full", "clip_id": c["clip_id"] + "_sb", "video_id": c["video_id"], "path": c["path"],
                      "in": sb["start"] - c["src_in"] + c["in"], "src_in": sb["start"], "crop": c.get("crop"),
                      "tier": c["tier"], "channel": c["channel"], "url": c["url"], "license": c.get("license", ""),
                      "watermark": c.get("watermark"), "face_score": c.get("face_score"), "is_third_party": True,
                      "credit": self.credit(c), "soundbite": {"text": sb["text"]}, "audio_from_source": True,
                      "lower_third": {"name": self.subject, "sub": f"{c.get('title', '')[:40]} · {c.get('year', '')}"}}
                shots = [sh]
                if dur - d > 0.05:
                    shots.append(self.photo_shot(seg, dur - d) or self.card_shot("list", dur - d, {"items": [self.subject]}))
                    shots[-1]["dur"] = q(dur - d)
                return shots
            # no matching audio: show as a quote card over footage (still verbatim, S3)
            k = "statement"
        if k in ("post", "statement"):
            fid = (seg.get("fact_ids") or [None])[0]
            card = self.official.get(fid, {})
            cd = q(min(dur, 8.0 if self.photos else self.cfg.max_clip_s))
            bg = self.bg_media(seg, cd, start)
            tmpl = "post_card" if k == "post" else "statement_card"
            data = card | {"text": card.get("text") or seg.get("text", "")}
            shots = [self.card_shot(tmpl, cd, data, bg=bg)]
            if dur - cd > 0.05:
                shots += self.fill(seg, start + cd, q(dur - cd))
            return shots
        return self.fill(seg, start, dur)

    def captions(self, seg, dur):
        v = self.voice["segments"].get(seg["id"])
        lead = self.pacing.get("lead", 0.1)
        if v and v.get("words"):
            words = [{"w": w["w"], "start": round(w["start"] + lead, 3), "end": round(w["end"] + lead, 3)} for w in v["words"]]
        else:
            from ..voice.whisper_timing import estimate
            words = [{"w": w["w"], "start": w["start"] + lead, "end": w["end"] + lead}
                     for w in estimate(seg.get("text", ""), max(dur - lead - self.pacing.get("tail", 0.4), 0.5))]
        return words

    def run(self):
        out, t = [], 0.0
        for seg in self.script["segments"]:
            dur = self.seg_duration(seg)
            shots = self.segment_shots(seg, t, dur)
            blk = {"seg_id": seg["id"], "kind": seg["kind"], "chapter": seg.get("chapter"), "start": q(t), "dur": dur,
                   "frames": int(round(dur * FPS)), "shots": shots, "text": seg.get("text", ""),
                   "captions": self.captions(seg, dur) if seg["kind"] in ("vo", "post", "statement") else [],
                   "audio": {"vo": (self.voice["segments"].get(seg["id"]) or {}).get("wav"),
                             "lead": self.pacing.get("lead", 0.1)}}
            for sh in shots:
                if sh.get("audio_from_source"):
                    blk["audio"]["source_clip"] = {"path": sh["path"], "in": sh["in"], "dur": sh["dur"]}
            out.append(blk)
            t += dur
        return out


def _reset_pool(pool):
    for c in (pool or {}).get("clips", []):
        c.pop("_used_at", None)
        c.pop("_uses", None)


def plan(script, voice, pool, images, ledger, official, cfg, rp=None, overrides=None) -> dict:
    """Plan, measure F1, re-plan if needed, validate F2/F4. Returns the plan dict."""
    attempts = []
    for mode in ("normal", "cards_over_footage"):
        _reset_pool(pool)
        p = Planner(script, voice, pool, images, ledger, official, cfg)
        p.cards_over_footage = mode == "cards_over_footage"
        segs = p.run()
        if overrides:
            apply_overrides(segs, overrides, pool)
        r = ratios.measure(segs)
        errs = ratios.check(r, cfg.footage_min, cfg.animation_max, cfg.text_max)
        attempts.append({"mode": mode, "ratios": r, "errors": errs})
        if not errs:
            break
        log.info(f"plan[{mode}] F1 not met ({errs}); re-planning")
    all_shots = [s for seg in segs for s in seg["shots"]]
    cap_errs = check_caps(all_shots, cfg.per_src_clips, cfg.per_src_secs, cfg.max_clip_s)
    if cap_errs:
        raise LockedRuleError("planner produced a plan breaking F2/F4: " + "; ".join(cap_errs))
    total = sum(s["dur"] for s in segs)
    n_vis = len(all_shots)
    result = {"segments": segs, "ratios": r, "ratio_errors": errs, "attempts": attempts,
              "runtime": round(total, 2), "shots": n_vis, "avg_shot": round(total / max(n_vis, 1), 2),
              "max_footage_shot": round(max([s["dur"] for s in all_shots if s["template"] == "footage"] or [0]), 3)}
    if rp is not None:
        write_json(rp.w("edit_plan.json"), result)
    return result


def apply_overrides(segs, overrides: dict, pool):
    """edit_plan_overrides.json: {"sh0012": {"clip_id": "..."}} or {"sh0012": {"image": "path.jpg"}}."""
    by_id = {c["clip_id"]: c for c in (pool or {}).get("clips", [])}
    for seg in segs:
        for sh in seg["shots"]:
            o = overrides.get(sh["shot_id"])
            if not o:
                continue
            if o.get("clip_id") in by_id:
                c = by_id[o["clip_id"]]
                d = min(sh["dur"], c["out"] - c["in"])
                if d + 1e-6 < sh["dur"]:
                    continue  # override clip too short — keep original
                sh.update({"template": "footage", "category": CAT_FOOTAGE, "clip_id": c["clip_id"],
                           "video_id": c["video_id"], "path": c["path"], "in": c["in"], "crop": c.get("crop"),
                           "tier": c["tier"], "channel": c["channel"], "url": c["url"], "is_third_party": True,
                           "src_in": c["src_in"], "license": c.get("license", "")})
            elif o.get("image"):
                sh.update({"template": "photo_card", "category": CAT_FOOTAGE, "image": o["image"],
                           "is_third_party": False, "credit": o.get("credit", "")})
                for k in ("clip_id", "video_id", "path"):
                    sh.pop(k, None)
