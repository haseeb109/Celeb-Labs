#!/bin/bash
# setup.command — one-time macOS (Apple Silicon) / Linux installer for N Labs.
# Installs ffmpeg + node (Homebrew on Mac), creates .venv with Python 3.12, installs
# Python packages and models, and creates empty key files in ~/.config/umf/ (chmod 600).
set -e
cd "$(dirname "$0")"
if [[ "$(uname)" == "Darwin" ]]; then
  command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
  brew install ffmpeg node python@3.12 || true
fi
command -v ffmpeg >/dev/null || { echo "ffmpeg missing (Linux: sudo apt install ffmpeg)"; exit 1; }
if command -v uv >/dev/null; then
  uv venv --python 3.12 .venv
  PIP="uv pip install --python .venv/bin/python"
else
  python3.12 -m venv .venv || python3 -m venv .venv
  .venv/bin/python -m pip install -U pip
  PIP=".venv/bin/python -m pip install"
fi
$PIP -r requirements.txt
if [[ "$(uname)" == "Darwin" ]]; then $PIP mlx-whisper || true; else $PIP faster-whisper || true; fi
$PIP insightface || echo "insightface not installed — OpenCV SFace face matching will be used"
.venv/bin/python -m playwright install chromium || true
.venv/bin/python run.py --init-keys
.venv/bin/python - <<'PY'
# warm the model caches: rembg u2net, rapidocr, OpenCV face models
import sys; sys.path.insert(0, ".")
try:
    from rembg import new_session; new_session("u2net"); print("rembg u2net ready")
except Exception as e: print("rembg:", e)
try:
    from nlabs.footage.faces import get_backend; print("face backend:", get_backend().name)
except Exception as e: print("faces:", e)
PY
chmod +x "N Labs.command"
echo "Done. Put your keys in ~/.config/umf/*.env, then double-click 'N Labs.command'."
