@echo off
REM N Labs.bat — Windows launcher menu for N Labs · UMF News Factory.
REM Runs everything with the project's own .venv (created by Setup.bat).
REM Keys live in %USERPROFILE%\.config\umf\*.env — never in this folder.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set PY=.venv\Scripts\python.exe
if not exist %PY% (echo Run Setup.bat first. & pause & exit /b 1)
set PATH=%~dp0bin;%PATH%
:menu
cls
echo ===========================================
echo    N Labs  ^·  UMF News Factory
echo ===========================================
echo  1  New video
echo  2  Resume run
echo  3  Approve script / plan (opens files)
echo  4  Choose brain   (current: !BRAIN!)
echo  5  Choose style   (current: !STYLE!)
echo  6  Self-test
echo  7  Update tools (yt-dlp)
echo  8  Open output folder
echo  9  Settings (config.json)
echo  0  Exit
set /p C=Choose: 
if "%C%"=="1" goto new
if "%C%"=="2" goto resume
if "%C%"=="3" goto approve
if "%C%"=="4" goto brain
if "%C%"=="5" goto style
if "%C%"=="6" (%PY% run.py --selftest & pause & goto menu)
if "%C%"=="7" (%PY% run.py --update-tools & pause & goto menu)
if "%C%"=="8" (start "" output & goto menu)
if "%C%"=="9" (start "" notepad config.json & goto menu)
if "%C%"=="0" exit /b 0
goto menu
:new
set /p T=Topic: 
set /p M=Minutes [20]: 
if "!M!"=="" set M=20
if "!STYLE!"=="" set STYLE=news_explainer
set B=
if not "!BRAIN!"=="" set B=--brain !BRAIN!
%PY% run.py "!T!" --style !STYLE! --minutes !M! !B!
pause
goto menu
:resume
%PY% run.py --list-runs
set /p R=Run id: 
set /p X=Allow more than 5,000 TTS characters? [y/N]: 
set CT=
if /i "!X!"=="y" set CT=--confirm-tts
%PY% run.py --resume !R! !CT!
pause
goto menu
:approve
%PY% run.py --list-runs
set /p R=Run id: 
start "" "output\!R!"
set /p G=Approve which gate (script/plan): 
%PY% run.py --resume !R! --approve !G!
pause
goto menu
:brain
echo deepseek / hive / anthropic / openai / manual
set /p BRAIN=Brain: 
goto menu
:style
%PY% run.py --list-styles
set /p STYLE=Style: 
goto menu
