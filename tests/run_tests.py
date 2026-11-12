#!/usr/bin/env python3
# tests/run_tests.py — the self-test matrix (spec Section 12): 12 tests from environment
# checks to a full offline 60-second end-to-end render. `--quick` skips test 12.
# Run: python run.py --selftest   (or python tests/run_tests.py [--quick] [--only 5,8])
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

import numpy as np  # noqa: E402

from nlabs.config import Config  # noqa: E402
from nlabs.constants import LockedRuleError, MAX_CLIP_SECONDS  # noqa: E402

RESULTS = []
WARN = []
TMP = Path(tempfile.mkdtemp(prefix="nlabs_test_"))


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def T(n, name):
    def deco(fn):
        fn.n, fn.title = n, name
        return fn
    return deco


# ------------------------------------------------------------------ 1
@T(1, "Environment (ffmpeg, ffprobe, node, yt-dlp, encoder, fonts/glyphs)")
def t_env():
    from nlabs.util import which_tool, run
    from nlabs.render.encode import pick_encoder
    from nlabs.render import gfx
    for tool in ("ffmpeg", "ffprobe"):
        check(which_tool(tool), f"{tool} missing")
    if not which_tool("node"):
        WARN.append("node not found (yt-dlp JS runtime) — some YouTube formats may fail")
    import yt_dlp
    v = yt_dlp.version.__version__
    enc = pick_encoder("auto")
    rep = gfx.glyph_report()
    missing = {k: v_["missing"] for k, v_ in rep.items() if v_["missing"]}
    if missing:
        WARN.append(f"glyphs drawn by fallback font: {missing}")
    return f"yt-dlp {v}, encoder {enc}, display font {Path(rep['display']['file']).name}"


# ------------------------------------------------------------------ 2
@T(2, "Imports & keys present (keys: warn only)")
def t_imports():
    import importlib
    mods = ["nlabs.pipeline", "nlabs.brain", "nlabs.research.station", "nlabs.research.official", "nlabs.script.write",
            "nlabs.footage.hunt", "nlabs.images.collect", "nlabs.voice.tts", "nlabs.edit.planner", "nlabs.render.engine",
            "nlabs.audio.mix", "nlabs.package.qc", "nlabs.vision.check", "cv2", "PIL", "httpx", "trafilatura", "yt_dlp"]
    for m in mods:
        importlib.import_module(m)
    opt = {}
    for m in ("scenedetect", "rapidocr_onnxruntime", "rembg", "insightface", "faster_whisper", "playwright"):
        try:
            importlib.import_module(m)
            opt[m] = True
        except Exception:
            opt[m] = False
    cfg = Config()
    keys = sorted(cfg.keys)
    for k in ("deepseek", "ai33"):
        if k not in cfg.keys:
            WARN.append(f"no {k} key in ~/.config/umf/{k}.env")
    return f"optional: {opt}; keys: {keys or 'none'}"


# ------------------------------------------------------------------ 3
@T(3, "Blocklist: news channel IDs/names rejected; OCR 'CNN' corner bug rejected")
def t_blocklist():
    from nlabs.footage.blocklist import Blocklist
    from nlabs.footage import watermark_scan as ws
    bl = Blocklist()
    check(bl.check("CNN", ""), "CNN name not blocked")
    check(bl.check("Some Channel", "UCupvZG-5ko_eiXAupbDfxWw"), "CNN id not blocked")
    check(bl.check("Bloomberg Television", ""), "Bloomberg not blocked")
    check(bl.check("BBC News عربي", ""), "BBC prefix not blocked")
    check(bl.check("Daily Tech News Network", "", 900_000), "news heuristic failed")
    check(bl.check("NVIDIA", "UCHuiy8bXnmK5nisYHUd1J5g") is None, "NVIDIA wrongly blocked")
    check(bl.check("Lex Fridman", "") is None, "podcast wrongly blocked")
    # user list can only ADD
    uf = TMP / "bl.json"
    uf.write_text(json.dumps({"names": ["Rogue Clips"], "remove": ["CNN"]}))
    bl2 = Blocklist(uf)
    check(bl2.check("Rogue Clips", "") and bl2.check("CNN", ""), "user list must add, never remove")
    # synthetic CNN-style corner bug → OCR → reject
    import cv2
    rng = np.random.default_rng(0)
    frames = []
    for k in range(12):
        f = (rng.integers(0, 255, (720, 1280, 3))).astype(np.uint8)
        f = cv2.GaussianBlur(f, (0, 0), 3)
        cv2.rectangle(f, (1060, 30), (1250, 120), (0, 0, 200), -1)
        cv2.putText(f, "CNN", (1075, 105), cv2.FONT_HERSHEY_SIMPLEX, 2.6, (255, 255, 255), 8)
        frames.append(f)
    if ws.get_ocr() is None:
        WARN.append("rapidocr not installed — OCR brand test skipped")
        return "names/ids OK; OCR skipped"
    r = ws.scan(frames, 0.70)
    check(r.decision == "reject" and r.brand == "CNN", f"CNN bug not rejected: {r}")
    return f"names/ids OK; OCR → {r.reason}"


# ------------------------------------------------------------------ 4
@T(4, "Watermark detector: static corner logo → crop; ticker bands → reject")
def t_watermark():
    from make_fixtures import watermark_clip
    from nlabs.footage import watermark_scan as ws
    from nlabs.footage.pool import read_frames
    corner = read_frames(watermark_clip("corner"), list(np.linspace(0.3, 7.6, 12)))
    r = ws.scan(corner, 0.70)
    check(r.decision == "crop", f"corner logo should be cropped: {r.summary()}")
    x0, y0, x1, y1 = r.crop
    check(x1 <= 1150 / 1280 + 0.01 or y0 >= 84 / 720 - 0.01, f"crop still contains logo: {r.crop}")
    check(r.area >= 0.70, "crop below 70 %")
    ticker = read_frames(watermark_clip("ticker"), list(np.linspace(0.3, 7.6, 12)))
    r2 = ws.scan(ticker, 0.70)
    check(r2.decision == "reject", f"ticker should be rejected: {r2.summary()}")
    # pure crop math
    c, a = ws.best_crop([(0.85, 0.02, 0.98, 0.15)], 0.70)
    check(c is not None and a >= 0.70, "crop math")
    c2, _ = ws.best_crop([(0, 0, 1, 0.12), (0, 0.78, 1, 1)], 0.70)
    check(c2 is None, "band crop should fail")
    return f"corner → {r.summary()}; ticker → {r2.summary()}"


# ------------------------------------------------------------------ helpers
def fake_pool(n_sources=10, clips_per=6, tier="C", path="x.mp4"):
    clips = []
    for s in range(n_sources):
        for k in range(clips_per):
            clips.append({"clip_id": f"v{s}_{k}", "video_id": f"v{s}", "path": path, "in": k * 5.0, "out": k * 5.0 + 5.0,
                          "src_in": k * 5.0, "tier": tier, "channel": f"Chan {s}", "channel_id": f"UC{s}", "url": f"https://youtu.be/v{s}",
                          "license": "short excerpt", "crop": None, "watermark": "clean", "face_score": 0.6,
                          "subject_present": True, "face_box": None, "sharpness": 300, "vertical": False, "frozen": False,
                          "relevance": 1.0, "tags": [], "score": 3.0 - 0.01 * (s * clips_per + k), "year": "2024"})
    return {"clips": clips, "stats": {}}


def fixture_ledger():
    from make_fixtures import FACTS, PAGES, fixture_fetcher
    from nlabs.research.ledger import Ledger
    from nlabs.research.extract import extract
    texts = {u: extract(fixture_fetcher(u))["text"] for u in PAGES}
    lg = Ledger(meta={"topic": "t"})
    for f in json.loads(json.dumps(FACTS))["facts"]:
        lg.add(f, texts, {"quantaline.example"})
    return lg


# ------------------------------------------------------------------ 5
@T(5, "Five-second cap: planner never > 5.0 s; renderer assert fires on a forged plan")
def t_five_second():
    from make_fixtures import script_60s
    from nlabs.edit.planner import plan
    from nlabs.render.engine import assert_plan_rules
    cfg = Config()
    lg = fixture_ledger()
    sc = script_60s()
    sc["subject"] = "Avery Stone"
    p = plan(sc, None, fake_pool(), [], lg, {"cards": []}, cfg)
    mx = max(s["dur"] for seg in p["segments"] for s in seg["shots"] if s["template"] == "footage")
    check(mx <= MAX_CLIP_SECONDS + 1e-6, f"planner emitted {mx}s")
    assert_plan_rules(p)
    forged = json.loads(json.dumps(p))
    for seg in forged["segments"]:
        for sh in seg["shots"]:
            if sh["template"] == "footage":
                sh["dur"] = 7.5
                seg["dur"] = sum(x["dur"] for x in seg["shots"])
                break
        else:
            continue
        break
    try:
        assert_plan_rules(forged)
        raise AssertionError("forged 7.5 s shot passed the renderer assert")
    except LockedRuleError:
        pass
    # config cannot loosen the lock
    cfg2 = Config(overrides={"max_clip_seconds": 9.0})
    check(cfg2.max_clip_s == 5.0, "config loosened the 5 s cap")
    return f"max planned footage shot {mx:.2f}s; forged plan rejected; config cannot raise cap"


# ------------------------------------------------------------------ 6
@T(6, "Per-source caps (F4): ≤4 clips and ≤15 s per Tier B/C source; Tier A exempt")
def t_caps():
    from nlabs.footage.select import SourceBudget, check_caps
    b = SourceBudget(4, 15.0, 5.0)
    c = {"clip_id": "a1", "video_id": "v1", "tier": "C"}
    for k in range(3):
        b.use(c | {"clip_id": f"a{k}"}, 5.0)
    check(not b.can_use(c | {"clip_id": "a9"}, 0.5), "15 s total cap not enforced")
    b2 = SourceBudget(4, 15.0, 5.0)
    for k in range(4):
        b2.use(c | {"clip_id": f"b{k}"}, 2.0)
    check(not b2.can_use(c | {"clip_id": "b9"}, 2.0), "4 clip cap not enforced")
    a = {"clip_id": "x", "video_id": "gov", "tier": "A"}
    b3 = SourceBudget(4, 15.0, 5.0)
    for k in range(8):
        b3.use(a | {"clip_id": f"g{k}"}, 4.0)
    check(not b3.can_use(a | {"clip_id": "g99"}, 5.5), "Tier A must still obey F2")
    shots = [{"shot_id": f"s{k}", "category": "footage", "video_id": "v1", "tier": "C", "dur": 4.0} for k in range(5)]
    errs = check_caps(shots, 4, 15.0, 5.0)
    check(any("F4" in e for e in errs), "check_caps missed violation")
    # the planner respects caps over a long script
    from nlabs.edit.planner import plan
    from make_fixtures import script_60s
    sc = script_60s(); sc["subject"] = "Avery Stone"
    p = plan(sc, None, fake_pool(3, 8), [], fixture_ledger(), {"cards": []}, Config())
    shots = [s for seg in p["segments"] for s in seg["shots"]]
    check(not check_caps(shots, 4, 15.0, 5.0), "planner broke F4")
    return "budget + validator + planner OK"


# ------------------------------------------------------------------ 7
@T(7, "Ratio check (F1) pass/fail cases")
def t_ratios():
    from nlabs.edit import ratios
    def segs(f, a, t):
        return [{"shots": [{"category": "footage", "dur": f}, {"category": "animation", "dur": a}, {"category": "text", "dur": t}]}]
    ok = ratios.measure(segs(70, 18, 12))
    check(not ratios.check(ok, 0.65, 0.20, 0.15), "valid mix failed")
    for bad in (segs(60, 25, 15), segs(70, 10, 20), segs(64, 21, 15)):
        check(ratios.check(ratios.measure(bad), 0.65, 0.20, 0.15), f"invalid mix passed {bad}")
    cfg = Config()
    check(cfg.footage_min >= 0.65 and cfg.text_max <= 0.15, "locks")
    return "pass and 3 fail cases OK"


# ------------------------------------------------------------------ 8
@T(8, "Script validator: good passes; missing fact_id / unattributed allegation / altered quote / private name rejected")
def t_script_validator():
    from make_fixtures import script_60s
    from nlabs.script.validate_script import validate_script, est_seconds
    lg = fixture_ledger()
    check(any(d["fact_id"] == "F007" for d in lg.dropped_quotes), "fabricated quote not dropped by code (S3)")
    st = {f["fact_id"]: f["status"] for f in lg.facts}
    check(st["F004"] == "reported" and st["F005"] == "reported", f"status logic wrong: {st}")
    check(st["F001"] == "confirmed", "primary source should confirm")
    cfg = Config()
    cards = [{"kind": "statement", "fact_id": "F002"}]
    pacing = cfg.style["pacing"]
    good = script_60s()
    total = sum(est_seconds(s, 15.0, pacing) for s in good["segments"])
    V = lambda s: validate_script(s, lg, cards, 60, 0.03, 15.0, pacing, [], cfg.style["retention"])
    e = validate_script(good, lg, cards, total, 0.03, 15.0, pacing, [], cfg.style["retention"])
    check(not e, f"good script rejected: {e}")
    def mutate(fn):
        s = json.loads(json.dumps(good)); fn(s["segments"]); return validate_script(s, lg, cards, total, 0.03, 15.0, pacing, [], cfg.style["retention"])
    e1 = mutate(lambda S: S[0].update(fact_ids=[]))
    check(any("fact_id" in x for x in e1), f"missing fact_id not caught {e1}")
    e2 = mutate(lambda S: S[7].update(text="The board had reviewed a conduct complaint for weeks before the exit. A spokesperson denied any wrongdoing in the case."))
    check(any("attribution" in x for x in e2), f"unattributed allegation not caught {e2}")
    e3 = mutate(lambda S: S[4].update(kind="vo", text='Stone wrote: "I am very proud of what this team has built, and it is the right moment to leave."'))
    check(any("exactly match" in x for x in e3), f"altered quote not caught {e3}")
    e4 = mutate(lambda S: S[7].update(text="According to the Daily Ledger, the complaint came from Jordan Pike, a former employee. A spokesperson denied any wrongdoing."))
    check(any("private" in x for x in e4), f"private name not caught {e4}")
    e5 = mutate(lambda S: S.__delitem__(4))
    check(any("S1" in x for x in e5), "missing official statement not caught")
    e6 = V(good)
    return f"est {total:.1f}s; 5 rejection cases OK; length check active ({len(e6)} errs at 60 s target)"


# ------------------------------------------------------------------ 9
@T(9, "TTS gate: 5,001 chars without --confirm-tts stops before any network call")
def t_tts_gate():
    from nlabs.voice import tts, ai33
    from nlabs.paths import RunPaths
    called = []
    orig = ai33.synth
    ai33.synth = lambda *a, **k: called.append(1) or (_ for _ in ()).throw(RuntimeError("network!"))
    try:
        text = ("word " * 1001)[:5001]
        sc = {"segments": [{"id": "s1", "kind": "vo", "text": text}]}
        rp = RunPaths("tts_gate_test", TMP / "w", TMP / "o")
        try:
            tts.run_tts(sc, Config(), rp, None, confirm=False, provider="ai33")
            raise AssertionError("gate did not stop")
        except tts.TTSBudgetStop as e:
            msg = str(e)
        check(not called, "ai33 was called despite the gate")
        check(len(text) == 5001, "test text")
        g = tts.budget_gate({"segments": [{"id": "s1", "kind": "vo", "text": "x" * 5000}]}, Config(), False, "v", 1.0)
        check(g["chars_new"] == 5000, "5,000 must pass")
        check(Config(overrides={"tts_confirm_chars": 99999}).tts_confirm_chars == 5000, "config raised the TTS limit")
    finally:
        ai33.synth = orig
    return msg.split(".")[0]


# ------------------------------------------------------------------ 10
@T(10, "Brain plumbing: mock provider + repair loop + needs_review")
def t_brain():
    from nlabs.brain.mock import MockBrain
    from nlabs.brain import run_pass, NeedsReview, extract_json
    from nlabs.usage import Usage
    u = Usage({})
    b = MockBrain({"p": ["not json at all", '{"queries": []}', '```json\n{"queries": ["a","b"]}\n```']}, usage=u)
    val = lambda d: [] if len(d.get("queries", [])) == 2 else ["need 2 queries"]
    d = run_pass(b, "p", [{"role": "user", "content": "hi"}], val, 3, 3)
    check(d == {"queries": ["a", "b"]}, f"repair result {d}")
    check(len(b.calls) == 3, "expected 2 repairs")
    check("failed validation" in b.calls[1][1][-1]["content"], "errors were not sent back")
    b2 = MockBrain({"p": ['{"x":1}']})
    try:
        run_pass(b2, "p", [{"role": "user", "content": "hi"}], lambda d: ["always wrong"], 2, 1)
        raise AssertionError("no NeedsReview")
    except NeedsReview:
        pass
    check(len(b2.calls) == 4, f"attempts×(repairs+1) = 4, got {len(b2.calls)}")
    check(extract_json('blah {"a": "}"} tail') == {"a": "}"}, "extract_json")
    check(u.totals()["tokens_in"] > 0, "usage ledger empty")
    # manual brain writes prompt and pauses
    from nlabs.brain.manual import Manual
    from nlabs.brain import NeedsManual
    m = Manual(TMP / "manual", interactive=False)
    try:
        m.complete([{"role": "user", "content": "x"}], pass_name="outline")
        raise AssertionError("manual did not pause")
    except NeedsManual:
        pass
    (TMP / "manual" / "outline_1.response.json").write_text('{"ok":1}')
    m2 = Manual(TMP / "manual", interactive=False)
    check(m2.complete([{"role": "user", "content": "x"}], pass_name="outline").text == '{"ok":1}', "manual resume")
    return "repair, fresh attempts, NeedsReview, manual pause/resume, usage OK"


# ------------------------------------------------------------------ 11
@T(11, "Templates render one frame each (golden-image smoke test, glyph check)")
def t_templates():
    from make_fixtures import source_clips
    from nlabs.render.templates import TEMPLATES
    from nlabs.render.media import Ctx
    from nlabs.render.overlays import apply
    from PIL import Image
    clips = source_clips()
    still = TMP / "still.jpg"
    from nlabs.footage.pool import read_frames
    import cv2
    cv2.imwrite(str(still), read_frames(clips[0], [3.0])[0])
    cfg = Config()
    ctx = Ctx(cfg)
    base = {"dur": 4.0, "path": str(clips[0]), "in": 1.0, "image": str(still), "crop": None}
    data = {
        "title": {"title": "The Fall × Rise — “Test” ✓ →"}, "chapter": {"n": 3, "title": "In His Own Words"},
        "quote_card": {"text": "We build the future.", "speaker": "Avery Stone"},
        "statement_card": {"text": "I am proud of what this team has built.", "speaker": "Avery Stone", "source_line": "Source: newsroom"},
        "post_card": {"author": "Avery Stone", "handle": "averystone", "verified": True, "date": "Nov 10, 2026",
                      "text": "Thank you to everyone at Quantaline.", "source_line": "Source: X / @averystone"},
        "list": {"items": ["CEO", "Board", "Shares"]}, "stamp": {"label": "ALLEGED"},
        "names": {"people": [{"name": "Avery Stone", "role": "Founder"}, {"name": "Morgan Lee", "role": "Interim CEO"}]},
        "doc": {"heading": "Board resolution", "text": "Generic document text " * 20}, "calendar": {"month": "Nov", "day": 10, "label": "Announcement"},
        "comment_prompt": {"question": "Should founders step aside?"}, "subscribe": {}, "recap": {"items": ["One", "Two"]},
        "endscreen": {"text": "WATCH NEXT"}, "counter": {"from": 0, "to": 12000, "label": "employees", "title": "Headcount"},
        "timeline": {"title": "Timeline", "events": [{"date": "2009", "label": "Founded"}, {"date": "2026", "label": "Exit"}]},
        "chart_line": {"title": "Shares", "points": [["Mon", 100], ["Tue", 94], ["Wed", 96]], "estimate": True},
        "bars": {"title": "Value", "items": [["A", 10], ["B", 6]], "hypothetical": True},
    }
    gdir = ROOT / "tests" / "golden"
    gdir.mkdir(exist_ok=True)
    made, diffs = 0, {}
    for name, fn in TEMPLATES.items():
        if fn is None:
            continue
        variants = [None]
        if name == "footage":
            variants = ["full", "punch_in", "framed", "split", "pip", "bw", "text_over"]
        for v in variants:
            sh = dict(base, shot_id=f"t_{name}_{v}", template=name, category="footage", data=data.get(name, {}))
            if v:
                sh["treatment"] = v
                sh["text_over"] = "KEYWORD"
            fr = fn(sh, 45, ctx)
            check(fr.shape == (1080, 1920, 3) and fr.dtype == np.uint8, f"{name} bad frame {fr.shape}")
            check(fr.std() > 3, f"{name}/{v} rendered a blank frame")
            seg = {"kind": "vo", "seg_id": "s1"}
            caps = [[{"w": "hello", "start": 0.0, "end": 2.0}, {"w": "world", "start": 2.0, "end": 3.0}]]
            out = apply(fr, sh | {"credit": "Footage: Test (public domain)", "overlay": {"stamp": "CONFIRMED"} if name == "footage" else {}},
                        1.5, 1.5, seg, ctx, caps, {"total": 10})
            small = np.asarray(Image.fromarray(out).resize((192, 108)))
            gp = gdir / f"{name}_{v or 'default'}.png"
            if gp.exists():
                ref = np.asarray(Image.open(gp).convert("RGB")).astype(np.int16)
                diffs[gp.stem] = float(np.abs(ref - small.astype(np.int16)).mean())
            else:
                Image.fromarray(small).save(gp)
            made += 1
    ctx.close()
    bad = {k: d for k, d in diffs.items() if d > 25}
    check(not bad, f"golden mismatch: {bad}")
    return f"{made} frames OK" + (f"; golden max diff {max(diffs.values()):.1f}" if diffs else "; golden images created")


# ------------------------------------------------------------------ 12
@T(12, "End-to-end mini run on fixtures (60 s video, dummy TTS, mock brain) → qc.json OK")
def t_e2e():
    from make_fixtures import source_clips, FACTS, TOPIC, SUBJECT, fixture_fetcher, script_60s, N, D
    from nlabs.brain.mock import MockBrain
    from nlabs.research.search import OfflineSearch, Hit
    from nlabs.pipeline import run
    from nlabs.script.validate_script import est_seconds
    clips = source_clips()
    windows = [{"path": str(p), "video_id": f"pd_fixture_{i}", "url": f"file://fixtures/{p.name}",
                "title": f"Fixture source {i} (generated, public domain)", "channel": "N Labs Fixtures",
                "channel_id": "UC_FIXTURE", "tier": "A", "license": "generated test footage (public domain)",
                "upload_date": "2026", "relevance": 1.0, "start": 0.0, "length": 16.0} for i, p in enumerate(clips)]
    sc = script_60s()
    total = sum(est_seconds(s, 15.0, Config().style["pacing"]) for s in sc["segments"])
    minutes = total / 60.0
    titles = {"titles": [{"style": s, "text": f"{s.title()} title for the fixture"} for s in
                         ["curiosity", "consequence", "number", "question", "contrarian"]],
              "summary": "Fixture summary.", "tags": [f"tag{k}" for k in range(15)], "pinned_comment": "What next?"}
    outline = {"chapters": [{"n": 1, "title": "The Announcement", "fact_ids": ["F001", "F002"], "official_cards": ["F002"]}],
               "comment_prompt": {"question": "Should founders step aside?"}}
    brain = MockBrain({"research_queries": json.dumps({"queries": [{"q": f"q{k}", "latest": True} for k in range(8)]}),
                       "extract_facts": json.dumps(FACTS), "outline": json.dumps(outline),
                       "script": json.dumps(sc), "titles": json.dumps(titles)})
    search = OfflineSearch(hits=[Hit(url=N, title="Leadership update"), Hit(url=D, title="Board review")])
    work, out = TMP / "work", TMP / "output"
    r = run(TOPIC, "news_explainer", minutes, "all", None, auto=True, subject=SUBJECT,
            overrides={"cleanup_after_run": False, "parallel_workers": 4},
            inject={"brain": brain, "search": search, "fetcher": fixture_fetcher, "windows": windows, "images": [],
                    "tts_provider": "dummy", "face_backend": "none", "post_fetcher": lambda u: {"url": u, "needs_manual": True}},
            base_work=work, base_out=out)
    check(r["status"] == "done", f"pipeline status {r['status']}: {r.get('message')}")
    od = Path(r["out"])
    q = json.loads((od / "qc.json").read_text())
    for f in ("video.mp4", "thumbnail_1.jpg", "thumbnail_2.jpg", "thumbnail_3.jpg", "metadata.txt", "script.txt", "script.json",
              "fact_ledger.json", "footage_log.csv", "image_credits.txt", "contact_sheet_plan.jpg", "contact_sheet_final.jpg",
              "qc.json", "run_report.md", "usage.json"):
        check((od / f).exists(), f"missing output {f}")
    check(q["overall"] == "OK", f"QC not OK: {json.dumps(q['checks'])} ratios {q['ratios']}")
    check(q["max_clip_s"] <= 5.0, "F2")
    shutil.copytree(od, ROOT / "tests" / "last_e2e_output", dirs_exist_ok=True)
    return f"runtime {q['runtime_s']}s, footage {q['ratios']['footage']:.0%}, LUFS {q['loudness_lufs']}, {q['size_gb'] * 1000:.1f} MB"


ALL = [t_env, t_imports, t_blocklist, t_watermark, t_five_second, t_caps, t_ratios, t_script_validator, t_tts_gate,
       t_brain, t_templates, t_e2e]


def main():
    quick = "--quick" in sys.argv
    only = None
    if "--only" in sys.argv:
        only = {int(x) for x in sys.argv[sys.argv.index("--only") + 1].split(",")}
    print("N Labs self-test\n" + "=" * 60)
    ok = True
    for fn in ALL:
        if quick and fn.n == 12 or (only and fn.n not in only):
            continue
        t0 = time.time()
        try:
            info = fn()
            print(f"[PASS] {fn.n:>2}. {fn.title}  ({time.time() - t0:.1f}s)\n        {info}")
            RESULTS.append((fn.n, True, info))
        except Exception as e:
            ok = False
            print(f"[FAIL] {fn.n:>2}. {fn.title}\n        {type(e).__name__}: {e}")
            traceback.print_exc(limit=3)
            RESULTS.append((fn.n, False, str(e)))
    for w in WARN:
        print(f"[WARN] {w}")
    print("=" * 60)
    print(f"{sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} passed")
    shutil.rmtree(TMP, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
