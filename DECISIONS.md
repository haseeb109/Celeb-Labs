# DECISIONS — defaults chosen during the build, and why

## Platform & stack
- **Python 3.12 venv via `uv`** (falls back to venv+pip). The build machine had 3.13 system Python; the project venv is 3.12 as specified.
- **Rendering is CPU (PIL + OpenCV + numpy) with `min(cpu-2, 8)` process workers.** GPU is used for encoding (NVENC/VideoToolbox) only; it keeps the renderer identical on Windows/Mac/Linux.
- **Segments are encoded with the final encoder settings** and concatenated with `-c copy`; audio is muxed afterwards. This avoids a second lossy video encode. If the file is over `max_output_gb`, it is re-encoded with a lower maxrate (Section 11).
- **Encoder auto-pick test-encodes** a tiny clip with each encoder, because ffmpeg often *lists* `h264_nvenc` even with no Nvidia GPU.
- **HyperFrames/Playwright animated overlays and the FastAPI `--ui`** were not built (both optional in the spec). All graphics are frame-rendered in Python; this keeps installation small and the renderer deterministic.

## Locked rules
- All locked values live in `nlabs/constants.py`. `Config` passes every config value through `tighten()`: a looser value is silently replaced by the locked one (tested: `max_clip_seconds: 9` → 5.0, `tts_confirm_chars: 99999` → 5000).
- **F2 applies to every footage shot that is not the owner's own** (Tier A/B/C), and to clips used *behind* cards. Enforced four times: shot splitting (`scenes.py`), `SourceBudget`, planner, and a hard `assert_plan_rules()` before any frame is rendered.
- **F1 categories:** real footage, real photos, stills, soundbites and *cards that show real media* (split-screen card, title/chapter text over footage) count as footage — the spec says "with text over it all count". Text cards on plain backgrounds count as text; charts/timelines/counters count as animation.
- **F1 re-plan strategy:** if a plan misses F1, the planner re-plans with title/chapter/end cards placed over real footage/photos. If footage runs out, it fills with licensed photos/stills; plain text cards are the last resort and then QC reports `CHECK` (never breaks F2/F6/F7 to fill).
- **F4** counts per source *video* (video_id). Tier A is exempt from F4 but not F2.
- **F6 static-overlay detector** only trusts the temporal test when the sampled window has ≥2 distinct scenes or real motion; on a single static tripod shot the background would look like an overlay, so only OCR text is used there. Corners use 12 % side margins, top band 12 %, bottom band 22 %.
- **F6 crop** keeps the source aspect ratio (16:9) and must keep ≥70 % *area* and contain the main face; otherwise reject. Logos are never blurred.
- **F7** built-in names/ids are code constants; `footage/blocklist.json` can only add. Extra heuristics: prefix matching for long brand names ("Yahoo Finance and …"), news-like channel names with >500 k subscribers, OCR brand strings in frames, and **titles that name a news brand** ("… / CNBC Full Interview") as likely re-uploads.
- **F8** reference embedding: owner `--reference-image` first; else the dominant face cluster across Tier A / official-channel windows. With no face backend at all, no clip is ever *claimed* to show the subject (lower thirds naming the subject are only added on face-matched clips).
- **Face backend order:** insightface (buffalo_s) → face_recognition → **OpenCV YuNet + SFace** (added because insightface needs a C++ build on Windows; SFace ships with opencv-python and its ONNX models are tiny). SFace cosine threshold reuses 0.45.

## Research & facts
- **Status is decided in code** and the brain can only make a status *weaker*: primary source (gov/mil, allow-listed official domain, or a domain whose root label equals a capitalized entity in the topic, e.g. `nvidia` → nvidianews.nvidia.com) or ≥2 reputable outlets → confirmed; 1 outlet → reported; allegation wording → alleged; denials kept.
- **Sources must be pages we actually fetched**; invented URLs are dropped with their fact.
- **Quotes** are verified against fetched page text after normalizing whitespace, quote marks and dashes; unverified quotes are removed and listed in `research_report.md`.
- **Script quote check** accepts an exact excerpt of a ledger quote (shorter exact substring) — never a paraphrase.
- **Short videos:** retention beats scale with length (`target/1200`), with floors (teaser by hook+15 s, comment prompt by 30 s) so 60-second tests are meaningful.
- No keyless web-search fallback was added (DuckDuckGo/Bing scraping is fragile and against their terms); the owner sets SearXNG, Brave or Tavily.

## Voice
- `post` and `statement` segments are **spoken** (the narrator reads the exact verified text) as well as shown as cards.
- V1 counts only characters **not already in the TTS cache**, so a resumed run never re-asks for cached lines.
- Dummy TTS (tests) makes a quiet synthetic signal of `len/15` seconds so ducking and loudness are exercised.

## Edit, render, audio
- Footage shots target ~3.6 s (avg new visual ≤4.5 s), clamp 1.5–5.0 s; the same clip is not reused within 60 s.
- Captions are hidden on cards that already show the words (post/statement/quote/comment/title/chapter/end).
- Plan dry runs (`--stage plan` without `--confirm-tts`) use **estimated timings**; the plan is then re-made with real audio and the plan gate asks again. An approved plan from real audio is rendered exactly as reviewed (re-planned only if `edit_plan_overrides.json` changed after it).
- Music: licensed files in `assets/music/` listed in `LICENSES.csv`; if empty, a quiet generated drone pad (no license needed). ai33 Suno is left as a `music_source` option to add later.
- SFX are synthesized with numpy (whoosh, boom, typewriter, clock) — nothing downloaded.
- Loudness: two-pass `loudnorm` I=−14, TP=−1.5, LRA=11 on the final mix.
- rembg uses **u2net** explicitly (newer rembg defaults to a 1 GB model).

## Packaging
- Thumbnail hooks are chosen from ledger keywords (consequence / money / question) and drawn over a real cutout; if there is no still at all, the thumbnail is text-only.
- Titles/description come from the brain with a code fallback; chapters are taken from the **real rendered timeline**.

## Environment found during the build (cloud sandbox)
- YouTube *search* worked, but per-video metadata hit YouTube's "confirm you're not a bot" wall (cloud IP). The hunt now detects this after 3 videos, updates yt-dlp once, and stops with a clear message instead of wasting time. Most other hosts (search APIs, DeepSeek, Wikimedia, X oEmbed) were blocked by the sandbox network, so the real-topic dry run could not reach the plan gate here — see `run_report.md` of that run. On the owner's home connection with keys these stations run normally.
