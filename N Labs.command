#!/bin/bash
# N Labs.command — macOS/Linux launcher menu for N Labs · UMF News Factory.
# Double-click in Finder (or run ./"N Labs.command"). Uses the project's .venv from setup.command.
# Keys live in ~/.config/umf/*.env — never in this folder.
cd "$(dirname "$0")"
PY=.venv/bin/python
[ -x "$PY" ] || { echo "Run setup.command first."; read -r; exit 1; }
export PATH="$PWD/bin:$PATH"
BRAIN=""; STYLE="news_explainer"
while true; do
  clear
  echo "==========================================="
  echo "   N Labs · UMF News Factory"
  echo "==========================================="
  echo " 1  New video"
  echo " 2  Resume run"
  echo " 3  Approve script / plan (opens files)"
  echo " 4  Choose brain   (current: ${BRAIN:-config})"
  echo " 5  Choose style   (current: $STYLE)"
  echo " 6  Self-test"
  echo " 7  Update tools (yt-dlp)"
  echo " 8  Open output folder"
  echo " 9  Settings (config.json)"
  echo " 0  Exit"
  read -r -p "Choose: " C
  case "$C" in
    1) read -r -p "Topic: " T; read -r -p "Minutes [20]: " M; M=${M:-20}
       $PY run.py "$T" --style "$STYLE" --minutes "$M" ${BRAIN:+--brain $BRAIN}; read -r -p "Enter to continue";;
    2) $PY run.py --list-runs; read -r -p "Run id: " R; read -r -p "Allow > 5,000 TTS chars? [y/N]: " X
       CT=""; [[ "$X" =~ ^[Yy] ]] && CT="--confirm-tts"; $PY run.py --resume "$R" $CT; read -r -p "Enter to continue";;
    3) $PY run.py --list-runs; read -r -p "Run id: " R; open "output/$R" 2>/dev/null || xdg-open "output/$R"
       read -r -p "Approve which gate (script/plan): " G; $PY run.py --resume "$R" --approve "$G"; read -r -p "Enter";;
    4) read -r -p "Brain (deepseek/hive/anthropic/openai/manual): " BRAIN;;
    5) $PY run.py --list-styles; read -r -p "Style: " STYLE;;
    6) $PY run.py --selftest; read -r -p "Enter to continue";;
    7) $PY run.py --update-tools; read -r -p "Enter to continue";;
    8) open output 2>/dev/null || xdg-open output;;
    9) open -e config.json 2>/dev/null || ${EDITOR:-nano} config.json;;
    0) exit 0;;
  esac
done
