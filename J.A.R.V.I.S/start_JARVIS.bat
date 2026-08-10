@echo off
title J.A.R.V.I.S Launcher
cd /d "%~dp0"

echo ===========================================
echo         J.A.R.V.I.S STARTUP
echo ===========================================
echo.

if not exist "jarvis-env\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    pause
    exit /b 1
)

call "jarvis-env\Scripts\activate.bat"

if not exist "logs" mkdir logs

if exist "hud.py" (
    echo Starting HUD...
    start "JARVIS HUD" python hud.py
)

timeout /t 2 >nul

if exist "simple_voice_commands.py" (
    echo Starting Voice Core...
    start "JARVIS Voice Core" python simple_voice_commands.py
)

timeout /t 2 >nul

if exist "jarvis_agent.py" (
    echo Starting JARVIS Agent...
    start "JARVIS Agent" python jarvis_agent.py
)

echo.
echo ===========================================
echo J.A.R.V.I.S started.
echo.
echo Wake command:
echo     Hey Jarvis
echo.
echo Shutdown command:
echo     Jarvis shutdown
echo ===========================================
pause
