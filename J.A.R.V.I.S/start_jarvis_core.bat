@echo off
setlocal EnableExtensions
cd /d "C:\Users\AlexandruM\Desktop\J.A.R.V.I.S"
if not exist "logs" mkdir "logs"
echo %date% %time% - JARVIS startup launched >> "logs\jarvis_startup.log"

REM Porneste HUD-ul, daca exista.
if exist "hud.py" start "JARVIS HUD" /min "C:\Users\AlexandruM\Desktop\J.A.R.V.I.S\jarvis-env\Scripts\python.exe" "hud.py" >> "logs\hud.log" 2>&1

REM Asteapta putin ca HUD-ul sa se initializeze.
timeout /t 2 /nobreak > nul

REM Porneste comenzile vocale cu wake word: Hey Jarvis.
start "JARVIS Voice" /min "C:\Users\AlexandruM\Desktop\J.A.R.V.I.S\jarvis-env\Scripts\python.exe" "simple_voice_commands.py" >> "logs\voice.log" 2>&1

echo %date% %time% - HUD and Voice modules started >> "logs\jarvis_startup.log"
exit /b 0
