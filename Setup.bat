@echo off
REM Setup.bat — one-time Windows 11 installer for N Labs. Everything installs INSIDE this folder:
REM uv + Python 3.12 (.venv), ffmpeg static build (bin\), portable Node.js (bin\node) if missing,
REM Python packages, models (rembg u2net, OCR, face), empty key files in %USERPROFILE%\.config\umf (user-only ACL).
setlocal
cd /d "%~dp0"
if not exist bin mkdir bin

echo [1/7] uv (Python manager)
where uv >nul 2>nul || powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
set PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%

echo [2/7] Python 3.12 virtual environment
uv venv --python 3.12 .venv || (echo uv failed & pause & exit /b 1)

echo [3/7] ffmpeg (static build into bin\)
if not exist bin\ffmpeg.exe (
  powershell -NoProfile -Command "Invoke-WebRequest https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip -OutFile bin\ffmpeg.zip"
  powershell -NoProfile -Command "Expand-Archive bin\ffmpeg.zip -DestinationPath bin\ff -Force"
  for /r bin\ff %%f in (ffmpeg.exe ffprobe.exe) do copy /y "%%f" bin\ >nul
  rmdir /s /q bin\ff & del bin\ffmpeg.zip
)

echo [4/7] Node.js (JS runtime for yt-dlp)
where node >nul 2>nul || (
  powershell -NoProfile -Command "Invoke-WebRequest https://nodejs.org/dist/v22.11.0/node-v22.11.0-win-x64.zip -OutFile bin\node.zip"
  powershell -NoProfile -Command "Expand-Archive bin\node.zip -DestinationPath bin -Force"
  move /y bin\node-v22.11.0-win-x64 bin\node >nul & del bin\node.zip
  copy /y bin\node\node.exe bin\ >nul
)

echo [5/7] Python packages
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
uv pip install --python .venv\Scripts\python.exe faster-whisper
uv pip install --python .venv\Scripts\python.exe onnxruntime-gpu 2>nul
uv pip install --python .venv\Scripts\python.exe insightface 2>nul || echo insightface skipped (needs C++ build tools) - OpenCV SFace will be used
.venv\Scripts\python.exe -m playwright install chromium

echo [6/7] API key files (user-only)
.venv\Scripts\python.exe run.py --init-keys
icacls "%USERPROFILE%\.config\umf" /inheritance:r /grant:r "%USERNAME%:(OI)(CI)F" >nul

echo [7/7] Models (rembg u2net, OCR, face models)
.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'.');from rembg import new_session;new_session('u2net');from nlabs.footage.faces import get_backend;print('face backend:',get_backend().name)"
.venv\Scripts\python.exe run.py --selftest --quick
echo.
echo Done. Put your keys in %USERPROFILE%\.config\umf\*.env and double-click "N Labs.bat".
pause
