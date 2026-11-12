# pipeline.py — runs the stations in order with resume (P1) and approval gates (P2):
# research → official → script [gate] → footage → images → voice (V1) → plan [gate] →
# render → mix → encode → package/QC. `inject` lets tests swap in offline fixtures.
from __future__ import annotations

import re
import sys
from pathlib import Path

from .brain import get_brain, NeedsManual, NeedsReview, BrainError
from .config import Config
from .constants import LockedRuleError
from .log import get_logger, attach_run_log, stage
from .paths import RunPaths, new_run_id
from .usage import Usage
from .util import read_json, write_json

log = get_logger()
STAGES = ["research", "script", "plan", "render", "all"]


class GateStop(Exception):
    """Pipeline paused at an approval gate (not an error)."""


def guess_subject(topic: str) -> str:
    m = re.match(r"^\s*((?:[A-Z][\w.'’-]+\s?){1,4})", topic)
    if m:
        words = m.group(1).split()
        stop = {"The", "A", "An", "Why", "How", "What", "When"}
        words = [w for w in words if w not in stop]
        # stop before a verb-like lower word already handled by regex; cut company words after 2-3 names
        return " ".join(words[:3]).strip(" ,.")
    return topic.split(",")[0][:40]


def ask_yes(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def gate(rp, name: str, cfg, auto: bool, files: list[Path]):
    """P2: stop for approval unless --auto, already approved, or the owner says yes now."""
    if auto or not cfg.get("approval_gates", True) or (rp.markers / f"approved_{name}").exists():
        return
    print(f"\n=== APPROVAL GATE: {name} ===")
    for f in files:
        print(f"  review: {f}")
    if ask_yes(f"Approve {name} and continue? [y/N] "):
        rp.mark_done(f"approved_{name}")
        return
    raise GateStop(f"Waiting for approval of '{name}'. Review the files above, then run:\n"
                   f"  python run.py --resume {rp.run_id} --approve {name}")


def run(topic: str | None = None, style: str = "news_explainer", minutes: float | None = None, stage_stop: str = "all",
        brain_name: str | None = None, auto: bool = False, confirm_tts: bool = False, resume: str | None = None,
        only_render: bool = False, rerender: list[str] | None = None, reference_image: str | None = None,
        posts_file: str | None = None, subject: str | None = None, approve: list[str] | None = None,
        overrides: dict | None = None, inject: dict | None = None, base_work=None, base_out=None) -> dict:
    inject = inject or {}
    run_id = resume or new_run_id(topic or "run")
    rp = RunPaths(run_id, base_work, base_out)
    meta = read_json(rp.w("run.json"), {}) or {}
    if resume and not meta:
        raise SystemExit(f"No run '{resume}' found in work/")
    topic = topic or meta.get("topic")
    style = meta.get("style", style) if resume else style
    cfg = Config(style, overrides)
    minutes = float(minutes or meta.get("minutes") or cfg.style.get("target_minutes", 20))
    subject = subject or meta.get("subject") or guess_subject(topic)
    meta.update(topic=topic, style=style, minutes=minutes, subject=subject, run_id=run_id)
    write_json(rp.w("run.json"), meta)
    for a in approve or []:
        rp.mark_done(f"approved_{a}")
    attach_run_log(rp.w("run.log"))
    usage = Usage(cfg.get("prices", {}))
    brain = inject.get("brain") or get_brain(cfg, usage, brain_name, rp)
    if inject.get("brain") is not None:
        brain.usage = usage
    log.info(f"N Labs run {run_id} · topic: {topic} · subject: {subject} · style {style} · {minutes} min · brain {brain.name}")
    manual: list[str] = []
    result = {"run_id": run_id, "out": str(rp.out), "work": str(rp.work), "status": "running"}
    pool = None
    try:
        # ---------------- 1. research
        from .research.station import run_research
        from .research.ledger import Ledger
        with stage("research"):
            ledger = run_research(topic, cfg, rp, brain, usage, inject.get("search"), fetcher=inject.get("fetcher"))
        if not ledger.facts:
            raise NeedsReview("research produced no facts — see research_report.md (search provider / network?)")
        pages = read_json(rp.w("pages.json"), {}) or {}
        # ---------------- 2. official statements & posts
        from .research.official import run_official
        with stage("official"):
            official = run_official(topic, subject, ledger, cfg, rp, pages, posts_file,
                                    **({"fetcher": inject["post_fetcher"]} if inject.get("post_fetcher") else {}))
        manual += [f"Paste text for {p['url']} into posts_manual.json ({p.get('reason')})" for p in official.get("needs_manual", [])]
        ledger = Ledger.from_json(read_json(rp.o("fact_ledger.json")))
        if stage_stop == "research":
            result["status"] = "stopped_after_research"
            return result
        # ---------------- 3. script
        from .script.write import run_script
        with stage("script"):
            script = run_script(topic, subject, ledger, official, cfg, rp, brain, minutes)
        gate(rp, "script", cfg, auto, [rp.o("script.txt"), rp.o("fact_ledger.json"), rp.o("research_report.md")])
        if stage_stop == "script":
            result["status"] = "stopped_after_script"
            return result
        # ---------------- 4. footage hunt
        from .script.validate_script import est_seconds
        footage_need = sum(est_seconds(s, 15.0, cfg.style.get("pacing", {})) for s in script["segments"]) * cfg.footage_min
        with stage("footage"):
            if inject.get("windows") is not None and not rp.is_done("footage"):
                from .footage.hunt import build_pool
                from .footage.blocklist import Blocklist
                from .footage import faces as facemod
                be = facemod.get_backend(inject.get("face_backend", cfg.get("face_backend", "auto")))
                st = {"need_seconds": round(footage_need, 1), "windows_rejected": [], "rejected": [], "errors": [],
                      "candidates": len(inject["windows"]), "windows": len(inject["windows"]), "reference": "fixture"}
                pool = build_pool(inject["windows"], cfg, None, be, Blocklist(), st, use_ocr=inject.get("ocr", True))
                write_json(rp.w("footage_pool.json"), pool)
                rp.mark_done("footage")
            else:
                from .footage.hunt import run_hunt
                pool = run_hunt(subject, ledger, script, cfg, rp, brain, footage_need, reference_image)
        from .package import contact_sheets
        contact_sheets.pool_sheet(pool, rp.o("contact_sheet_pool.jpg"))
        # ---------------- 5. images
        from .images.collect import run_images
        with stage("images"):
            kws = list({k for s in script["segments"] for k in (s.get("visual", {}) or {}).get("keywords", [])})
            if inject.get("images") is not None:
                from .images.collect import extract_stills
                from .images import credits
                images = extract_stills(pool, rp) + inject["images"]
                write_json(rp.w("images.json"), images)
                credits.write(images, rp.o("image_credits.txt"))
            else:
                images = run_images(subject, kws, pool, cfg, rp)
        # ---------------- 6. voice (V1 gate inside)
        from .voice.tts import run_tts, TTSBudgetStop, tts_chars
        voice, estimated = None, False
        with stage("voice"):
            if stage_stop == "plan" and not confirm_tts and not rp.is_done("voice"):
                log.info(f"plan dry-run: TTS not called ({tts_chars(script):,} chars); timings estimated")
                estimated = True
            else:
                try:
                    voice = run_tts(script, cfg, rp, usage, confirm_tts, inject.get("tts_provider"),
                                    ask=None if auto else ask_yes)
                except TTSBudgetStop as e:
                    manual.append(str(e))
                    raise
        # ---------------- 7. plan
        from .edit.planner import plan as make_plan
        with stage("plan"):
            overrides_file = rp.out / "edit_plan_overrides.json"
            saved = rp.w("edit_plan.json")
            reuse = saved.exists() and (only_render or (rp.markers / "approved_plan").exists()) and \
                not (read_json(saved, {}) or {}).get("estimated_timings", True) and \
                (not overrides_file.exists() or overrides_file.stat().st_mtime < saved.stat().st_mtime)
            if reuse:
                plan = read_json(saved)          # the approved plan is rendered exactly as reviewed
                log.info("plan: reusing the approved edit plan")
            else:
                plan = make_plan(script, voice, pool, images, ledger, official, cfg, rp,
                                 read_json(overrides_file, {}) if overrides_file.exists() else None)
                plan["estimated_timings"] = estimated
            write_json(rp.w("edit_plan.json"), plan)
            write_json(rp.o("edit_plan.json"), plan)
            contact_sheets.plan_sheet(plan, rp.o("contact_sheet_plan.jpg"), _frame_renderer(cfg))
            from .vision.check import check as vcheck
            plan["vision"] = vcheck(rp.o("contact_sheet_plan.jpg"), subject, cfg)
            if not overrides_file.exists():
                write_json(overrides_file, {"_help": "Swap shots: {\"sh0012\": {\"clip_id\": \"<from footage_pool>\"}} "
                                                     "or {\"sh0012\": {\"image\": \"path.jpg\", \"credit\": \"...\"}}"})
        from .package import report as rep
        rep.write(rp, topic, None, pool.get("stats"), plan, None, manual, usage)
        if stage_stop == "plan":
            result.update(status="stopped_after_plan", plan=str(rp.o("edit_plan.json")))
            return result
        if estimated:
            rp.clear_done("approved_plan")
        gate(rp, "plan", cfg, auto, [rp.o("contact_sheet_plan.jpg"), rp.o("edit_plan.json"), rp.o("run_report.md")])
        # ---------------- 8. render
        from .render.engine import render_all
        from .render import encode
        with stage("render"):
            segs = render_all(plan, cfg, rp, rerender=set(rerender or []))
            silent = rp.w("video_silent.mp4")
            encode.concat(segs, silent)
        # ---------------- 9. mix & encode
        from .audio.mix import build_mix
        with stage("mix_encode"):
            mix = build_mix(plan, rp, cfg)
            video = rp.o("video.mp4")
            encode.mux(silent, Path(mix["path"]), video)
            size = encode.enforce_size(video, cfg.get("max_output_gb", 1.0), encode.pick_encoder(cfg.get("encoder", "auto")))
        # ---------------- 10. package & QC
        from .package import footage_log, metadata, thumbnails, qc as qcmod, cleanup
        from .images import credits as cr
        with stage("package"):
            rows = footage_log.write(plan, rp.o("footage_log.csv"))
            img_lines = cr.write(images, rp.o("image_credits.txt"))
            metadata.build(script, ledger, plan, rows, img_lines, mix["music_credits"], cfg, brain, rp, official)
            thumbnails.run(images, ledger, subject, rp, cfg)
            contact_sheets.final_sheet(video, rp.o("contact_sheet_final.jpg"))
            q = qcmod.run(plan, video, mix, cfg, usage, pool.get("stats"), rows, rp, (voice or {}).get("gate"))
            q["size"] = size
            write_json(rp.o("qc.json"), q)
            if q["overall"] == "OK":
                cleanup.run(rp, cfg)
        usage.save(rp.o("usage.json"))
        rep.write(rp, topic, q, pool.get("stats"), plan, None, manual, usage)
        print(usage.report())
        result.update(status="done", qc=q["overall"], video=str(video))
        return result
    except GateStop as e:
        result.update(status="awaiting_approval", message=str(e))
        print(str(e))
        return result
    except NeedsManual as e:
        result.update(status="needs_manual", message=str(e))
        print(str(e))
        return result
    except (NeedsReview, BrainError, LockedRuleError) as e:
        result.update(status="needs_review" if not isinstance(e, LockedRuleError) else "locked_rule_stop", message=str(e))
        log.error(str(e))
        return result
    finally:
        usage.save(rp.o("usage.json"))
        write_json(rp.w("result.json"), result)


def _frame_renderer(cfg):
    from .render.media import Ctx
    from .render.templates import for_style
    tm = for_style(cfg.style_dir)

    def render(sh):
        ctx = Ctx(cfg)
        try:
            fn = tm.get(sh["template"]) or tm["list"]
            return fn(sh, int(min(sh["dur"], 2.0) * 30), ctx)
        except Exception:
            import numpy as np
            return np.full((180, 320, 3), 40, np.uint8)
        finally:
            ctx.close()
    return render


def footage_preview(topic: str, subject: str | None = None, style: str = "news_explainer", minutes: float = 20,
                    brain_name: str | None = None, reference_image: str | None = None, max_videos: int | None = None,
                    overrides: dict | None = None) -> dict:
    """Station 4 on its own (no research needed): hunt + scan + pool contact sheet + report.
    Useful to check footage availability for a topic before paying for research/TTS."""
    from .footage.hunt import run_hunt
    from .research.ledger import Ledger
    from .package import contact_sheets, report as rep
    cfg = Config(style, overrides)
    subject = subject or guess_subject(topic)
    rp = RunPaths(new_run_id(topic) + "_footage")
    attach_run_log(rp.w("run.log"))
    usage = Usage(cfg.get("prices", {}))
    try:
        brain = get_brain(cfg, usage, brain_name, rp)
        if brain.name in ("deepseek", "hive", "openai", "anthropic") and not brain.key:
            raise BrainError("no key")
    except Exception:
        from .brain.mock import MockBrain
        brain = MockBrain({"*": "{}"})   # → template queries
    need = minutes * 60 * cfg.footage_min
    with stage("footage"):
        pool = run_hunt(subject, Ledger(), None, cfg, rp, brain, need, reference_image, max_videos)
    contact_sheets.pool_sheet(pool, rp.o("contact_sheet_pool.jpg"))
    rep.write(rp, f"{topic} (footage preview)", None, pool["stats"], None, None, None, usage)
    return {"run_id": rp.run_id, "out": str(rp.out), "stats": {k: v for k, v in pool["stats"].items()
                                                                if k not in ("rejected", "windows_rejected", "queries")}}
