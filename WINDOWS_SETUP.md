# Windows 11 setup (HP Victus · i5-13th gen · RTX 3050 6 GB · 32 GB RAM)

1. Copy the folder somewhere without spaces issues, e.g. `D:\Z Labs\N Labs`.
2. Double-click **Setup.bat**. It installs, *inside the folder*:
   - `uv` (Python manager) and a Python 3.12 `.venv`
   - ffmpeg + ffprobe static build → `bin\` (includes `h264_nvenc` for the RTX 3050)
   - portable Node.js → `bin\` (only if `node` isn't installed) — yt-dlp uses it as its JS runtime
   - Python packages from `requirements.txt`, `faster-whisper`, `onnxruntime-gpu` (CUDA if available)
   - `insightface` if your PC can build it (needs "Desktop development with C++" from Visual Studio Build Tools);
     otherwise OpenCV's SFace face model is used automatically (downloaded to `cache\faces\`)
   - Playwright Chromium (for JavaScript-heavy news pages)
   - empty key files in `%USERPROFILE%\.config\umf\` with a **user-only** ACL (icacls)
   - the rembg `u2net` cutout model (~176 MB) and a quick self-test
3. Paste your keys into `%USERPROFILE%\.config\umf\deepseek.env`, `ai33.env`, `brave.env` (or `tavily.env`).
4. Double-click **N Labs.bat**.

## GPU notes
- The encoder is auto-picked by test-encoding: `h264_nvenc` → `h264_videotoolbox` → `libx264`.
  Update the Nvidia driver if NVENC is not picked.
- Rendering is CPU (PIL/OpenCV) with `min(cpu_count-2, 8)` workers → 8 on the i5-13th gen.
- faster-whisper uses CUDA automatically when available (only needed when ai33 timings fail).

## Antivirus / SmartScreen
Windows may ask about `ffmpeg.exe` or `node.exe` in `bin\` the first time — allow them.

## Updating
Menu **7 Update tools** updates yt-dlp. To update everything, run `Setup.bat` again (it is safe to re-run).
