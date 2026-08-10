@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ==========================================================
REM J.A.R.V.I.S Windows Auto Start Setup
REM Ruleaza acest fisier O SINGURA DATA din folderul principal J.A.R.V.I.S.
REM Dupa aceea, J.A.R.V.I.S va porni automat odata cu Windows.
REM ==========================================================

set "BASE_DIR=%~dp0"
set "BASE_DIR=%BASE_DIR:~0,-1%"

set "VENV_DIR=%BASE_DIR%\jarvis-env"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "PYTHONW_EXE=%VENV_DIR%\Scripts\pythonw.exe"

set "HUD_FILE=%BASE_DIR%\hud.py"
set "VOICE_FILE=%BASE_DIR%\simple_voice_commands.py"

set "LOG_DIR=%BASE_DIR%\logs"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

set "CORE_BAT=%BASE_DIR%\start_jarvis_core.bat"
set "HIDDEN_VBS=%BASE_DIR%\start_jarvis_hidden.vbs"
set "STARTUP_VBS=%STARTUP_DIR%\JARVIS_Auto_Start.vbs"

echo.
echo ==========================================================
echo              J.A.R.V.I.S AUTO START SETUP
echo ==========================================================
echo Folder proiect:
echo %BASE_DIR%
echo.

if not exist "%VENV_DIR%" (
    echo [ERROR] Nu gasesc mediul virtual:
    echo %VENV_DIR%
    echo.
    echo Creeaza/refa mediul virtual jarvis-env inainte:
    echo py -3.13 -m venv jarvis-env
    echo .\jarvis-env\Scripts\Activate.ps1
    echo pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Nu gasesc:
    echo %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%PYTHONW_EXE%" (
    echo [WARN] Nu gasesc pythonw.exe. Voi folosi python.exe.
    set "PYTHONW_EXE=%PYTHON_EXE%"
)

if not exist "%HUD_FILE%" (
    echo [WARN] Nu gasesc hud.py:
    echo %HUD_FILE%
    echo HUD-ul nu va porni pana nu exista acest fisier.
)

if not exist "%VOICE_FILE%" (
    echo [ERROR] Nu gasesc simple_voice_commands.py:
    echo %VOICE_FILE%
    echo Fara acest fisier J.A.R.V.I.S nu poate asculta Hey Jarvis.
    pause
    exit /b 1
)

if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
)

echo [1/4] Creez fisierul de pornire core...

> "%CORE_BAT%" echo @echo off
>> "%CORE_BAT%" echo setlocal EnableExtensions
>> "%CORE_BAT%" echo cd /d "%BASE_DIR%"
>> "%CORE_BAT%" echo if not exist "logs" mkdir "logs"
>> "%CORE_BAT%" echo echo %%date%% %%time%% - JARVIS startup launched ^>^> "logs\jarvis_startup.log"
>> "%CORE_BAT%" echo.
>> "%CORE_BAT%" echo REM Porneste HUD-ul, daca exista.
>> "%CORE_BAT%" echo if exist "hud.py" start "JARVIS HUD" /min "%PYTHON_EXE%" "hud.py" ^>^> "logs\hud.log" 2^>^&1
>> "%CORE_BAT%" echo.
>> "%CORE_BAT%" echo REM Asteapta putin ca HUD-ul sa se initializeze.
>> "%CORE_BAT%" echo timeout /t 2 /nobreak ^> nul
>> "%CORE_BAT%" echo.
>> "%CORE_BAT%" echo REM Porneste comenzile vocale cu wake word: Hey Jarvis.
>> "%CORE_BAT%" echo start "JARVIS Voice" /min "%PYTHON_EXE%" "simple_voice_commands.py" ^>^> "logs\voice.log" 2^>^&1
>> "%CORE_BAT%" echo.
>> "%CORE_BAT%" echo echo %%date%% %%time%% - HUD and Voice modules started ^>^> "logs\jarvis_startup.log"
>> "%CORE_BAT%" echo exit /b 0

echo [2/4] Creez launcher-ul ascuns...

> "%HIDDEN_VBS%" echo Set WshShell = CreateObject("WScript.Shell")
>> "%HIDDEN_VBS%" echo WshShell.Run Chr(34) ^& "%CORE_BAT%" ^& Chr(34), 0, False

echo [3/4] Adaug J.A.R.V.I.S in Windows Startup...

copy /Y "%HIDDEN_VBS%" "%STARTUP_VBS%" > nul

if errorlevel 1 (
    echo [ERROR] Nu am putut copia fisierul in Startup:
    echo %STARTUP_VBS%
    pause
    exit /b 1
)

echo [4/4] Pornesc J.A.R.V.I.S acum...

wscript "%HIDDEN_VBS%"

echo.
echo ==========================================================
echo                    SETUP COMPLET
echo ==========================================================
echo J.A.R.V.I.S va porni automat la urmatoarea pornire Windows.
echo.
echo Comanda vocala de activare:
echo   Hey Jarvis
echo.
echo Raspuns:
echo   Yes Sir, how may I help you today?
echo.
echo Comanda de inchidere:
echo   Jarvis shutdown
echo.
echo Fisiere create:
echo   %CORE_BAT%
echo   %HIDDEN_VBS%
echo   %STARTUP_VBS%
echo.
echo Loguri:
echo   %LOG_DIR%\jarvis_startup.log
echo   %LOG_DIR%\hud.log
echo   %LOG_DIR%\voice.log
echo.
echo Pentru dezactivare auto-start:
echo   sterge fisierul:
echo   %STARTUP_VBS%
echo.
pause
exit /b 0
