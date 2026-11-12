# N Labs · UMF News Factory

A standalone desktop tool that turns **a news topic in plain text** into a finished, rule-checked,
**footage-heavy** YouTube video (default 20 min, 1080p30) plus thumbnails, metadata and a full audit trail.

```
python run.py "Jensen Huang resigns as Nvidia CEO" --style news_explainer --minutes 20
```

## Run it in under 5 minutes

1. **Install once** — Windows: double-click `Setup.bat`. Mac: double-click `setup.command`.
   Everything (Python 3.12 venv, ffmpeg, node, models) installs inside this folder.
2. **Add keys** — open `~/.config/umf/` (Windows: `%USERPROFILE%\.config\umf\`) and paste keys after the `=`:
   - `deepseek.env` (the brain, required unless you use `--brain manual`)
   - `ai33.env` (voice), `brave.env` **or** `tavily.env` **or** set `searxng_url` in `config.json` (search)
   - optional: `pexels.env`, `pixabay.env`, `flickr.env`, `gemini.env`, `anthropic.env`, `openai.env`, `hive.env`
   Keys never go in the project folder, logs or git.
3. **Self-test** — menu option 6 (or `python run.py --selftest`). All 12 tests should be green.
4. **Make a video** — double-click `N Labs.bat` / `N Labs.command` → **1 New video**.
   The run stops twice for you (approval gates): after the **script** and after the **edit plan**.
   Review the files it lists, then menu **3 Approve** (or `python run.py --resume <run_id> --approve script`).

## The stations

| # | Station | What it does | Main file |
|---|---|---|---|
| 1 | Research | 8–15 queries → search → fetch (robots respected) → facts with code-decided status and **verbatim-verified quotes** | `nlabs/research/station.py` |
| 2 | Official statements & posts | X posts via free oEmbed, newsroom statements → recreated cards; "has not commented" fact if none | `nlabs/research/official.py` |
| 3 | Script | outline → script → validator (L1–L5, S1, S3, retention beats, length ±3 %) with repair loop | `nlabs/script/` |
| 4 | Footage hunt | yt-dlp search, blocklist, tiers, subtitle mining, **partial** window downloads, shot detection, face match, watermark/OCR scan, scored pool | `nlabs/footage/` |
| 5 | Images | official press photos (with terms), Wikimedia, Flickr CC, Pexels/Pixabay, stills from footage | `nlabs/images/` |
| 6 | Voice | ai33.pro (polling, word timings) → Kokoro → OS voice; **5,000-char gate**; hash cache | `nlabs/voice/tts.py` |
| 7 | Edit plan | audio-driven shots, treatments, F1 ratios with automatic re-plan, contact sheet, overrides | `nlabs/edit/planner.py` |
| 8 | Render | 23 templates, word-by-word captions, credits, lower thirds, parallel segments, concat | `nlabs/render/` |
| 9 | Mix & encode | VO + soundbites + synthesized SFX + ducked music, −14 LUFS, NVENC/VideoToolbox/x264, size cap | `nlabs/audio/`, `render/encode.py` |
| 10 | Package & QC | 3 thumbnails, metadata (5 titles, chapters, sources, credits), footage log, qc.json, report | `nlabs/package/` |

## Outputs — `output/<YYYY-MM-DD>_<slug>/`

`video.mp4`, `thumbnail_1..3.jpg`, `metadata.txt`, `script.txt`, `script.json`, `fact_ledger.json`,
`footage_log.csv`, `image_credits.txt`, `contact_sheet_pool.jpg`, `contact_sheet_plan.jpg`,
`contact_sheet_final.jpg`, `edit_plan.json`, `edit_plan_overrides.json`, `research_report.md`,
`qc.json`, `run_report.md`, `usage.json`.

## Locked rules (enforced in code — config can only make them stricter)

| Rule | Where it is enforced |
|---|---|
| **F1** ≥65 % real footage/photos, ≤20 % animation, ≤15 % text cards | `edit/ratios.py` (planner re-plans; QC fails) |
| **F2** no third-party clip > 5.0 s on screen | `footage/scenes.py`, `footage/select.py`, planner, **hard assert** in `render/engine.py` |
| **F3** pool ≥ 3× needed seconds from ≥ 8 sources | `footage/hunt.py` (logged in run_report) |
| **F4** ≤4 clips & ≤15 s per Tier B/C source | `footage/select.py` (budget + validator), QC |
| **F5** treatments: split, framed, PiP, B&W, punch-in, text-over | `edit/treatments.py`, `render/templates/footage.py` |
| **F6** watermarks/logos/chyrons/burned captions → crop (≥70 %) or reject, never blur | `footage/watermark_scan.py` |
| **F7** news-channel blocklist (+ OCR brand detection on re-uploads) | `footage/blocklist.py` (built-ins can't be removed) |
| **F8** face match vs reference before a clip is presented as the subject | `footage/faces.py`, `footage/pool.py` |
| **S1–S4** official statements mandatory, recreated cards, verbatim quotes, outlets cited not shown | `research/`, `script/validate_script.py`, `render/templates/cards.py` |
| **L1–L6** fact ids, attribution, no private names, no AI faces, hypotheticals labelled, recency stamp | `research/ledger.py`, `script/validate_script.py`, `package/metadata.py` |
| **V1** stop before TTS if > 5,000 chars without `--confirm-tts` | `voice/tts.py` |
| **V2** TTS cached by sha1(voice + speed + text) | `voice/tts.py` |
| **P1–P3** resume markers, approval gates, footage_log.csv | `paths.py`, `pipeline.py`, `package/footage_log.py` |

## CLI

```
python run.py "<topic>" --style news_explainer --minutes 20
  --stage research|script|plan|render|all   stop after a stage
  --brain deepseek|hive|anthropic|openai|manual
  --auto                    skip approval gates (locked rules still apply)
  --confirm-tts             allow > 5,000 TTS characters
  --resume <run_id> [--approve script|plan]   --rerender-seg s042
  --reference-image face.jpg                face reference for the subject (F8)
  --posts posts_manual.json                 owner-supplied official post URLs/text
  --subject "Name"          override detected subject
  --footage-preview [--max-videos N]        run only the footage hunt (no keys needed)
  --list-styles  --list-runs  --selftest [--quick]  --update-tools  --init-keys
```

**Manual brain** (`--brain manual`): every prompt is written to `work/<run>/manual/<pass>_<n>.prompt.md`.
Paste the JSON reply into `<pass>_<n>.response.json` (e.g. from ChatGPT/Claude in the browser) and `--resume`.

**Swapping shots at the plan gate**: edit `output/<run>/edit_plan_overrides.json`:
`{"sh0012": {"clip_id": "<id from footage_pool>"}}` or `{"sh0012": {"image": "C:/pics/x.jpg", "credit": "..."}}`, then resume.

## Costs (typical 20-minute video)

- DeepSeek brain: ~150–250 k tokens in, ~40 k out → about **$0.10–0.15**
- ai33 TTS: ~17–19 k characters → needs `--confirm-tts` (V1). Price per 1 k chars is set in `config.json → prices`.
- Search: Brave/Tavily ~15 queries; SearXNG self-hosted is free.
- Everything else (yt-dlp, OCR, faces, render, music pad, SFX) is free and local.
`usage.json` and the `BRAIN USAGE` block show the real numbers per run.

## Troubleshooting

| Problem | Fix |
|---|---|
| `No search provider configured` | add `brave.env`/`tavily.env`, or set `searxng_url` |
| YouTube "Sign in to confirm you're not a bot" / 403 | menu 7 (update yt-dlp); run on a home connection; optional burner `cookies_file` in config.json |
| Pool below target (F3) | normal for niche topics; the planner fills with licensed photos and stills. It never breaks F2/F6/F7 to fill |
| `needs_review` after the script pass | the brain couldn't satisfy the validator; read `run.log`, try `--brain anthropic` or `--brain manual` |
| `awaiting_approval` | that's a gate: review the files, then `--resume <id> --approve script|plan` |
| Render crashed | just resume — finished segments are reused (hash-cached) |
| Video too large | automatic re-encode with lower maxrate until ≤ `max_output_gb` |

## Notes for the owner

- Rules F2/F4/F6/F7 **reduce** copyright and Content ID risk; they do not make third-party footage risk-free.
  Tier A (public domain) and Tier B (licensed) footage are the safest; the tool prefers them automatically.
  Keep `footage_log.csv` for every upload.
- Real-person stories carry defamation risk: **never skip the script approval gate on scandal topics.**
- Run downloads on a home/residential connection; cloud servers get blocked by YouTube and Flickr.
- Keep yt-dlp updated (menu option 7). It also self-updates at most once per 24 h.

See also: `WINDOWS_SETUP.md`, `ADDING_A_STYLE.md`, `DECISIONS.md`, `CHANGELOG.md`.
