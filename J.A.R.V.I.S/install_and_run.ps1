# PowerShell script: install_and_run.ps1
# Creează mediu virtual, instalează dependențe și rulează JARVIS

$ErrorActionPreference = "Stop"

Write-Host "=== J.A.R.V.I.S. Installer & Runner ==="

# 1. Creează venv
if (!(Test-Path "jarvis-env")) {
    Write-Host "Creating virtual environment..."
    python -m venv jarvis-env
}

# 2. Activează venv
Write-Host "Activating virtual environment..."
.\jarvis-env\Scripts\Activate.ps1

# 3. Instalează dependențele
Write-Host "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Rulează Jarvis
Write-Host "Starting JARVIS..."
python jarvis_vosk_openai.py
