# tests/fixtures/make_fixtures.py — generates the offline fixtures used by the self-test:
# 8 synthetic "public-domain" source clips (ffmpeg-generated, no third-party content),
# watermark test clips, and the fixture news pages / ledger / script for the 60 s demo.
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from nlabs.util import ffmpeg  # noqa: E402

FIX = Path(__file__).resolve().parent
GEN = FIX / "generated"

SOURCES = [
    "mandelbrot=s=1280x720:start_scale=3:end_scale=0.3:rate=30",
    "life=s=1280x720:mold=10:r=30:ratio=0.3:death_color=#1E3A5F:life_color=#F5B83D",
    "cellauto=s=1280x720:rule=110:rate=30",
    "gradients=s=1280x720:speed=0.05:rate=30:n=4",
    "sierpinski=s=1280x720:rate=30:type=carpet",
    "zoneplate=s=1280x720:rate=30:kt2=8:ky=10:kx=10",
    "mandelbrot=s=1280x720:start_scale=1.5:end_scale=0.05:rate=30:outer=normalized_iteration_count",
    "life=s=1280x720:mold=25:r=30:ratio=0.3:death_color=#4A6A96:life_color=#2EC4B6",
]


def source_clips(n=8, seconds=16, force=False) -> list[Path]:
    GEN.mkdir(parents=True, exist_ok=True)
    out = []
    for i, src in enumerate(SOURCES[:n]):
        p = GEN / f"pd_source_{i}.mp4"
        if force or not p.exists():
            # a hard cut every 4 s (hue shift) so shot detection has real scenes; noise keeps it sharp
            vf = (f"format=yuv420p,hue=h='floor(t/4)*70':s=1.3,noise=alls=18:allf=t,eq=brightness=0.06:contrast=1.1,"
                  f"drawbox=x='mod(t*160,1280)':y=300:w=120:h=120:color=white@0.6:t=fill")
            ffmpeg(["-f", "lavfi", "-i", f"{src}", "-f", "lavfi", "-i", f"sine=f={220 + 40 * i}:sample_rate=48000",
                    "-t", str(seconds), "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", str(p)])
        out.append(p)
    return out


def watermark_clip(kind: str, force=False) -> Path:
    """kind: 'corner' (static corner logo → crop) or 'ticker' (top+bottom banners → reject)."""
    GEN.mkdir(parents=True, exist_ok=True)
    p = GEN / f"wm_{kind}.mp4"
    if p.exists() and not force:
        return p
    base = "mandelbrot=s=1280x720:start_scale=2:end_scale=0.2:rate=30"
    vf = "format=yuv420p,hue=h='floor(t/2)*90':s=1.4,noise=alls=25:allf=t"
    font = ROOT / "styles" / "news_explainer" / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
    ff = str(font).replace(":", "\\:")
    if kind == "corner":
        vf += (",drawbox=x=1150:y=24:w=110:h=60:color=white@1:t=fill,drawbox=x=1156:y=30:w=98:h=48:color=red@1:t=4,"
               f"drawtext=fontfile='{ff}':text='LOGO':x=1166:y=36:fontsize=30:fontcolor=black")
    else:
        vf += (",drawbox=x=0:y=0:w=1280:h=86:color=0x102040@1:t=fill,"
               f"drawtext=fontfile='{ff}':text='BREAKING  MARKETS  LIVE  UPDATE':x=40:y=22:fontsize=40:fontcolor=white,"
               "drawbox=x=0:y=560:w=1280:h=160:color=0x9a0000@1:t=fill,"
               f"drawtext=fontfile='{ff}':text='STOCKS FALL AFTER ANNOUNCEMENT':x=40:y=590:fontsize=52:fontcolor=white,"
               f"drawtext=fontfile='{ff}':text='DOW -1.2%  NASDAQ -2.4%  S&P -1.8%':x=40:y=660:fontsize=36:fontcolor=yellow")
    ffmpeg(["-f", "lavfi", "-i", base, "-t", "8", "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", str(p)])
    return p


# ---------- fixture "news pages" (fictional company and person, written for tests)
SUBJECT = "Avery Stone"
TOPIC = "Avery Stone steps down as Quantaline CEO"
PAGES = {
    "https://quantaline.example/newsroom/leadership-update": """
<html><head><title>Leadership update — Quantaline Newsroom</title></head><body><article>
<h1>Leadership update</h1><p>November 10, 2026</p>
<p>Quantaline today announced that Avery Stone has stepped down as Chief Executive Officer and as a member of the Board, effective immediately.</p>
<p>"I am proud of what this team has built, and I believe this is the right moment to step aside," said Avery Stone.</p>
<p>The Board has appointed Chief Operating Officer Morgan Lee as interim Chief Executive Officer while it conducts a search.</p>
<p>Quantaline was founded by Avery Stone in 2009 and now employs more than 12,000 people worldwide. The company designs low-power sensor chips used in cars and phones.</p>
</article></body></html>""",
    "https://dailyledger.example/2026/11/quantaline-ceo-review": """
<html><head><title>Quantaline board had reviewed CEO conduct, people familiar say</title></head><body><article>
<p>The Quantaline board had been reviewing a complaint about workplace conduct for several weeks before the announcement, according to two people familiar with the matter.</p>
<p>A spokesperson for Avery Stone denied any wrongdoing and said the departure was a personal decision.</p>
<p>Quantaline shares fell 6 percent in early trading on Monday after the announcement.</p>
<p>Analysts said the founder's exit leaves questions about the company's product roadmap for next year. The complaint was filed by a former employee, Jordan Pike, according to the people.</p>
</article></body></html>""",
}


def fixture_fetcher(url):
    if url not in PAGES:
        from nlabs.research.fetch import Skipped
        raise Skipped("fixture: unknown url")
    return {"url": url, "html": PAGES[url], "status": 200, "fetched": "2026-11-12T09:00:00+0000"}


N = "https://quantaline.example/newsroom/leadership-update"
D = "https://dailyledger.example/2026/11/quantaline-ceo-review"
FACTS = {"facts": [
    {"text": "Quantaline announced that Avery Stone stepped down as CEO and board member, effective immediately.",
     "status": "confirmed", "type": "fact", "quote": None, "people": ["Avery Stone"], "date": "2026-11-10",
     "sources": [{"url": N, "outlet": "Quantaline newsroom", "published": "2026-11-10"}]},
    {"text": "Avery Stone said stepping aside now is the right moment.", "status": "confirmed", "type": "statement",
     "quote": "I am proud of what this team has built, and I believe this is the right moment to step aside,",
     "people": ["Avery Stone"], "date": "2026-11-10",
     "sources": [{"url": N, "outlet": "Quantaline newsroom", "published": "2026-11-10"}]},
    {"text": "COO Morgan Lee was appointed interim CEO.", "status": "confirmed", "type": "fact", "quote": None,
     "people": ["Morgan Lee"], "date": "2026-11-10", "sources": [{"url": N, "outlet": "Quantaline newsroom"}]},
    {"text": "The board had reviewed a workplace conduct complaint for weeks before the announcement.",
     "status": "confirmed", "type": "fact", "quote": None, "people": ["Avery Stone"], "private_people": ["Jordan Pike"],
     "denials": ["A spokesperson for Avery Stone denied any wrongdoing."],
     "sources": [{"url": D, "outlet": "Daily Ledger"}]},
    {"text": "Quantaline shares fell 6 percent in early trading after the announcement.", "status": "reported",
     "type": "fact", "quote": None, "people": [], "sources": [{"url": D, "outlet": "Daily Ledger"}]},
    {"text": "Quantaline was founded by Avery Stone in 2009 and employs more than 12,000 people.", "status": "confirmed",
     "type": "fact", "quote": None, "people": ["Avery Stone"], "sources": [{"url": N, "outlet": "Quantaline newsroom"}]},
    {"text": "A fabricated quote test", "status": "confirmed", "type": "fact",
     "quote": "This sentence never appeared in any source page at all.", "people": [],
     "sources": [{"url": N, "outlet": "Quantaline newsroom"}]},
]}

QUOTE = "I am proud of what this team has built, and I believe this is the right moment to step aside"


def script_60s() -> dict:
    """Hand-written 60-second fixture script (what a brain would return)."""
    S = [
        ("s001", 0, "vo", "hook", "On Monday, Quantaline said founder Avery Stone had stepped down as chief executive and left the board.", ["F001"]),
        ("s002", 0, "vo", "open_loop", "But one small detail in that announcement raised more questions than answers.", []),
        ("s003", 0, "title", "none", "The Exit", []),
        ("s004", 1, "chapter", "none", "The Announcement", []),
        ("s005", 1, "statement", "none", QUOTE, ["F002"]),
        ("s006", 1, "vo", "comment_prompt", "Should founders step aside once their board starts asking questions? Comment below.", []),
        ("s007", 1, "vo", "recap", "So far: Stone is out, and Morgan Lee is now the interim chief executive.", ["F003", "F001"]),
        ("s008", 1, "vo", "none", "According to the Daily Ledger, the board reviewed a conduct complaint for weeks. Stone's spokesperson denied wrongdoing.", ["F004"]),
        ("s009", 1, "vo", "recap", "Recap: a founder gone, a denied complaint, and shares reportedly down six percent.", ["F005", "F004"]),
        ("s010", 1, "vo", "none", "Our answer: boards must ask hard questions, even of founders. Subscribe for more.", []),
        ("s011", 1, "endscreen", "none", "WATCH NEXT", []),
    ]
    segs = []
    for sid, ch, kind, ret, text, fids in S:
        seg = {"id": sid, "chapter": ch, "kind": kind, "retention": ret, "text": text, "fact_ids": fids,
               "visual": {"intent": "subject_speaking" if kind == "vo" else "event", "prefer": ["footage"],
                          "keywords": ["stage", "office"]}}
        if sid == "s010":
            seg["answers_comment_prompt"] = True
            seg["opinion"] = True
        if sid == "s006":
            seg["opinion"] = True
        segs.append(seg)
    return {"segments": segs}


if __name__ == "__main__":
    print(source_clips(force="--force" in sys.argv))
    print(watermark_clip("corner"), watermark_clip("ticker"))
