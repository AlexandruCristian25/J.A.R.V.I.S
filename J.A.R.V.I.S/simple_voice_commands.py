import os
import sys
import json
import re
import time
import shutil
import string
import webbrowser
import subprocess
from jarvis_mark46_voice import speak as mark46_speak, speak_async, stop_voice

try:
    import winreg
except Exception:
    winreg = None

try:
    import speech_recognition as sr
except Exception:
    sr = None

# Mark XLVI voice integration uses jarvis_mark46_voice.py instead of pyttsx3.
pyttsx3 = None

try:
    from jarvis_agent import handle_command
except Exception as e:
    handle_command = None
    JARVIS_AGENT_IMPORT_ERROR = e
else:
    JARVIS_AGENT_IMPORT_ERROR = None


# ==========================================================
# JARVIS STRICT VOICE COMMAND ROUTER
# ==========================================================
# What this version does:
# 1. It executes only clear commands.
# 2. It does not send random recognized text to Ollama/LLM.
# 3. It asks confirmation for files/projects/risky actions.
# 4. It can open apps, websites, files, folders and projects.
# 5. It searches C:, D:, E:, USB sticks and external drives.
# ==========================================================

STRICT_MODE = True
REQUIRE_CONFIRMATION_FOR_FILES = False
REQUIRE_CONFIRMATION_FOR_PROJECTS = False
REQUIRE_CONFIRMATION_FOR_RISKY_ACTIONS = True
MAX_SEARCH_SECONDS = 35

# ==========================================================
# ENTERPRISE FAST VOICE / VAD SETTINGS
# ==========================================================
ENABLE_ENTERPRISE_VAD = True

# Lower value = hears quieter/farther voice.
# If your room is noisy, increase to 120-180.
VAD_ENERGY_THRESHOLD = 38

# Stops faster after you finish speaking.
VAD_PAUSE_THRESHOLD = 0.85

# Keeps short pauses inside a sentence.
VAD_NON_SPEAKING_DURATION = 0.18

# Calibrate once, quickly, at startup/first listen.
VAD_CALIBRATION_SECONDS = 0.15

# Do not recalibrate every loop; that caused delay and unstable sensitivity.
VAD_CALIBRATE_EVERY_LISTEN = False

# After calibration, force the threshold to stay sensitive.
VAD_FORCE_SENSITIVE_THRESHOLD = True
VAD_MAX_ENERGY_THRESHOLD = 85
VAD_MIN_ENERGY_THRESHOLD = 18

WAKE_PHRASE_LIMIT = 6
ACTIVE_PHRASE_LIMIT = 35
PUSH_TO_TALK_PHRASE_LIMIT = 40

WAKE_START_TIMEOUT = None
ACTIVE_START_TIMEOUT = 7
PUSH_TO_TALK_START_TIMEOUT = 7
MIN_COMMAND_WORDS = 1

# Debug can slow down the loop visually; keep it False for normal usage.
VAD_DEBUG = False

_MICROPHONE_CALIBRATED_ONCE = False
_LAST_CALIBRATION_TIME = 0

# ==========================================================
# PERSONAL VOICE PROFILE - ALEXANDRU
# ==========================================================
VOICE_PROFILE_NAME = "Alexandru"
VOICE_SENSITIVITY_MODE = "HIGH"
NATURAL_COMMAND_MODE = True
SILENT_PATHS_IN_RESPONSES = True

# ==========================================================
# ENTERPRISE TESTING / REFINEMENT MODE
# ==========================================================
VOICE_REFINEMENT_MODE = True
VOICE_COMMAND_LOG_FILE = "voice_command_history.json"
VOICE_CORRECTIONS_FILE = "voice_corrections.json"
VOICE_MAX_HISTORY = 300
VOICE_CONFIDENCE_MIN_WORDS = 1
VOICE_CONFIRM_AFTER_NORMALIZATION = False

HUD_STATUS_FILE = "hud_status.txt"
HUD_COMMAND_FILE = "hud_command.txt"
HUD_RESULT_FILE = "hud_result.txt"
HUD_VOICE_FILE = "voice_level.txt"

HUD_PROJECT_FILE = "hud_project.txt"
HUD_CURRENT_FILE = "hud_current_file.txt"
HUD_ACTION_FILE = "hud_action.txt"
HUD_AI_STATUS_FILE = "hud_ai_status.txt"

HUD_SECURITY_SCORE_FILE = "hud_security_score.txt"
HUD_PROJECT_SCORE_FILE = "hud_project_score.txt"
HUD_MEMORY_STATUS_FILE = "hud_memory_status.txt"
HUD_VISION_STATUS_FILE = "hud_vision_status.txt"
HUD_OLLAMA_STATUS_FILE = "hud_ollama_status.txt"


def write_hud_file(path, value):
    try:
        with open(path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(str(value))
    except Exception:
        pass


def update_hud(
    status=None,
    command=None,
    result=None,
    voice=None,
    project=None,
    current_file=None,
    action=None,
    ai_status=None,
    security_score=None,
    project_score=None,
    memory_status=None,
    vision_status=None,
    ollama_status=None
):
    if status is not None:
        write_hud_file(HUD_STATUS_FILE, status)

    if command is not None:
        write_hud_file(HUD_COMMAND_FILE, command)

    if result is not None:
        write_hud_file(HUD_RESULT_FILE, short_text(result, 220))

    if voice is not None:
        write_hud_file(HUD_VOICE_FILE, voice)

    if project is not None:
        write_hud_file(HUD_PROJECT_FILE, project)

    if current_file is not None:
        write_hud_file(HUD_CURRENT_FILE, current_file)

    if action is not None:
        write_hud_file(HUD_ACTION_FILE, action)

    if ai_status is not None:
        write_hud_file(HUD_AI_STATUS_FILE, ai_status)

    if security_score is not None:
        write_hud_file(HUD_SECURITY_SCORE_FILE, security_score)

    if project_score is not None:
        write_hud_file(HUD_PROJECT_SCORE_FILE, project_score)

    if memory_status is not None:
        write_hud_file(HUD_MEMORY_STATUS_FILE, memory_status)

    if vision_status is not None:
        write_hud_file(HUD_VISION_STATUS_FILE, vision_status)

    if ollama_status is not None:
        write_hud_file(HUD_OLLAMA_STATUS_FILE, ollama_status)


def short_text(text, limit=160):
    text = str(text).replace("\n", " ").strip()

    if len(text) <= limit:
        return text

    return text[:limit - 3] + "..."


def extract_first_score(text):
    """
    Extracts values like:
    Overall: 6.4/10
    Security: 5.0/10
    Score: 78%
    """
    text = str(text)

    patterns = [
        r"overall[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?\s*/\s*10)",
        r"security[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?\s*/\s*10)",
        r"score[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?\s*/\s*10)",
        r"score[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?\s*%)",
    ]

    lower = text.lower()

    for pattern in patterns:
        match = re.search(pattern, lower)

        if match:
            return match.group(1).replace(" ", "")

    return None


def extract_security_score(text):
    text = str(text)
    lower = text.lower()

    patterns = [
        r"security[^0-9]{0,30}([0-9]+(?:\.[0-9]+)?\s*/\s*10)",
        r"risk level[^a-zA-Z]{0,20}(low|medium|high)",
        r"security risk level[^a-zA-Z]{0,20}(low|medium|high)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lower)

        if match:
            return match.group(1).upper().replace(" ", "")

    if "high" in lower and "risk" in lower:
        return "HIGH"

    if "medium" in lower and "risk" in lower:
        return "MEDIUM"

    if "low" in lower and "risk" in lower:
        return "LOW"

    return None


def update_hud_from_command_result(command, result):
    lower_command = clean_text(command)
    result_text = str(result)

    project_score = None
    security_score = None
    vision_status = None
    memory_status = "SYNC"
    ollama_status = "READY"

    if any(word in lower_command for word in ["memory", "last", "continue", "resume", "remember"]):
        memory_status = "ACTIVE"

    if lower_command.startswith("score project "):
        project_score = extract_first_score(result_text) or "DONE"

    if (
        "security" in lower_command
        or "security report" in lower_command
        or "secure " in lower_command
        or "audit" in lower_command
        or "vulnerab" in lower_command
        or "api key" in lower_command
        or "password" in lower_command
        or "secret" in lower_command
        or "sql injection" in lower_command
        or "xss" in lower_command
        or "dangerous import" in lower_command
        or "roadmap" in lower_command
        or "architect" in lower_command
        or "release" in lower_command
        or "deployment" in lower_command
        or "maturity" in lower_command
        or "production readiness" in lower_command
        or "sprint" in lower_command
        or "what should i fix next" in lower_command
        or "dashboard" in lower_command
        or "go live" in lower_command
        or "release readiness" in lower_command
        or "deployment readiness" in lower_command
    ):
        security_score = extract_security_score(result_text) or "DONE"

    if (
        "screen" in lower_command
        or "code on screen" in lower_command
        or "error on screen" in lower_command
        or "current" in lower_command
    ):
        vision_status = "ACTIVE"

    if any(
        word in lower_command
        for word in [
            "analyze",
            "review",
            "score",
            "fix",
            "secure",
            "explain",
            "suggest",
            "report",
        ]
    ):
        ollama_status = "READY"

    update_hud(
        project_score=project_score,
        security_score=security_score,
        memory_status=memory_status,
        vision_status=vision_status,
        ollama_status=ollama_status,
    )

WAKE_WORDS = {
    "jarvis",
    "hey jarvis",
    "hey jervis",
    "okay jarvis",
    "ok jarvis",

    # Common STT mistakes for "Hey Jarvis"
    "hey jay",
    "hi jarvis",
    "play jarvis",
    "hey jar",
    "hey jha",
    "hay jarvis",
    "hey service",
    "hey travis",
    "hey charvis",
    "hey jars",
    "a jarvis",
    "hey alex",
    "jarvis please",
}

EXIT_COMMANDS = {
    "exit",
    "quit",
    "stop",
    "stop listening",
    "stop speaking",
    "stop voice",
    "silence",
    "shutdown",
    "shutdown jarvis",
    "jarvis shutdown",
    "jervis shutdown",
    "goodbye jarvis",
    "bye jarvis",
    "turn off jarvis",
    "close jarvis",
}

OPEN_PREFIXES = [
    "open website ",
    "open site ",
    "go to ",
    "visit ",
    "open app ",
    "open application ",
    "open program ",
    "open folder ",
    "open directory ",
    "open file ",
    "open document ",
    "open project ",
    "open code ",
    "open ",
]

SAFE_JARVIS_PREFIXES = [
    "score project ",
    "review project ",
    "analyze project ",
    "security review project ",
    "strict security analyzer project ",
    "suggest fixes for project ",
    "suggest fixes ",
    "export report ",
    "daily check",
    "daily project check",
    "smart daily check",
    "show projects",
    "refresh projects",
    "refresh deep project ",
    "find duplicates in project ",
    "find dead code in project ",
    "read file ",
    "preview file ",
    "safe preview file ",

    # Screen Vision
    "read screen",
    "analyze screen",
    "analyze my screen",
    "read terminal",
    "analyze terminal",
    "read browser",
    "analyze browser",
    "read code on screen",
    "review code on screen",
    "review this code",
    "find bugs on screen",
    "find the bug",
    "find bugs",
    "explain error on screen",
    "explain this error",
    "what error is on screen",
    "what is this error",
    "what is wrong here",
    "read error on screen",

    # AI Coding Assistant
    "fix file ",
    "fix project file ",
    "secure file ",
    "secure project file ",
    "apply safe patch project file ",
    "apply ai patch project file ",
    "auto improve project file ",
    "backup file ",
    "backup project file ",
    "restore backup file ",
    "restore backup project file ",
    "suggest safe patch file ",
    "suggest safe patch project file ",
    "list backups",

    # Step 4 - Current screen/current code workflow
    "scan current screen project",
    "analyze current code",
    "analyze current file",
    "find bug on current screen",
    "find bugs on current screen",
    "explain current error",
    "fix current error",
    "review current file",
    "review current project",
    "scan current project",
    "analyze current project",
    "fix what is on screen",
    "suggest fix from screen",
    "suggest fixes from screen",
    "what should i fix",

    # Step 6 / Step 7 - Iron Man Security Developer Mode
    "secure cyber shield ai",
    "secure cybershield ai",
    "secure cyber",
    "scan cyber shield ai",
    "scan cybershield ai",
    "scan cyber",
    "audit cyber shield ai",
    "audit cybershield ai",
    "audit cyber",
    "find vulnerabilities",
    "find vulnerabilities cyber shield ai",
    "find vulnerabilities cyber",
    "find api keys ",
    "scan api keys ",
    "find passwords ",
    "scan passwords ",
    "find hardcoded secrets ",
    "scan hardcoded secrets ",
    "find secrets ",
    "scan secrets ",
    "find sql injection ",
    "scan sql injection ",
    "find xss ",
    "scan xss ",
    "find dangerous imports ",
    "scan dangerous imports ",
    "full security audit ",
    "enterprise audit ",
    "scan entire project ",
    "generate security roadmap ",
    "security roadmap ",

    # Step 9 - Conversational Memory
    "what was i working on",
    "what was i working on last",
    "what project was i working on",
    "what project was i working on last",
    "what file did we review last",
    "what file did you review last",
    "what vulnerabilities did you find",
    "show last security report",
    "show last audit",
    "continue last audit",
    "continue last project",
    "resume last project",
    "resume last task",
    "continue last task",
    "what projects do you remember",
    "compare remembered projects",
    "memory summary",
    "show memory summary",

    # Step 10 - Deep Memory Integration
    "memory aware review ",
    "memory aware security review ",
    "project timeline ",
    "show project timeline ",
    "audit history",
    "audit history ",
    "vulnerability history",
    "vulnerability history ",
    "remembered fixes",
    "remembered fixes ",
    "project evolution ",
    "show project evolution ",
    "engineering session summary",
    "session summary",
    "continue previous session",
    "last 20 audits",
    "last vulnerabilities",
    "last vulnerabilities ",
    "last improvements",
    "last improvements ",

    # Step 12 - Generic Project Commander
    "plan project ",
    "project plan ",
    "architect project ",
    "project architect ",
    "become project architect ",
    "prepare release ",
    "release checklist ",
    "prepare deployment ",
    "deployment checklist ",
    "project maturity ",
    "estimate project maturity ",
    "production readiness ",
    "estimate production readiness ",
    "what should i fix next ",
    "what should i fix next project ",
    "next best improvements ",
    "highest risk vulnerabilities ",
    "high risk vulnerabilities ",
    "generate sprint plan ",
    "sprint plan ",
    "generate roadmap ",
    "generate project roadmap ",
    "project roadmap ",

    # Step 13 - Voice + Memory + Project Fusion
    "continue working on my last project",
    "continue working on last project",
    "continue working on the last project",
    "review the last project",
    "review my last project",
    "scan the last project",
    "audit the last project",
    "secure the last project",
    "improve the last project",
    "fix the last project",
    "optimize the last project",
    "generate roadmap for last project",
    "generate roadmap for the last project",
    "roadmap for last project",
    "prepare release for last project",
    "prepare deployment for last project",
    "production readiness for last project",
    "project maturity for last project",
    "what should we do next",
    "what should i do next",
    "what is next",
    "next task",
    "continue session",
    "resume session",
    "resume previous session",
    "continue previous session",

    # Step 31 - Voice Project Review / Enterprise Dashboards
    "review ",
    "security audit ",
    "production readiness ",
    "release readiness ",
    "deployment readiness ",
    "go live report ",
    "enterprise dashboard",
    "show enterprise dashboard",
    "show executive dashboard",
    "show kpi dashboard",
    "show release dashboard",
    "show debt dashboard",
    "show security dashboard",
    "show strongest projects",
    "show weakest projects",
    "show projects needing attention",
    "show all projects health",
    "show engineering dashboard",
    "show portfolio dashboard",
    "export enterprise dashboard",
    "export executive dashboard",
    "export all dashboards",

    # Step 33 - Command History & Error History
    "command history",
    "show command history",
    "last commands",
    "error history",
    "show error history",
    "last errors",
    "jarvis usage stats",
    "usage stats",
    "show usage stats",
    "clear old history",
    "clean old history",
    "export command history",
    "export history",
]

RISKY_WORDS = {
    "delete",
    "remove",
    "format",
    "wipe",
    "erase",
    "overwrite",
    "replace code",
    "paste code",
    "write code",
    "modify file",
    "edit file",
}

BAD_RECOGNITION_PATTERNS = {
    "/no_think",
    "call project",
    "fibres",
    "fiber",
    "fibre",
}

APP_ALIASES = {
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "notepad": ["notepad.exe"],
    "paint": ["mspaint.exe"],
    "powershell": ["powershell.exe"],
    "command prompt": ["cmd.exe"],
    "cmd": ["cmd.exe"],
    "file explorer": ["explorer.exe"],
    "explorer": ["explorer.exe"],
    "task manager": ["taskmgr.exe"],
    "control panel": ["control.exe"],
    "settings": ["ms-settings:"],
    "calendar": ["outlookcal:", "ms-calendar:"],

    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "chrome.exe",
    ],
    "google chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "chrome.exe",
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "msedge.exe",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        "firefox.exe",
    ],
    "vscode": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        "code",
        "code.cmd",
    ],
    "visual studio code": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        "code",
        "code.cmd",
    ],
    "word": ["winword.exe"],
    "excel": ["excel.exe"],
    "powerpoint": ["powerpnt.exe"],
    "spotify": [
        os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
        "spotify.exe",
    ],
    "steam": [
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
        "steam.exe",
    ],
}

APP_CORRECTIONS = {
    "computer": "calculator",
    "calculate": "calculator",
    "calculation": "calculator",
    "fire": "firefox",
    "browser": "chrome",
    "code": "vscode",
    "vs code": "vscode",
    "visual studio": "visual studio code",
}

WEBSITE_ALIASES = {
    "google": "google.com",
    "youtube": "youtube.com",
    "you tube": "youtube.com",
    "gmail": "gmail.com",
    "github": "github.com",
    "git hub": "github.com",
    "chatgpt": "chat.openai.com",
    "chat gpt": "chat.openai.com",
    "openai": "openai.com",
    "open ai": "openai.com",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "linkedin": "linkedin.com",
    "linked in": "linkedin.com",
    "wikipedia": "wikipedia.org",
    "wiki": "wikipedia.org",
    "stackoverflow": "stackoverflow.com",
    "stack overflow": "stackoverflow.com",
    "reddit": "reddit.com",
    "w3schools": "w3schools.com",
    "mdn": "developer.mozilla.org",
    "mozilla": "developer.mozilla.org",
    "emag": "emag.ro",
    "olx": "olx.ro",
    "yahoo": "yahoo.com",
    "yahoo mail": "mail.yahoo.com",
    "yahoomail": "mail.yahoo.com",
    "mail yahoo": "mail.yahoo.com",
    "outlook": "outlook.live.com",
    "hotmail": "outlook.live.com",
}

FOLDER_ALIASES = {
    "desktop": "Desktop",
    "downloads": "Downloads",
    "download": "Downloads",
    "documents": "Documents",
    "document": "Documents",
    "pictures": "Pictures",
    "images": "Pictures",
    "music": "Music",
    "videos": "Videos",
}

PROJECT_ALIASES = {
    "cyber shield ai": "CyberShield AI",
    "cybershield ai": "CyberShield AI",
    "cyber shield": "CyberShield AI",
    "cyber": "CyberShield AI",
    "jarvis": "J.A.R.V.I.S",
    "jervis": "J.A.R.V.I.S",
    "jar": "J.A.R.V.I.S",
    "project jar": "J.A.R.V.I.S",
    "projector": "J.A.R.V.I.S",
}

PROJECT_FOLDER_ALIASES = {
    "CyberShield AI": [
        "CyberShield_AI_Enterprise_Hardened_Enhanced",
        "CyberShield AI",
        "Cyber Security App",
        "CyberShield",
        "Hardened",
        "Enhanced",
    ],
    "J.A.R.V.I.S": [
        "J.A.R.V.I.S",
        "JARVIS",
        "Jarvis",
        "J.A.R.V.I.S Agent",
        "JARVIS Voice",
    ],
}

SKIP_DIRS = {
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "$recycle.bin",
    "system volume information",
    "node_modules",
    "venv",
    ".venv",
    "jarvis-env",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".cache",
}

# Mark XLVI voice integration.
# Voice engine: EdgeTTS
# Default voice: en-US-GuyNeural
tts_engine = "mark46_edgetts"


def speak(text):
    """
    Speaks with the Mark XLVI voice adapter.

    Required file in the same folder:
    - jarvis_mark46_voice.py

    Required packages:
    - edge-tts
    - miniaudio
    - sounddevice
    - numpy
    """
    text = str(text).strip()

    if not text:
        return

    print(f"\nJARVIS:\n{text}\n")

    spoken_text = short_text(text, 320)

    try:
        mark46_speak(spoken_text)
    except Exception as error:
        print(f"[VOICE] Mark XLVI voice error: {error}")
        if "edge_tts" in str(error) or "edge-tts" in str(error):
            print("[VOICE] Fix: python -m pip install edge-tts miniaudio sounddevice numpy")


def speak_background(text):
    """
    Non-blocking Mark XLVI voice.
    Useful if you want JARVIS to speak while the terminal continues running.
    """
    text = str(text).strip()

    if not text:
        return None

    print(f"\nJARVIS:\n{text}\n")

    try:
        return speak_async(text)
    except Exception as error:
        print(f"[VOICE] Mark XLVI async voice error: {error}")
        return None


def stop_speaking():
    """
    Stops current Mark XLVI voice playback.
    """
    try:
        stop_voice()
    except Exception as error:
        print(f"[VOICE] Stop voice error: {error}")


def clean_text(text):
    text = str(text).lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" dot ", ".")
    text = text.replace(" point ", ".")
    text = text.replace(" slash ", "/")
    return text.strip()




def collapse_repeated_command_words(text):
    """
    Fixes STT duplicates like:
    - open open firefox -> open firefox
    - jarvis jarvis open chrome -> jarvis open chrome
    """
    text = clean_text(text)

    if not text:
        return ""

    words = text.split()
    cleaned_words = []

    for word in words:
        if cleaned_words and cleaned_words[-1] == word:
            continue
        cleaned_words.append(word)

    cleaned = " ".join(cleaned_words)

    repeated_phrases = [
        ("open open ", "open "),
        ("jarvis jarvis ", "jarvis "),
        ("hey hey ", "hey "),
        ("please please ", "please "),
    ]

    changed = True

    while changed:
        changed = False

        for wrong, right in repeated_phrases:
            if wrong in cleaned:
                cleaned = cleaned.replace(wrong, right)
                changed = True

    return cleaned.strip()


def normalize_wake_transcript(text):
    """
    Converts common STT wake-word mistakes into 'hey jarvis' or 'jarvis'.
    """
    text = collapse_repeated_command_words(text)

    replacements = {
        "hey jay": "hey jarvis",
        "hi jarvis": "hey jarvis",
        "play jarvis": "hey jarvis",
        "hey jar": "hey jarvis",
        "hey jha": "hey jarvis",
        "hay jarvis": "hey jarvis",
        "hey jervis": "hey jarvis",
        "hey service": "hey jarvis",
        "hey travis": "hey jarvis",
        "hey charvis": "hey jarvis",
        "hey jars": "hey jarvis",
        "a jarvis": "hey jarvis",
        "jervis": "jarvis",
    }

    if text in replacements:
        return replacements[text]

    text = re.sub(
        r"\b(hey|hi|hay|play|a)\s+(jay|jar|jha|jervis|service|travis|charvis|jars|jarvis)\b",
        "hey jarvis",
        text
    )

    text = re.sub(r"\bjervis\b", "jarvis", text)

    return text.strip()


def starts_with_wake_variant(text):
    """
    True if text starts with a wake word or common wake transcription.
    """
    normalized = normalize_wake_transcript(text)

    if normalized in WAKE_WORDS:
        return True

    if normalized == "hey jarvis" or normalized == "jarvis":
        return True

    if normalized.startswith("hey jarvis "):
        return True

    if normalized.startswith("jarvis "):
        return True

    return False



def remove_wake_word(text):
    text = normalize_wake_transcript(text)

    for wake in sorted(WAKE_WORDS, key=len, reverse=True):
        wake = clean_text(wake)

        if text == wake:
            return ""

        if text.startswith(wake + " "):
            return text[len(wake):].strip()

    if text.startswith("hey jarvis "):
        return text[len("hey jarvis "):].strip()

    if text.startswith("jarvis "):
        return text[len("jarvis "):].strip()

    return text



def display_name_from_target(target):
    text = str(target or "").strip().strip('"')

    if not text:
        return "item"

    text = text.replace("\\", "/").rstrip("/")

    if "/" in text:
        text = text.split("/")[-1]

    return text or "item"


def friendly_open_message(kind, target):
    name = display_name_from_target(target)

    pretty = {
        "vscode": "VS Code",
        "visual studio code": "VS Code",
        "chrome": "Chrome",
        "google chrome": "Chrome",
        "firefox": "Firefox",
        "edge": "Microsoft Edge",
        "file explorer": "File Explorer",
        "explorer": "File Explorer",
        "downloads": "Downloads",
        "documents": "Documents",
        "desktop": "Desktop",
        "pictures": "Pictures",
        "cybershield ai": "CyberShield AI",
        "cyber shield ai": "CyberShield AI",
        "jarvis": "J.A.R.V.I.S",
        "j.a.r.v.i.s": "J.A.R.V.I.S",
    }

    clean = clean_text(name)
    name = pretty.get(clean, name)

    return f"Opening {name}"


def normalize_personal_command(text):
    text = collapse_repeated_command_words(text)
    text = normalize_wake_transcript(text)
    text = clean_text(text)

    if not text:
        return ""

    exact = {
        "open fire": "open firefox",
        "open fox": "open firefox",
        "open firefox browser": "open firefox",
        "open google": "open website google",
        "open you tube": "open website youtube",
        "open youtube": "open website youtube",
        "open git hub": "open website github",
        "open github": "open website github",
        "open chat gpt": "open website chatgpt",
        "open chatgpt": "open website chatgpt",
        "open vs": "open vscode",
        "open vs code": "open vscode",
        "open visual studio code": "open vscode",
        "open code": "open vscode",
        "open project cyber": "open project CyberShield AI",
        "open project cyber shield": "open project CyberShield AI",
        "open project cyber shield ai": "open project CyberShield AI",
        "open project cybershield": "open project CyberShield AI",
        "open project cybershield ai": "open project CyberShield AI",
        "open jarvis": "open project J.A.R.V.I.S",
        "open project jarvis": "open project J.A.R.V.I.S",
        "show project": "show projects",
        "show projects": "show projects",
        "list projects": "show projects",
        "find project cyber": "find project CyberShield AI",
        "where is project cyber": "where is project CyberShield AI",
        "review cyber": "review project CyberShield AI",
        "review cyber shield": "review project CyberShield AI",
        "review cyber shield ai": "review project CyberShield AI",
        "security cyber": "full security audit CyberShield AI",
        "audit cyber": "full security audit CyberShield AI",
        "scan cyber": "full security audit CyberShield AI",
        "score cyber": "score project CyberShield AI",
        "score cyber shield": "score project CyberShield AI",
        "score cyber shield ai": "score project CyberShield AI",
        "make word report cyber": "review project CyberShield AI and create word report",
        "make pdf report cyber": "review project CyberShield AI and create pdf report",
        "create word report cyber": "review project CyberShield AI and create word report",
        "create pdf report cyber": "review project CyberShield AI and create pdf report",
        "create report cyber": "review project CyberShield AI and create pdf report",
    }

    if text in exact:
        return exact[text]

    text = re.sub(r"\bopen\s+(fire|fox)\b", "open firefox", text)
    text = re.sub(r"\bopen\s+(vs|vs code|visual studio code|code)\b", "open vscode", text)
    text = re.sub(r"\bcyber\s+shield\s+ai\b", "CyberShield AI", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcybershield\s+ai\b", "CyberShield AI", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcybers\s+in\s+the\b", "CyberShield AI", text)
    text = re.sub(r"\bproject\s+cyber\b", "project CyberShield AI", text)
    text = re.sub(r"\bfor\s+cyber\b", "for CyberShield AI", text)
    text = re.sub(r"\bfrom\s+cyber\b", "from CyberShield AI", text)

    if "report" in text and "cyber" in text:
        if "word" in text or "doc" in text or "docx" in text:
            return "review project CyberShield AI and create word report"
        if "pdf" in text:
            return "review project CyberShield AI and create pdf report"
        if "powerpoint" in text or "ppt" in text or "presentation" in text:
            return "review project CyberShield AI and create powerpoint report"
        if "excel" in text or "xls" in text:
            return "review project CyberShield AI and create excel report"
        return "review project CyberShield AI and create pdf report"

    return text.strip()






# ==========================================================
# ENTERPRISE VOICE REFINEMENT HELPERS
# ==========================================================
def _voice_safe_load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            return json.load(file)
    except Exception:
        return default if default is not None else {}


def _voice_safe_save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def log_voice_command(raw_text, normalized_text, result=None):
    if not VOICE_REFINEMENT_MODE:
        return

    data = _voice_safe_load_json(VOICE_COMMAND_LOG_FILE, [])

    if not isinstance(data, list):
        data = []

    data.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "raw": str(raw_text or ""),
        "normalized": str(normalized_text or ""),
        "result": short_text(result or "", 260),
    })

    data = data[-VOICE_MAX_HISTORY:]
    _voice_safe_save_json(VOICE_COMMAND_LOG_FILE, data)


def load_voice_corrections():
    data = _voice_safe_load_json(VOICE_CORRECTIONS_FILE, {})

    if not isinstance(data, dict):
        return {}

    return {
        clean_text(key): str(value).strip()
        for key, value in data.items()
        if str(key).strip() and str(value).strip()
    }


def save_voice_correction(wrong, right):
    wrong = clean_text(wrong)
    right = str(right or "").strip()

    if not wrong or not right:
        return "Missing correction."

    data = load_voice_corrections()
    data[wrong] = right

    _voice_safe_save_json(VOICE_CORRECTIONS_FILE, data)

    return f"Voice correction saved: {wrong} -> {right}"


def apply_saved_voice_corrections(text):
    cleaned = clean_text(text)
    corrections = load_voice_corrections()

    if cleaned in corrections:
        return corrections[cleaned]

    for wrong, right in corrections.items():
        if wrong and wrong in cleaned:
            cleaned = cleaned.replace(wrong, clean_text(right))

    return cleaned.strip()


def normalize_report_command(text):
    lower = clean_text(text)

    if "report" not in lower and "presentation" not in lower and "spreadsheet" not in lower:
        return text

    project = "CyberShield AI" if any(token in lower for token in ["cyber", "cybershield", "cyber shield"]) else get_last_project_from_memory()

    if any(word in lower for word in ["word", "doc", "docx"]):
        return f"create word report for project {project}"

    if any(word in lower for word in ["powerpoint", "ppt", "pptx", "presentation"]):
        return f"create powerpoint report for project {project}"

    if any(word in lower for word in ["excel", "xls", "xlsx", "spreadsheet"]):
        return f"create excel report for project {project}"

    if any(word in lower for word in ["pdf"]):
        return f"create pdf report for project {project}"

    return f"create pdf report for project {project}"


def normalize_open_anything_command(text):
    lower = clean_text(text)

    # Natural website requests
    web_patterns = [
        (r"^(?:go to|visit|open site|open website)\s+(.+)$", "open website"),
        (r"^(?:open)\s+(google|youtube|you tube|github|git hub|chatgpt|chat gpt|gmail|linkedin|facebook|instagram|reddit|stackoverflow|stack overflow|wikipedia|yahoo mail|outlook)$", "open website"),
    ]

    for pattern, prefix in web_patterns:
        match = re.match(pattern, lower)
        if match:
            return f"{prefix} {match.group(1).strip()}"

    # Natural app requests
    app_aliases = {
        "visual studio community": "visual studio community",
        "visual studio": "visual studio community",
        "vs community": "visual studio community",
        "vs code": "vscode",
        "visual studio code": "vscode",
        "code": "vscode",
        "fire": "firefox",
        "fox": "firefox",
        "mozilla": "firefox",
        "browser": "chrome",
        "google browser": "chrome",
        "file manager": "file explorer",
        "files": "file explorer",
        "terminal": "powershell",
        "windows terminal": "powershell",
    }

    for spoken, app in app_aliases.items():
        if lower == f"open {spoken}" or lower == f"launch {spoken}" or lower == f"start {spoken}":
            return f"open application {app}"

    # Folder shortcuts
    if lower in {"open downloads", "show downloads", "downloads"}:
        return "open folder downloads"

    if lower in {"open documents", "show documents", "documents"}:
        return "open folder documents"

    if lower in {"open desktop", "show desktop", "desktop"}:
        return "open folder desktop"

    return text


def normalize_enterprise_voice_command(text):
    """
    Final normalization layer used before routing.
    Keeps the old logic, but adds:
    - saved corrections
    - better report commands
    - better website/app/folder commands
    - project aliases
    """
    command = str(text or "").strip()

    if not command:
        return ""

    command = apply_saved_voice_corrections(command)
    command = normalize_wake_transcript(command)
    command = collapse_repeated_command_words(command)
    command = normalize_open_anything_command(command)
    command = normalize_personal_command(command)
    command = normalize_report_command(command)

    # Make sure common project phrases are stable.
    command = re.sub(r"\bcyber\s+shield\s+ai\b", "CyberShield AI", command, flags=re.IGNORECASE)
    command = re.sub(r"\bcybershield\s+ai\b", "CyberShield AI", command, flags=re.IGNORECASE)
    command = re.sub(r"\bcyber\s+project\b", "project CyberShield AI", command, flags=re.IGNORECASE)

    return command.strip()


def voice_refinement_status():
    history = _voice_safe_load_json(VOICE_COMMAND_LOG_FILE, [])
    corrections = load_voice_corrections()

    if not isinstance(history, list):
        history = []

    output = [
        "VOICE REFINEMENT STATUS",
        f"Commands logged: {len(history)}",
        f"Saved corrections: {len(corrections)}",
        "",
        "Recent commands:"
    ]

    for item in history[-10:]:
        output.append(
            f"- {item.get('timestamp', '')} | "
            f"raw: {item.get('raw', '')} | "
            f"normalized: {item.get('normalized', '')}"
        )

    if corrections:
        output.append("")
        output.append("Corrections:")
        for wrong, right in list(corrections.items())[-20:]:
            output.append(f"- {wrong} -> {right}")

    return "\n".join(output)


def handle_voice_meta_command(command):
    lower = clean_text(command)

    if lower in {"voice status", "voice refinement status", "show voice status", "show voice corrections"}:
        return voice_refinement_status()

    # Example:
    # remember voice correction open fire means open firefox
    match = re.match(
        r"^(?:remember|save)\s+voice\s+correction\s+(.+?)\s+(?:means|as|to)\s+(.+)$",
        command,
        flags=re.IGNORECASE
    )

    if match:
        return save_voice_correction(match.group(1).strip(), match.group(2).strip())

    return None


def normalize_project_name(text):
    lower = clean_text(text)

    for wrong, right in PROJECT_ALIASES.items():
        if wrong in lower:
            return right

    return str(text).strip()


# ==========================
# STEP 13 - VOICE + MEMORY + PROJECT FUSION HELPERS
# ==========================
def get_last_project_from_memory():
    """
    Best-effort resolver for natural phrases:
    last project / previous project / current project.
    It never blocks voice commands if memory modules are unavailable.
    """
    candidates = []

    try:
        from project_memory import last_project_name
        value = last_project_name()

        if value:
            candidates.append(value)
    except Exception:
        pass

    try:
        from deep_project_memory import what_was_i_working_on_last
        text = str(what_was_i_working_on_last())

        for line in text.splitlines():
            line = line.strip()

            if line and not line.lower().startswith(("last", "files", "tech", "project:", "path:")):
                candidates.append(line)
                break
    except Exception:
        pass

    try:
        from deep_project_memory import last_deep_project
        text = str(last_deep_project())

        for line in text.splitlines():
            line = line.strip()

            if line and not line.lower().startswith(("last", "files", "tech", "project:", "path:")):
                candidates.append(line)
                break
    except Exception:
        pass

    for candidate in candidates:
        candidate = str(candidate).strip()

        if candidate and "no " not in candidate.lower():
            return candidate

    return "CyberShield AI"


def resolve_memory_project_reference(command):
    """
    Converts natural memory references into concrete project commands.
    Examples:
    - generate roadmap for last project
    - prepare release for previous project
    - production readiness for current project
    """
    text = str(command).strip()
    lower = clean_text(text)

    memory_refs = [
        "last project",
        "previous project",
        "current project",
        "the last project",
        "my last project",
        "the previous project",
        "my previous project",
    ]

    if not any(ref in lower for ref in memory_refs):
        return None

    project_name = get_last_project_from_memory()

    phrase_routes = [
        ("continue working", f"autonomous improve {project_name}"),
        ("review", f"autonomous review {project_name}"),
        ("scan", f"full security audit {project_name}"),
        ("audit", f"full security audit {project_name}"),
        ("secure", f"autonomous secure {project_name}"),
        ("improve", f"autonomous improve {project_name}"),
        ("fix", f"autonomous fix {project_name}"),
        ("optimize", f"autonomous optimize {project_name}"),
        ("roadmap", f"plan project {project_name}"),
        ("plan", f"plan project {project_name}"),
        ("architect", f"architect project {project_name}"),
        ("release", f"prepare release {project_name}"),
        ("deployment", f"prepare deployment {project_name}"),
        ("production readiness", f"production readiness {project_name}"),
        ("maturity", f"project maturity {project_name}"),
        ("what should", f"what should i fix next {project_name}"),
        ("next", f"what should i fix next {project_name}"),
    ]

    for marker, routed in phrase_routes:
        if marker in lower:
            return routed

    if "continue" in lower or "resume" in lower:
        return "continue previous session"

    return f"autonomous review {project_name}"


def resolve_what_next_command(command):
    lower = clean_text(command)

    if lower in {
        "what should we do next",
        "what should i do next",
        "what is next",
        "next task",
        "continue session",
        "resume session",
        "resume previous session",
        "continue previous session",
    }:
        if "session" in lower:
            return "continue previous session"

        project_name = get_last_project_from_memory()
        return f"what should i fix next {project_name}"

    return None



# ==========================
# STEP 31 - VOICE PROJECT REVIEW HELPERS
# Natural voice commands for project reviews, dashboards, release readiness.
# ==========================
def resolve_step31_voice_project_command(command):
    lower = clean_text(command)

    # Global dashboards without project name.
    exact_global_routes = {
        "enterprise dashboard": "show enterprise dashboard",
        "show enterprise dashboard": "show enterprise dashboard",
        "executive dashboard": "show executive dashboard",
        "show executive dashboard": "show executive dashboard",
        "kpi dashboard": "show kpi dashboard",
        "show kpi dashboard": "show kpi dashboard",
        "release dashboard": "show release dashboard",
        "show release dashboard": "show release dashboard",
        "debt dashboard": "show debt dashboard",
        "show debt dashboard": "show debt dashboard",
        "security dashboard": "show security dashboard",
        "show security dashboard": "show security dashboard",
        "show strongest projects": "show strongest projects",
        "show weakest projects": "show weakest projects",
        "show projects needing attention": "show projects needing attention",
        "show all projects health": "show all projects health",
        "show engineering dashboard": "show engineering dashboard",
        "engineering dashboard": "show engineering dashboard",
        "show portfolio dashboard": "show portfolio dashboard",
        "portfolio dashboard": "show portfolio dashboard",
        "export enterprise dashboard": "export enterprise dashboard",
        "export executive dashboard": "export executive dashboard",
        "export all dashboards": "export all dashboards",
    }

    if lower in exact_global_routes:
        return exact_global_routes[lower]

    # Natural project commands.
    project_routes = [
        ("review ", "review project "),
        ("review project ", "review project "),
        ("analyze ", "analyze project "),
        ("analyze project ", "analyze project "),
        ("security audit ", "full security audit "),
        ("audit ", "full security audit "),
        ("secure ", "full security audit "),
        ("production readiness ", "production readiness "),
        ("release readiness ", "release readiness "),
        ("deployment readiness ", "deployment readiness "),
        ("go live report ", "go live report "),
        ("go live ", "go live report "),
        ("enterprise readiness ", "enterprise readiness "),
    ]

    for spoken_prefix, routed_prefix in project_routes:
        if lower.startswith(spoken_prefix):
            target = command[len(spoken_prefix):].strip()

            if target:
                return routed_prefix + normalize_project_name(target)

    # Natural "for <project>" variants.
    for marker, routed_prefix in [
        ("production readiness for ", "production readiness "),
        ("release readiness for ", "release readiness "),
        ("deployment readiness for ", "deployment readiness "),
        ("go live report for ", "go live report "),
        ("security audit for ", "full security audit "),
        ("review for ", "review project "),
    ]:
        if lower.startswith(marker):
            target = command[len(marker):].strip()

            if target:
                return routed_prefix + normalize_project_name(target)

    # Common CyberShield shortcuts.
    if lower in {
        "review cyber",
        "review cyber shield",
        "review cyber shield ai",
        "review cybershield ai",
    }:
        return "review project CyberShield AI"

    if lower in {
        "security audit cyber",
        "security audit cyber shield",
        "security audit cyber shield ai",
        "audit cyber",
        "audit cyber shield ai",
    }:
        return "full security audit CyberShield AI"

    if lower in {
        "production readiness cyber",
        "production readiness cyber shield ai",
    }:
        return "production readiness CyberShield AI"

    if lower in {
        "release readiness cyber",
        "release readiness cyber shield ai",
    }:
        return "release readiness CyberShield AI"

    if lower in {
        "deployment readiness cyber",
        "deployment readiness cyber shield ai",
    }:
        return "deployment readiness CyberShield AI"

    if lower in {
        "go live cyber",
        "go live report cyber",
        "go live cyber shield ai",
        "go live report cyber shield ai",
    }:
        return "go live report CyberShield AI"

    return None


def is_step31_dashboard_command(command):
    lower = clean_text(command)

    dashboard_markers = [
        "dashboard",
        "strongest projects",
        "weakest projects",
        "projects needing attention",
        "all projects health",
    ]

    return any(marker in lower for marker in dashboard_markers)


def normalize_command(command):
    command = remove_wake_word(command)
    command = clean_text(command)
    command = normalize_wake_transcript(command)
    command = collapse_repeated_command_words(command)
    command = normalize_personal_command(command)
    command = normalize_enterprise_voice_command(command)

    exact_replacements = {
        "open open firefox": "open firefox",
        "open open chrome": "open chrome",
        "open open vscode": "open vscode",
        "open open visual studio code": "open vscode",
        "open fire": "open firefox",
        "open calendar": "open application calendar",
        "open google chrome": "open chrome",
        "open download": "open folder downloads",
        "open downloads": "open folder downloads",
        "open document": "open folder documents",
        "open documents": "open folder documents",
        "show project": "show projects",
        "show projects": "show projects",
        "list project": "show projects",
        "list projects": "show projects",
        "preview app.py from cyber shield ai": "preview file app.py from cyber shield ai",
        "preview file app.py from cyber": "preview file app.py from cyber shield ai",
        "preview file app from cyber": "preview file app.py from cyber shield ai",
        "open yahoo mail": "open website yahoo mail",
        "open yahoo": "open website yahoo",
        "recite the yahoo mail": "open website yahoo mail",
        "project jar": "open project J.A.R.V.I.S",
        "open project jar": "open project J.A.R.V.I.S",
        "open projector": "open project J.A.R.V.I.S",
        "projector": "open project J.A.R.V.I.S",
        "project cyber": "open project CyberShield AI",
        "project cyber shield": "open project CyberShield AI",
        "project cyber shield ai": "open project CyberShield AI",
        "score project cyber": "score project CyberShield AI",
        "score project cyber shield": "score project CyberShield AI",
        "score project cyber shield ai": "score project CyberShield AI",

        # Screen Vision natural commands
        "review code": "review code on screen",
        "review this code": "review code on screen",
        "analyze this code": "review code on screen",
        "analyze code": "review code on screen",
        "analyze code on screen": "review code on screen",
        "check this code": "review code on screen",
        "check code": "review code on screen",
        "find bug": "find bugs on screen",
        "find bugs": "find bugs on screen",
        "find the bug": "find bugs on screen",
        "find the bugs": "find bugs on screen",
        "find bugs in this code": "find bugs on screen",
        "what is wrong here": "explain error on screen",
        "what's wrong here": "explain error on screen",
        "what is this error": "explain error on screen",
        "what error is this": "explain error on screen",
        "explain error": "explain error on screen",
        "explain this error": "explain error on screen",
        "read error": "read error on screen",
        "read this error": "read error on screen",
        "read code": "read code on screen",
        "read this code": "read code on screen",
        "look at my screen": "analyze my screen",
        "look at the screen": "analyze my screen",
        "explain my screen": "analyze my screen",
        "explain what i see": "analyze my screen",
        "what do you see": "analyze my screen",

        # AI Coding Assistant natural commands
        "fix app.py from cyber": "fix file app.py from CyberShield AI",
        "fix app.py from cyber shield ai": "fix file app.py from CyberShield AI",
        "secure app.py from cyber": "secure file app.py from CyberShield AI",
        "secure app.py from cyber shield ai": "secure file app.py from CyberShield AI",
        "backup app.py from cyber": "backup file app.py from CyberShield AI",
        "backup app.py from cyber shield ai": "backup file app.py from CyberShield AI",

        # Step 33 - History natural commands
        "show last commands": "command history",
        "show command history": "command history",
        "show error history": "error history",
        "show last errors": "last errors",
        "show usage stats": "jarvis usage stats",
        "export history": "export command history",
        "clean old history": "clear old history",
    }

    if command in exact_replacements:
        command = exact_replacements[command]

    step31_command = resolve_step31_voice_project_command(command)

    if step31_command:
        return step31_command

    fused_command = resolve_memory_project_reference(command)

    if fused_command:
        return fused_command

    next_command = resolve_what_next_command(command)

    if next_command:
        return next_command

    # Step 9 natural conversational memory patterns.
    if (
        "working on" in command
        or "last project" in command
        or "current project" in command
    ):
        if "file" not in command:
            return "what was i working on last"

    if "last file" in command or "file did" in command:
        return "what file did we review last"

    if "last audit" in command:
        if "continue" in command or "resume" in command:
            return "continue last audit"
        return "show last audit"

    if "security report" in command and "last" in command:
        return "show last security report"

    if "vulnerabilities" in command and ("find" in command or "found" in command or "did you" in command):
        return "what vulnerabilities did you find"

    if "continue" in command and "project" in command:
        return "continue last project"

    if "resume" in command and "project" in command:
        return "resume last project"

    if ("continue" in command or "resume" in command) and "task" in command:
        return "continue last task"

    if "projects do you remember" in command or "remembered projects" in command:
        if "compare" in command:
            return "compare remembered projects"
        return "what projects do you remember"

    if "memory summary" in command or "summarize memory" in command:
        return "memory summary"

    # Step 7 natural Iron Man Security Developer Mode.
    if command in {
        "secure project",
        "secure my project",
        "scan project",
        "scan my project",
        "audit project",
        "audit my project",
        "find vulnerabilities",
        "find security issues",
        "find security problems",
        "check security",
        "check vulnerabilities",
    }:
        return "full security audit CyberShield AI"

    if (
        any(word in command for word in ["secure", "scan", "audit"])
        and any(word in command for word in ["cyber", "cybershield", "cyber shield"])
    ):
        if "roadmap" in command:
            return "generate security roadmap CyberShield AI"
        return "full security audit CyberShield AI"

    if (
        "vulnerab" in command
        or "security issues" in command
        or "security problems" in command
        or "weaknesses" in command
    ):
        if "cyber" in command or "project" in command:
            return "full security audit CyberShield AI"

    if "api key" in command or "api keys" in command:
        return "find api keys CyberShield AI" if "cyber" in command or "project" in command else command

    if "password" in command or "passwords" in command:
        return "find passwords CyberShield AI" if "cyber" in command or "project" in command else command

    if "secret" in command or "secrets" in command:
        return "find hardcoded secrets CyberShield AI" if "cyber" in command or "project" in command else command

    if "sql injection" in command:
        return "find sql injection CyberShield AI" if "cyber" in command or "project" in command else command

    if "xss" in command:
        return "find xss CyberShield AI" if "cyber" in command or "project" in command else command

    if "dangerous import" in command or "dangerous imports" in command:
        return "find dangerous imports CyberShield AI" if "cyber" in command or "project" in command else command

    if "security roadmap" in command or "roadmap security" in command:
        return "generate security roadmap CyberShield AI"

    # Step 10 / Step 12 generic project planner voice patterns.
    generic_project_prefixes = [
        "memory aware review ",
        "memory aware security review ",
        "project timeline ",
        "show project timeline ",
        "audit history ",
        "vulnerability history ",
        "remembered fixes ",
        "project evolution ",
        "show project evolution ",
        "last vulnerabilities ",
        "last improvements ",
        "plan project ",
        "project plan ",
        "architect project ",
        "project architect ",
        "become project architect ",
        "prepare release ",
        "release checklist ",
        "prepare deployment ",
        "deployment checklist ",
        "project maturity ",
        "estimate project maturity ",
        "production readiness ",
        "estimate production readiness ",
        "what should i fix next ",
        "what should i fix next project ",
        "next best improvements ",
        "highest risk vulnerabilities ",
        "high risk vulnerabilities ",
        "generate sprint plan ",
        "sprint plan ",
        "generate roadmap ",
        "generate project roadmap ",
        "project roadmap ",
    ]

    for prefix in generic_project_prefixes:
        if command.startswith(prefix):
            target = command[len(prefix):].strip()

            if target:
                if prefix in ["project plan ", "generate project roadmap ", "project roadmap ", "generate roadmap "]:
                    return "plan project " + normalize_project_name(target)
                if prefix in ["project architect ", "become project architect "]:
                    return "architect project " + normalize_project_name(target)
                if prefix == "show project timeline ":
                    return "project timeline " + normalize_project_name(target)
                if prefix == "show project evolution ":
                    return "project evolution " + normalize_project_name(target)
                if prefix == "release checklist ":
                    return "prepare release " + normalize_project_name(target)
                if prefix == "deployment checklist ":
                    return "prepare deployment " + normalize_project_name(target)
                if prefix == "estimate project maturity ":
                    return "project maturity " + normalize_project_name(target)
                if prefix == "estimate production readiness ":
                    return "production readiness " + normalize_project_name(target)
                if prefix == "what should i fix next project ":
                    return "what should i fix next " + normalize_project_name(target)
                if prefix == "high risk vulnerabilities ":
                    return "highest risk vulnerabilities " + normalize_project_name(target)
                if prefix == "sprint plan ":
                    return "generate sprint plan " + normalize_project_name(target)

                return prefix + normalize_project_name(target)

    if command.startswith("prepare ") and " for release" in command:
        target = command[len("prepare "):].strip()
        target = re.sub(r"\s+for\s+release\s*$", "", target, flags=re.IGNORECASE).strip()

        if target:
            return "prepare release " + normalize_project_name(target)

    if command.startswith("prepare ") and " for deployment" in command:
        target = command[len("prepare "):].strip()
        target = re.sub(r"\s+for\s+deployment\s*$", "", target, flags=re.IGNORECASE).strip()

        if target:
            return "prepare deployment " + normalize_project_name(target)

    # Natural Screen Vision patterns.
    if (
        "error" in command
        and any(word in command for word in ["explain", "what", "this", "screen"])
    ):
        return "explain error on screen"

    if (
        "bug" in command
        and any(word in command for word in ["find", "check", "search"])
    ):
        return "find bugs on screen"

    if (
        "code" in command
        and any(word in command for word in ["review", "analyze", "check"])
    ):
        return "review code on screen"

    if (
        "screen" in command
        and any(word in command for word in ["analyze", "explain", "look"])
    ):
        return "analyze my screen"

    # Natural file fix patterns:
    # Example: "fix app.py from cyber shield ai"
    if command.startswith("fix ") and " from " in command:
        if "cyber" in command:
            file_part = command[len("fix "):].split(" from ")[0].strip()
            return f"fix file {file_part} from CyberShield AI"
        return "fix file " + command[len("fix "):].strip()

    if command.startswith("secure ") and " from " in command:
        if "cyber" in command:
            file_part = command[len("secure "):].split(" from ")[0].strip()
            return f"secure file {file_part} from CyberShield AI"
        return "secure file " + command[len("secure "):].strip()

    if command.startswith("backup ") and " from " in command:
        if "cyber" in command:
            file_part = command[len("backup "):].split(" from ")[0].strip()
            return f"backup file {file_part} from CyberShield AI"
        return "backup file " + command[len("backup "):].strip()

    # Step 4 natural current-screen/current-code patterns.
    if "current" in command and "error" in command:
        return "explain error on screen"

    if "current" in command and "code" in command:
        return "review code on screen"

    if "current" in command and "file" in command:
        return "review code on screen"

    if "current" in command and "project" in command:
        return "analyze my screen"

    if "screen" in command and any(word in command for word in ["fix", "suggest", "problem"]):
        return "explain error on screen"

    if "what should i fix" in command:
        return "find bugs on screen"

    # Project assistant natural patterns.
    if command.startswith(("show project structure ", "show project files ", "show project statistics ", "show project stats ", "show largest files ", "show security report ")) and "cyber" in command:
        if command.startswith("show project structure "):
            return "show project structure CyberShield AI"
        if command.startswith("show project files "):
            return "show project files CyberShield AI"
        if command.startswith(("show project statistics ", "show project stats ")):
            return "show project statistics CyberShield AI"
        if command.startswith("show largest files "):
            return "show largest files CyberShield AI"
        if command.startswith("show security report "):
            return "show security report CyberShield AI"

    # Only normalize "cyber" inside explicit project commands.
    project_command_prefixes = (
        "open project ",
        "score project ",
        "review project ",
        "analyze project ",
        "suggest fixes ",
        "strict security ",
        "export report ",
        "show project structure ",
        "show project files ",
        "show project statistics ",
        "show project stats ",
        "show largest files ",
        "show security report ",
        "find api keys ",
        "scan api keys ",
        "find passwords ",
        "scan passwords ",
        "find hardcoded secrets ",
        "scan hardcoded secrets ",
        "find secrets ",
        "scan secrets ",
        "find sql injection ",
        "scan sql injection ",
        "find xss ",
        "scan xss ",
        "find dangerous imports ",
        "scan dangerous imports ",
        "full security audit ",
        "enterprise audit ",
        "scan entire project ",
        "generate security roadmap ",
        "security roadmap ",
        "memory aware review ",
        "memory aware security review ",
        "project timeline ",
        "show project timeline ",
        "audit history ",
        "vulnerability history ",
        "remembered fixes ",
        "project evolution ",
        "show project evolution ",
        "last vulnerabilities ",
        "last improvements ",
        "plan project ",
        "project plan ",
        "architect project ",
        "project architect ",
        "prepare release ",
        "release checklist ",
        "prepare deployment ",
        "deployment checklist ",
        "project maturity ",
        "production readiness ",
        "what should i fix next ",
        "next best improvements ",
        "highest risk vulnerabilities ",
        "high risk vulnerabilities ",
        "generate sprint plan ",
        "sprint plan ",
        "generate roadmap ",
        "generate project roadmap ",
        "project roadmap ",
    )

    if command.startswith(project_command_prefixes) and "cyber" in command:
        if command.startswith("open project "):
            return "open project CyberShield AI"
        if command.startswith("score project "):
            return "score project CyberShield AI"
        if command.startswith("suggest fixes"):
            return "suggest fixes for project CyberShield AI"
        if command.startswith("strict security"):
            return "strict security analyzer project CyberShield AI"
        if command.startswith("export report"):
            return "export report CyberShield AI"
        if command.startswith("show project structure"):
            return "show project structure CyberShield AI"
        if command.startswith("show project files"):
            return "show project files CyberShield AI"
        if command.startswith("show project statistics") or command.startswith("show project stats"):
            return "show project statistics CyberShield AI"
        if command.startswith("show largest files"):
            return "show largest files CyberShield AI"
        if command.startswith("show security report"):
            return "show security report CyberShield AI"
        if command.startswith("find api keys") or command.startswith("scan api keys"):
            return "find api keys CyberShield AI"
        if command.startswith("find passwords") or command.startswith("scan passwords"):
            return "find passwords CyberShield AI"
        if command.startswith("find hardcoded secrets") or command.startswith("scan hardcoded secrets") or command.startswith("find secrets") or command.startswith("scan secrets"):
            return "find hardcoded secrets CyberShield AI"
        if command.startswith("find sql injection") or command.startswith("scan sql injection"):
            return "find sql injection CyberShield AI"
        if command.startswith("find xss") or command.startswith("scan xss"):
            return "find xss CyberShield AI"
        if command.startswith("find dangerous imports") or command.startswith("scan dangerous imports"):
            return "find dangerous imports CyberShield AI"
        if command.startswith("full security audit") or command.startswith("enterprise audit") or command.startswith("scan entire project"):
            return "full security audit CyberShield AI"
        if command.startswith("generate security roadmap") or command.startswith("security roadmap"):
            return "generate security roadmap CyberShield AI"
        if command.startswith(("plan project", "project plan", "generate roadmap", "generate project roadmap", "project roadmap")):
            return "plan project CyberShield AI"
        if command.startswith(("architect project", "project architect")):
            return "architect project CyberShield AI"
        if command.startswith(("prepare release", "release checklist")):
            return "prepare release CyberShield AI"
        if command.startswith(("prepare deployment", "deployment checklist")):
            return "prepare deployment CyberShield AI"
        if command.startswith("project maturity"):
            return "project maturity CyberShield AI"
        if command.startswith("production readiness"):
            return "production readiness CyberShield AI"
        if command.startswith(("what should i fix next", "next best improvements")):
            return "what should i fix next CyberShield AI"
        if command.startswith(("highest risk vulnerabilities", "high risk vulnerabilities")):
            return "highest risk vulnerabilities CyberShield AI"
        if command.startswith(("generate sprint plan", "sprint plan")):
            return "generate sprint plan CyberShield AI"

    return command


def get_drives():
    drives = []

    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append(drive)

    return drives


def open_target(path):
    try:
        os.startfile(path)
        return True
    except Exception:
        pass

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        return True
    except Exception:
        return False


def open_website(target):
    target = clean_text(target)
    target = WEBSITE_ALIASES.get(target, target)
    target = target.replace(" ", "")

    if not target:
        return "Website target is empty."

    if "." not in target:
        target += ".com"

    if not target.startswith("http://") and not target.startswith("https://"):
        target = "https://" + target

    webbrowser.open(target)
    return friendly_open_message("website", target)



def find_app_from_registry(exe_name):
    if winreg is None:
        return None

    registry_paths = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
    ]

    for root, key_path in registry_paths:
        try:
            with winreg.OpenKey(root, key_path) as key:
                value, _ = winreg.QueryValueEx(key, None)

                if value and os.path.exists(value):
                    return value
        except Exception:
            continue

    return None


def open_application(name):
    name = clean_text(name)

    corrections = {
        "computer": "calculator",
        "calculate": "calculator",
        "calculation": "calculator",
        "browser": "chrome",
        "code": "vscode",
        "vs code": "vscode",
        "visual studio": "visual studio code",
        "fire": "firefox",
        "mozilla": "firefox",
        "mozilla firefox": "firefox",
    }

    name = corrections.get(name, name)
    candidates = APP_ALIASES.get(name)

    if candidates:
        # 1. Direct paths and PATH
        for candidate in candidates:
            candidate = os.path.expandvars(candidate)

            if candidate.endswith(":"):
                if open_target(candidate):
                    return friendly_open_message("application", name)

            if os.path.exists(candidate):
                try:
                    subprocess.Popen(
                        [candidate],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return friendly_open_message("application", name)
                except Exception:
                    pass

            resolved = shutil.which(candidate)

            if resolved:
                try:
                    subprocess.Popen(
                        [resolved],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return friendly_open_message("application", name)
                except Exception:
                    pass

        # 2. Windows registry App Paths, useful for Chrome/Firefox/Edge.
        for candidate in candidates:
            exe_name = os.path.basename(candidate)

            if not exe_name.lower().endswith(".exe"):
                continue

            registry_path = find_app_from_registry(exe_name)

            if registry_path:
                try:
                    subprocess.Popen(
                        [registry_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return friendly_open_message("application", name)
                except Exception:
                    pass

        # 3. Controlled shell fallback only for known Windows built-ins.
        windows_shell_ok = {
            "calculator",
            "calc",
            "notepad",
            "paint",
            "powershell",
            "command prompt",
            "cmd",
            "file explorer",
            "explorer",
            "task manager",
            "control panel",
            "settings",
            "calendar",
        }

        if name in windows_shell_ok:
            for candidate in candidates:
                if open_target(candidate):
                    return friendly_open_message("application", name)

        return (
            f"Could not open application: {name}. "
            f"It may not be installed, or it is not indexed. Run python app_indexer.py and try again."
        )

    # Unknown app fallback should be honest.
    if open_target(name):
        return friendly_open_message("application", name)

    return f"Could not open application: {name}"

def user_folder(name):
    name = clean_text(name)
    folder = FOLDER_ALIASES.get(name, name)
    path = os.path.join(os.path.expanduser("~"), folder)

    if os.path.exists(path):
        return path

    return None


def score_match(query, candidate_name):
    query = clean_text(query)
    candidate = clean_text(candidate_name)

    if not query or not candidate:
        return 0

    if query == candidate:
        return 100

    if query in candidate:
        return 85

    query_parts = set(query.replace("_", " ").replace("-", " ").split())
    candidate_parts = set(candidate.replace("_", " ").replace("-", " ").split())

    if not query_parts:
        return 0

    common = len(query_parts & candidate_parts)
    return int((common / len(query_parts)) * 70)


def find_file_or_folder(name, max_seconds=MAX_SEARCH_SECONDS):
    name = clean_text(name)

    if not name:
        return None

    known = user_folder(name)
    if known:
        return known

    if os.path.exists(name):
        return os.path.abspath(name)

    roots = [os.getcwd(), os.path.expanduser("~")]
    roots.extend(get_drives())

    best_path = None
    best_score = 0
    start = time.time()

    for root_dir in roots:
        if time.time() - start > max_seconds:
            break

        if not os.path.exists(root_dir):
            continue

        try:
            for root, dirs, files in os.walk(root_dir):
                if time.time() - start > max_seconds:
                    break

                dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]

                folder_name = os.path.basename(root)
                folder_score = score_match(name, folder_name)

                if folder_score > best_score:
                    best_score = folder_score
                    best_path = root

                for file_name in files:
                    file_score = score_match(name, file_name)

                    if file_score > best_score:
                        best_score = file_score
                        best_path = os.path.join(root, file_name)

                if best_score >= 100:
                    return best_path

        except Exception:
            continue

    if best_score >= 55:
        return best_path

    return None


def find_project_folder(project_name):
    normalized = normalize_project_name(project_name)
    possible_names = PROJECT_FOLDER_ALIASES.get(normalized, [normalized, project_name])

    quick_roots = [
        os.getcwd(),
        os.path.dirname(os.getcwd()),
        "D:\\",
        "E:\\",
        os.path.expanduser("~"),
    ]

    for root_dir in quick_roots:
        if not os.path.exists(root_dir):
            continue

        try:
            for root, dirs, files in os.walk(root_dir):
                dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]
                base = os.path.basename(root).lower().replace("_", "").replace("-", "").replace(" ", "")
                full = root.lower().replace("_", "").replace("-", "").replace(" ", "")

                for name in possible_names:
                    key = clean_text(name).replace("_", "").replace("-", "").replace(" ", "")
                    if key and (key in base or key in full):
                        return root

        except Exception:
            continue

    for name in possible_names:
        found = find_file_or_folder(name)
        if found and os.path.isdir(found):
            return found

    return None


def safe_handle_command(command):
    if handle_command is None:
        return f"jarvis_agent could not be loaded: {JARVIS_AGENT_IMPORT_ERROR}"

    try:
        return handle_command(command)
    except FileNotFoundError as e:
        return f"Path not found from saved memory: {e}"
    except Exception as e:
        return f"JARVIS command error: {e}"


def has_clear_intent(command):
    lower = normalize_enterprise_voice_command(normalize_personal_command(clean_text(command)))

    if handle_voice_meta_command(lower) is not None:
        return True

    if any(word in lower for word in ["report", "presentation", "spreadsheet"]) and any(word in lower for word in ["create", "generate", "make", "export", "review"]):
        return True

    if lower in EXIT_COMMANDS:
        return True

    if any(lower.startswith(prefix) for prefix in OPEN_PREFIXES):
        return True

    if any(lower.startswith(prefix) for prefix in SAFE_JARVIS_PREFIXES):
        return True

    return False


def needs_confirmation(command):
    lower = clean_text(command)

    safe_ai_prefixes = (
        "fix file ",
        "fix project file ",
        "secure file ",
        "secure project file ",
        "apply safe patch project file ",
        "apply ai patch project file ",
        "auto improve project file ",
        "backup file ",
        "backup project file ",
        "restore backup file ",
        "restore backup project file ",
        "suggest safe patch file ",
        "suggest safe patch project file ",
        "list backups",
    )

    if lower.startswith(safe_ai_prefixes):
        return False

    if any(word in lower for word in RISKY_WORDS):
        return True

    if REQUIRE_CONFIRMATION_FOR_FILES and lower.startswith(("open file ", "open document ")):
        return True

    if REQUIRE_CONFIRMATION_FOR_PROJECTS and lower.startswith(("open project ", "open code ")):
        return True

    if REQUIRE_CONFIRMATION_FOR_RISKY_ACTIONS and any(word in lower for word in RISKY_WORDS):
        return True

    return False




# ==========================
# ENTERPRISE VAD HELPERS
# ==========================
def configure_enterprise_vad(recognizer):
    if recognizer is None:
        return

    try:
        # Keep dynamic threshold OFF after calibration.
        # This prevents JARVIS from becoming deaf when Windows/noise spikes.
        recognizer.dynamic_energy_threshold = False
        recognizer.pause_threshold = VAD_PAUSE_THRESHOLD
        recognizer.non_speaking_duration = VAD_NON_SPEAKING_DURATION

        current = getattr(recognizer, "energy_threshold", VAD_ENERGY_THRESHOLD or 100)

        if VAD_ENERGY_THRESHOLD is not None:
            current = VAD_ENERGY_THRESHOLD

        if VAD_FORCE_SENSITIVE_THRESHOLD:
            current = max(VAD_MIN_ENERGY_THRESHOLD, min(current, VAD_MAX_ENERGY_THRESHOLD))

        recognizer.energy_threshold = current

    except Exception:
        pass


def calibrate_microphone_noise(recognizer, source, seconds=VAD_CALIBRATION_SECONDS, force=False):
    global _MICROPHONE_CALIBRATED_ONCE
    global _LAST_CALIBRATION_TIME

    try:
        if recognizer is None:
            return

        # Avoid calibrating at every wake loop.
        # That was the reason it kept saying "Calibrating..." and reacting late.
        if (
            _MICROPHONE_CALIBRATED_ONCE
            and not force
            and not VAD_CALIBRATE_EVERY_LISTEN
        ):
            configure_enterprise_vad(recognizer)
            return

        update_hud(
            status="CALIBRATING",
            command="Fast microphone calibration...",
            result="Quick noise check.",
            action="Fast voice calibration",
            voice="0.1",
            ai_status="READY",
            ollama_status="LOCAL"
        )

        recognizer.dynamic_energy_threshold = True

        recognizer.adjust_for_ambient_noise(
            source,
            duration=seconds
        )

        detected = getattr(recognizer, "energy_threshold", VAD_ENERGY_THRESHOLD or 100)

        # Make it sensitive enough for farther voice.
        if VAD_FORCE_SENSITIVE_THRESHOLD:
            detected = max(
                VAD_MIN_ENERGY_THRESHOLD,
                min(detected, VAD_MAX_ENERGY_THRESHOLD)
            )

        recognizer.energy_threshold = detected
        recognizer.dynamic_energy_threshold = False
        recognizer.pause_threshold = VAD_PAUSE_THRESHOLD
        recognizer.non_speaking_duration = VAD_NON_SPEAKING_DURATION

        _MICROPHONE_CALIBRATED_ONCE = True
        _LAST_CALIBRATION_TIME = time.time()

        if VAD_DEBUG:
            print(f"[VAD] calibrated energy={recognizer.energy_threshold}")

    except Exception:
        configure_enterprise_vad(recognizer)


def vad_listen_audio(
    recognizer,
    microphone,
    timeout=None,
    phrase_time_limit=None,
    prompt="Listening...",
    calibrate=False
):
    configure_enterprise_vad(recognizer)

    update_hud(
        status="LISTENING",
        command=prompt,
        result="Listening instantly with fast voice detection.",
        action="Fast VAD voice capture",
        ai_status="READY",
        vision_status="ACTIVE",
        memory_status="SYNC",
        ollama_status="LOCAL",
        voice="0.8"
    )

    with microphone as source:
        # Quick one-time calibration only.
        should_calibrate = (
            calibrate
            or not _MICROPHONE_CALIBRATED_ONCE
            or VAD_CALIBRATE_EVERY_LISTEN
        )

        if should_calibrate:
            calibrate_microphone_noise(
                recognizer,
                source,
                seconds=VAD_CALIBRATION_SECONDS,
                force=calibrate
            )
        else:
            configure_enterprise_vad(recognizer)

        print(prompt)

        if VAD_DEBUG:
            print(
                f"[VAD] energy={getattr(recognizer, 'energy_threshold', 'n/a')} "
                f"pause={getattr(recognizer, 'pause_threshold', 'n/a')} "
                f"non_speaking={getattr(recognizer, 'non_speaking_duration', 'n/a')}"
            )

        audio = recognizer.listen(
            source,
            timeout=timeout,
            phrase_time_limit=phrase_time_limit
        )

    update_hud(
        status="PROCESSING",
        command="Processing speech...",
        result="Converting voice to text.",
        action="Speech recognition",
        ai_status="PROCESSING",
        ollama_status="LOCAL",
        voice="0.2"
    )

    return audio


def recognize_audio_google_safe(recognizer, audio):
    """
    Safer recognition:
    - tries English first
    - then Romanian-English environment fallback
    - never crashes the voice loop
    """
    languages = ["en-US", "en-GB", "ro-RO"]

    for language in languages:
        try:
            text = recognizer.recognize_google(audio, language=language)
            text = str(text or "").strip()

            if text:
                return text
        except Exception:
            continue

    return ""


def clean_recognized_command(text):
    text = str(text or "").strip()

    if not text:
        return ""

    cleaned = clean_text(text)
    cleaned = normalize_wake_transcript(cleaned)
    cleaned = collapse_repeated_command_words(cleaned)
    cleaned = normalize_personal_command(cleaned)

    replacements = {
        "hey jha": "hey jarvis",
        "hey jar": "hey jarvis",
        "hey jervis": "hey jarvis",
        "hay jarvis": "hey jarvis",
        "jar": "jarvis",
        "jervis": "jarvis",
        "open fire": "open firefox",
        "open firefox browser": "open firefox",
        "open vs": "open vscode",
        "open vs code": "open vscode",
        "open visual studio code": "open vscode",
        "open project cybers in the": "open project CyberShield AI",
        "open project cyber shield": "open project CyberShield AI",
        "open project cybershield": "open project CyberShield AI",
        "open project cyber": "open project CyberShield AI",
    }

    if cleaned in replacements:
        return replacements[cleaned]

    cleaned = re.sub(r"\b(hey|hi|hay|play|a)\s+(jay|jha|jar|jervis|service|travis|charvis|jars|jarvis)\b", "hey jarvis", cleaned)
    cleaned = re.sub(r"\bjervis\b", "jarvis", cleaned)
    cleaned = re.sub(r"\bopen\s+fire\b", "open firefox", cleaned)
    cleaned = re.sub(r"\bcybers\s+in\s+the\b", "cybershield ai", cleaned)
    cleaned = re.sub(r"\bcyber\s+shield\s+ai\b", "CyberShield AI", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bcybershield\s+ai\b", "CyberShield AI", cleaned, flags=re.IGNORECASE)

    return cleaned.strip()


def transcript_is_noise(text):
    lower = clean_text(text)

    if starts_with_wake_variant(lower):
        return False

    if lower.startswith(("open ", "review ", "analyze ", "score ", "show ", "find ", "read ", "fix ", "secure ")):
        return False

    if not lower:
        return True

    known_noise = {
        "grandma",
        "musical",
        "try another",
        "what is retarded",
        "can you hear me",
    }

    if lower in known_noise:
        return True

    if len(lower) <= 2:
        return True

    return False


# ==========================
# HEY JARVIS WAKE-WORD MODE
# ==========================
WAKE_RESPONSE = "Yes Sir, how may I help you today?"
SHUTDOWN_RESPONSE = "Shutting down. Have a great day, Sir."
CONVERSATION_IDLE_SECONDS = 15


def is_wake_word(text):
    return starts_with_wake_variant(text)


def is_shutdown_command(text):
    lower = clean_text(text)
    return lower in EXIT_COMMANDS or "jarvis shutdown" in lower or "shutdown jarvis" in lower


def recognize_without_enter(recognizer, microphone, timeout=None, phrase_time_limit=8, prompt="Listening..."):
    """
    Continuous microphone recognition without pressing ENTER.

    Enterprise VAD version:
    - calibrates to ambient noise
    - waits for speech
    - ends after a natural pause
    - cleans common STT mistakes
    """
    audio = vad_listen_audio(
        recognizer,
        microphone,
        timeout=timeout,
        phrase_time_limit=phrase_time_limit,
        prompt=prompt,
        calibrate=False
    )

    text = recognize_audio_google_safe(
        recognizer,
        audio
    )

    text = clean_recognized_command(text)
    text = collapse_repeated_command_words(text)

    update_hud(
        status="PROCESSING",
        command=text,
        result="Command recognized." if text else "No clear speech recognized."
    )

    return text


def listen_for_wake_word(recognizer, microphone):
    """
    Passive standby loop.
    It only activates when it hears: Hey JARVIS.
    VAD version reduces random words and waits naturally for speech.
    """
    update_hud(
        status="STANDBY",
        command="Say: Hey Jarvis",
        result="Wake-word mode active.",
        action="Waiting for wake word",
        ai_status="READY",
        voice="0.0"
    )

    try:
        text = recognize_without_enter(
            recognizer,
            microphone,
            timeout=WAKE_START_TIMEOUT,
            phrase_time_limit=WAKE_PHRASE_LIMIT,
            prompt="Standby... say 'Hey Jarvis'"
        )

        if starts_with_wake_variant(text):
            text = normalize_wake_transcript(text)
            print("Heard:", text)
            return text

        if transcript_is_noise(text):
            return ""

        print("Heard:", text)
        return text

    except Exception:
        return ""


def listen_for_active_command(recognizer, microphone):
    """
    After wake word, JARVIS listens for a real command.
    VAD version waits until you finish the sentence.
    """
    try:
        text = recognize_without_enter(
            recognizer,
            microphone,
            timeout=ACTIVE_START_TIMEOUT,
            phrase_time_limit=ACTIVE_PHRASE_LIMIT,
            prompt="JARVIS active. Speak your command..."
        )

        if transcript_is_noise(text):
            return ""

        return text

    except Exception:
        return ""


def shutdown_jarvis():
    update_hud(
        status="SHUTDOWN",
        command="JARVIS shutdown",
        result="System shutting down.",
        action="Shutdown",
        ai_status="OFFLINE",
        voice="0.0"
    )

    speak(SHUTDOWN_RESPONSE)

    try:
        stop_speaking()
    except Exception:
        pass

    raise SystemExit(0)




def prepare_microphone_for_instant_mode(recognizer, microphone):
    """
    Runs one quick calibration at startup, then keeps JARVIS sensitive.
    """
    try:
        configure_enterprise_vad(recognizer)

        with microphone as source:
            calibrate_microphone_noise(
                recognizer,
                source,
                seconds=VAD_CALIBRATION_SECONDS,
                force=True
            )

        update_hud(
            status="READY",
            command="Microphone ready",
            result="Fast voice mode enabled.",
            action="Instant voice mode",
            voice="0.0",
            ai_status="READY",
            ollama_status="LOCAL"
        )

        print(
            f"[VOICE] Instant mode ready. "
            f"Energy={getattr(recognizer, 'energy_threshold', 'n/a')}, "
            f"pause={getattr(recognizer, 'pause_threshold', 'n/a')}"
        )

    except Exception as error:
        print(f"[VOICE] Microphone preparation warning: {error}")



def run_wake_word_mode(recognizer, microphone):
    """
    Gemini / Google-style flow:
    1. Waits for 'Hey Jarvis'
    2. Replies: Yes Sir, how may I help you today?
    3. Listens for commands for a short active session
    4. Goes back to standby
    5. 'Jarvis shutdown' closes the assistant cleanly
    """
    speak("JARVIS voice system online. Say Hey Jarvis when you need me.")

    prepare_microphone_for_instant_mode(recognizer, microphone)

    while True:
        heard = normalize_wake_transcript(listen_for_wake_word(recognizer, microphone))

        if not heard:
            continue

        if is_shutdown_command(heard):
            shutdown_jarvis()

        if not is_wake_word(heard):
            continue

        speak(WAKE_RESPONSE)

        active_until = time.time() + CONVERSATION_IDLE_SECONDS

        while time.time() < active_until:
            command = listen_for_active_command(recognizer, microphone)
            command_clean = clean_text(command)

            if not command_clean:
                speak("I did not hear a command. Returning to standby.")
                break

            print("You:", command)

            if is_shutdown_command(command_clean):
                shutdown_jarvis()

            normalized = normalize_command(command)

            update_hud(
                status="PROCESSING",
                command=normalized,
                result="Executing voice command...",
                action="Voice command execution",
                ai_status="READY",
                voice="0.2"
            )

            try:
                result = handle_command_text(
                    normalized,
                    recognizer=recognizer,
                    microphone=microphone
                )

                if result == "exit":
                    shutdown_jarvis()

                print("Result:", result)

                update_hud_from_command_result(normalized, result)

                update_hud(
                    status="SUCCESS",
                    command=normalized,
                    result=result,
                    action="Command completed",
                    ai_status="READY",
                    voice="0.0"
                )

                if result:
                    speak(short_text(result, 260))

            except SystemExit:
                raise

            except Exception as error:
                log_error_history(
                    normalized,
                    error,
                    stage="wake_word_mode"
                )

                update_hud(
                    status="ERROR",
                    command=normalized,
                    result=str(error),
                    action="Command failed",
                    ai_status="READY",
                    voice="0.0"
                )

                speak("I encountered an error while executing that command.")

            # Keep active mode alive for chained commands.
            active_until = time.time() + CONVERSATION_IDLE_SECONDS

        update_hud(
            status="STANDBY",
            command="Say: Hey Jarvis",
            result="Returned to standby.",
            action="Waiting for wake word",
            ai_status="READY",
            voice="0.0"
        )



def recognize_once(recognizer, microphone, timeout=None, phrase_time_limit=18):
    """
    Push-to-talk style with Enterprise VAD:
    - press ENTER
    - speak naturally
    - JARVIS stops after your pause
    """

    update_hud(
        status="STANDBY",
        command="Press ENTER, then speak your full command...",
        result="Waiting..."
    )

    input("\nPress ENTER, then speak your full command... ")

    audio = vad_listen_audio(
        recognizer,
        microphone,
        timeout=timeout if timeout is not None else PUSH_TO_TALK_START_TIMEOUT,
        phrase_time_limit=phrase_time_limit if phrase_time_limit is not None else PUSH_TO_TALK_PHRASE_LIMIT,
        prompt="Listening now... speak naturally. I will stop when you pause.",
        calibrate=True
    )

    print("Processing command...")

    text = recognize_audio_google_safe(
        recognizer,
        audio
    )

    text = clean_recognized_command(text)

    update_hud(
        status="PROCESSING",
        command=text,
        result="Command recognized." if text else "No clear speech recognized."
    )

    return text


def confirm_action(recognizer, microphone, command):
    speak(f"I heard: {command}. Say yes to confirm, or no to cancel.")

    try:
        answer = recognize_once(recognizer, microphone, timeout=5, phrase_time_limit=4)
        answer = clean_text(answer)
        print("Confirmation:", answer)

        yes_words = {"yes", "yeah", "yep", "confirm", "ok", "okay", "sure", "open it", "do it"}
        no_words = {"no", "nope", "cancel", "stop", "don't", "do not"}

        # Accept phrases like:
        # "yes open it", "yes please", "okay open it"
        if any(answer == word or answer.startswith(word + " ") for word in yes_words):
            return True

        if any(answer == word or answer.startswith(word + " ") for word in no_words):
            return False

        return False

    except Exception:
        return False


def handle_open_command(command):
    command = normalize_command(command)

    prefix = None
    target = None
    lower = clean_text(command)

    for p in OPEN_PREFIXES:
        if lower.startswith(p):
            prefix = p
            target = command[len(p):].strip()
            break

    if not prefix:
        return None

    if not target:
        return "I heard open, but I did not hear what to open."

    target_lower = clean_text(target)

    if prefix in {"open project ", "open code "}:
        project_name = normalize_project_name(target)
        found_project = find_project_folder(project_name)

        if found_project:
            open_target(found_project)
            return f"Opening project folder: {found_project}"

        return "I could not find the project folder on this laptop, PC, stick, or external drive."

    if prefix in {"open website ", "open site ", "go to ", "visit "}:
        return open_website(target)

    if target_lower in WEBSITE_ALIASES or "." in target_lower:
        return open_website(target)

    if prefix in {"open folder ", "open directory ", "open file ", "open document "}:
        found = find_file_or_folder(target)

        if found:
            open_target(found)
            return f"Opening: {found}"

        return f"I could not find: {target}"

    if prefix in {"open app ", "open application ", "open program "}:
        return open_application(target)

    app_name = APP_CORRECTIONS.get(target_lower, target_lower)

    if app_name in APP_ALIASES:
        return open_application(app_name)

    folder = user_folder(target_lower)
    if folder:
        open_target(folder)
        return f"Opening folder: {folder}"

    if target_lower in WEBSITE_ALIASES:
        return open_website(target_lower)

    # Treat common web/mail phrases as websites, not apps.
    if "mail" in target_lower and any(word in target_lower for word in ["yahoo", "outlook", "hotmail", "gmail"]):
        return open_website(target_lower)

    found = find_file_or_folder(target)
    if found:
        open_target(found)
        return f"Opening: {found}"

    return open_application(target)




# ==========================
# STEP 33 - COMMAND HISTORY & ERROR HISTORY
# Tracks executed commands, errors, usage statistics, and exports history.
# Safe logging only. No sensitive audio storage.
# ==========================
HISTORY_DIR = "history"
COMMAND_HISTORY_FILE = os.path.join(
    HISTORY_DIR,
    "command_history.json"
)
ERROR_HISTORY_FILE = os.path.join(
    HISTORY_DIR,
    "error_history.json"
)


def _history_now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _history_date_for_file():
    return time.strftime("%Y-%m-%d_%H-%M-%S")


def _ensure_history_dir():
    os.makedirs(
        HISTORY_DIR,
        exist_ok=True
    )


def _load_history_file(path):
    if not os.path.exists(path):
        return []

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        return []

    except Exception:
        return []


def _save_history_file(path, data):
    _ensure_history_dir()

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )


def log_command_history(
    raw_command,
    normalized_command,
    result,
    status="SUCCESS"
):
    data = _load_history_file(COMMAND_HISTORY_FILE)

    entry = {
        "timestamp": _history_now(),
        "raw_command": str(raw_command),
        "normalized_command": str(normalized_command),
        "status": str(status),
        "result_preview": short_text(result, 500),
    }

    data.append(entry)

    # Keep history reasonably small.
    data = data[-1000:]

    _save_history_file(
        COMMAND_HISTORY_FILE,
        data
    )


def log_error_history(
    command,
    error,
    stage="runtime"
):
    data = _load_history_file(ERROR_HISTORY_FILE)

    entry = {
        "timestamp": _history_now(),
        "command": str(command),
        "stage": str(stage),
        "error": str(error),
    }

    data.append(entry)

    data = data[-500:]

    _save_history_file(
        ERROR_HISTORY_FILE,
        data
    )


def command_history(limit=20):
    data = _load_history_file(COMMAND_HISTORY_FILE)

    if not data:
        return "No command history found."

    output = [
        "COMMAND HISTORY",
        f"Showing last {min(limit, len(data))} command(s):",
        ""
    ]

    for item in data[-limit:]:
        output.append(
            f"- {item.get('timestamp', 'Unknown')} | "
            f"{item.get('status', 'UNKNOWN')} | "
            f"{item.get('normalized_command', '')}"
        )

    return "\n".join(output)


def error_history(limit=20):
    data = _load_history_file(ERROR_HISTORY_FILE)

    if not data:
        return "No error history found."

    output = [
        "ERROR HISTORY",
        f"Showing last {min(limit, len(data))} error(s):",
        ""
    ]

    for item in data[-limit:]:
        output.append(
            f"- {item.get('timestamp', 'Unknown')} | "
            f"{item.get('stage', 'runtime')} | "
            f"{item.get('command', '')}"
        )
        output.append(
            f"  Error: {short_text(item.get('error', ''), 240)}"
        )

    return "\n".join(output)


def last_errors(limit=10):
    return error_history(limit=limit)


def jarvis_usage_stats():
    commands = _load_history_file(COMMAND_HISTORY_FILE)
    errors = _load_history_file(ERROR_HISTORY_FILE)

    if not commands:
        return "No usage statistics available yet."

    total = len(commands)
    successful = len(
        item for item in commands
        if item.get("status") == "SUCCESS"
    )
    failed = len(
        item for item in commands
        if item.get("status") == "ERROR"
    )

    command_counter = {}

    for item in commands:
        cmd = clean_text(
            item.get("normalized_command", "")
        )

        if not cmd:
            continue

        first_words = " ".join(cmd.split()[:3])
        command_counter[first_words] = command_counter.get(first_words, 0) + 1

    ranked = sorted(
        command_counter.items(),
        key=lambda row: row[1],
        reverse=True
    )

    output = [
        "JARVIS USAGE STATS",
        "",
        f"Total commands: {total}",
        f"Successful commands: {successful}",
        f"Failed commands: {failed}",
        f"Errors logged: {len(errors)}",
        "",
        "Most used command patterns:"
    ]

    for command, count in ranked[:15]:
        output.append(f"- {command}: {count}")

    return "\n".join(output)


def clear_old_history(keep_last=100):
    commands = _load_history_file(COMMAND_HISTORY_FILE)
    errors = _load_history_file(ERROR_HISTORY_FILE)

    commands_kept = commands[-keep_last:]
    errors_kept = errors[-keep_last:]

    _save_history_file(
        COMMAND_HISTORY_FILE,
        commands_kept
    )
    _save_history_file(
        ERROR_HISTORY_FILE,
        errors_kept
    )

    return (
        "Old history cleared.\n"
        f"Commands kept: {len(commands_kept)}\n"
        f"Errors kept: {len(errors_kept)}"
    )


def export_command_history():
    commands = _load_history_file(COMMAND_HISTORY_FILE)
    errors = _load_history_file(ERROR_HISTORY_FILE)

    _ensure_history_dir()

    path = os.path.join(
        HISTORY_DIR,
        f"jarvis_command_history_{_history_date_for_file()}.md"
    )

    content = [
        "# JARVIS Command History Export",
        "",
        f"Generated: {_history_now()}",
        "",
        "## Usage Stats",
        "",
        "```text",
        jarvis_usage_stats(),
        "```",
        "",
        "## Recent Commands",
        "",
        "```text",
        command_history(limit=100),
        "```",
        "",
        "## Recent Errors",
        "",
        "```text",
        error_history(limit=50),
        "```",
    ]

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        f.write("\n".join(content))

    return f"Command history exported:\n{path}"


def handle_history_command(command):
    lower = clean_text(command)

    if lower in {"command history", "show command history", "last commands"}:
        return command_history()

    if lower in {"error history", "show error history", "last errors"}:
        return error_history()

    if lower in {"jarvis usage stats", "usage stats", "show usage stats"}:
        return jarvis_usage_stats()

    if lower in {"clear old history", "clean old history"}:
        return clear_old_history()

    if lower in {"export command history", "export history"}:
        return export_command_history()

    return None


def handle_command_text(command, recognizer=None, microphone=None):
    command = normalize_command(command)

    update_hud(
        status="PROCESSING",
        command=command,
        result="Routing command...",
        action="Routing voice command",
        ai_status="READY",
        voice="0.1"
    )

    if not command:
        return "I heard the wake word. Please say a command."

    if clean_text(command) in EXIT_COMMANDS:
        if clean_text(command) in {"stop speaking", "stop voice", "silence"}:
            stop_speaking()
            return "Voice stopped."
        return "exit"

    history_result = handle_history_command(command)

    if history_result is not None:
        return history_result

    if any(pattern in clean_text(command) for pattern in BAD_RECOGNITION_PATTERNS):
        return "I did not understand a clean command. Please repeat clearly."

    if not has_clear_intent(command):
        return (
            "I did not understand a clear command. "
            "Use: open calculator, open project CyberShield AI, open folder downloads, "
            "review this code, explain current error, analyze current code, continue working on last project, plan project <name>, architect project <name>, or score project <name>."
        )

    if needs_confirmation(command) and recognizer is not None and microphone is not None:
        confirmed = confirm_action(recognizer, microphone, command)

        if not confirmed:
            return "Command cancelled."

    open_result = handle_open_command(command)

    if open_result is not None:
        return open_result

    # Advanced commands are delegated to jarvis_agent.py.
    command_lower = clean_text(command)

    update_hud(
        status="PROCESSING",
        command=command,
        result="Delegating to JARVIS agent...",
        action="Agent command",
        ai_status="THINKING" if any(word in command_lower for word in ["analyze", "review", "fix", "secure", "explain", "find bugs", "score", "report", "audit", "vulnerab", "api key", "password", "secret", "sql injection", "xss", "roadmap", "architect", "maturity", "production readiness", "release readiness", "deployment readiness", "go live", "dashboard", "sprint"]) else "READY",
        vision_status="ACTIVE" if ("screen" in command_lower or "current" in command_lower) else None,
        memory_status="ACTIVE" if any(word in command_lower for word in ["memory", "last", "continue", "resume", "remember"]) else "SYNC",
        ollama_status="THINKING" if any(word in command_lower for word in ["analyze", "review", "fix", "secure", "explain", "score", "report", "audit", "vulnerab", "api key", "password", "secret", "sql injection", "xss", "roadmap", "architect", "maturity", "production readiness", "release readiness", "deployment readiness", "go live", "dashboard", "sprint"]) else "LOCAL",
        voice="0.1"
    )

    return safe_handle_command(command)


def voice_summary(result):
    text = str(result).strip()

    if not text:
        return "Command completed."

    if len(text) > 500:
        lower = text.lower()

        if "last project" in lower or "last deep project" in lower:
            return "I found the last project in memory. Check the terminal for details."

        if "last project file" in lower or "last file" in lower:
            return "I found the last reviewed file. Check the terminal for details."

        if "last project audit" in lower or "last audit" in lower:
            return "I found the last audit. Check the terminal for details."

        if "project conversation summary" in lower:
            return "Memory summary generated. Check the terminal for details."


        if "jarvis project roadmap" in lower or "project roadmap" in lower:
            return "Project roadmap generated. Check the terminal and HUD for details."

        if "project architect mode" in lower or "architecture view" in lower:
            return "Project architect report completed. Check the terminal for details."

        if "release checklist" in lower:
            return "Release checklist generated. Check the terminal for details."

        if "deployment checklist" in lower:
            return "Deployment checklist generated. Check the terminal for details."

        if "production readiness estimate" in lower:
            return "Production readiness estimated. Check the terminal for details."

        if "release readiness" in lower:
            return "Release readiness report completed. Check the terminal for details."

        if "go-live report" in lower or "go live report" in lower:
            return "Go live report completed. Check the terminal for details."

        if "enterprise engineering dashboard" in lower or "enterprise dashboard" in lower:
            return "Enterprise dashboard generated. Check the terminal and HUD for details."

        if "executive portfolio dashboard" in lower or "executive dashboard" in lower:
            return "Executive dashboard generated. Check the terminal for details."

        if "engineering kpi dashboard" in lower or "kpi dashboard" in lower:
            return "KPI dashboard generated. Check the terminal for details."

        if "enterprise release dashboard" in lower or "release dashboard" in lower:
            return "Release dashboard generated. Check the terminal for details."

        if "technical debt dashboard" in lower or "debt dashboard" in lower:
            return "Technical debt dashboard generated. Check the terminal for details."

        if "project maturity estimate" in lower:
            return "Project maturity estimated. Check the terminal for details."

        if "sprint plan" in lower:
            return "Sprint plan generated. Check the terminal for details."

        if "next best improvements" in lower or "recommended next improvements" in lower:
            return "Next best improvements generated. Check the terminal for details."

        if "highest-risk findings" in lower or "highest risk vulnerabilities" in lower:
            return "Highest risk vulnerabilities report generated. Check the terminal for details."

        if "project structure" in lower:
            return "Project structure generated. Check the terminal and HUD for details."

        if "project files" in lower:
            return "Project files listed. Check the terminal for the full list."

        if "project statistics" in lower:
            return "Project statistics generated. Check the terminal for details."

        if "largest files" in lower:
            return "Largest files report generated. Check the terminal for details."

        if "full security audit" in lower:
            return "Full security audit completed. Check the terminal and HUD for details."

        if "security roadmap" in lower:
            return "Security roadmap generated. Check the terminal for details."

        if "api key" in lower or "token scan" in lower:
            return "API key scan completed. Check the terminal for details."

        if "password scan" in lower:
            return "Password scan completed. Check the terminal for details."

        if "sql injection" in lower:
            return "SQL injection scan completed. Check the terminal for details."

        if "xss" in lower:
            return "XSS scan completed. Check the terminal for details."

        if "dangerous import" in lower:
            return "Dangerous import scan completed. Check the terminal for details."

        if "security" in lower and ("risk" in lower or "issues" in lower or "report" in lower):
            return "Security report completed. Check the terminal for details."

        if "backup" in lower:
            return "Backup command completed. Check the terminal for details."

        if "command history" in lower:
            return "Command history generated. Check the terminal for details."

        if "error history" in lower:
            return "Error history generated. Check the terminal for details."

        if "usage stats" in lower:
            return "Usage statistics generated. Check the terminal for details."

        if "command history exported" in lower:
            return "Command history exported. Check the terminal for the file path."

        if "overall" in lower:
            for line in text.splitlines():
                if "overall" in line.lower():
                    return "Project analysis completed. " + line.strip()

        return "Command completed. Check the terminal for full details."

    return text


def main():
    if sr is None:
        print("Missing dependency: speech_recognition")
        print("Install with: python -m pip install SpeechRecognition pyaudio")
        return

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 250
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 1.5
    recognizer.non_speaking_duration = 0.8

    try:
        microphone = sr.Microphone()
    except Exception as e:
        print("Microphone error:", e)
        print("Try installing PyAudio:")
        print("python -m pip install pipwin")
        print("python -m pipwin install pyaudio")
        return

    print("Calibrating microphone noise level. Stay quiet for 2 seconds...")
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=2.0)
    print("Calibration done.")

    update_hud(
        status="STANDBY",
        command="JARVIS ready.",
        result="Push ENTER and speak.",
        voice="0.0",
        project="No Project",
        current_file="No File",
        action="System online",
        ai_status="READY",
        security_score="N/A",
        project_score="N/A",
        memory_status="SYNC",
        vision_status="ACTIVE",
        ollama_status="LOCAL"
    )

    print("JARVIS Push-To-Talk Voice Commands Ready")
    print("Examples:")
    print(" - open calculator")
    print(" - open chrome")
    print(" - open website wikipedia.org")
    print(" - open folder downloads")
    print(" - open file <name>")
    print(" - open project CyberShield AI")
    print(" - score project CyberShield AI")
    print(" - review this code")
    print(" - explain this error")
    print(" - find bugs")
    print(" - fix app.py from cyber shield ai")
    print(" - scan current screen project")
    print(" - analyze current code")
    print(" - find bug on current screen")
    print(" - explain current error")
    print(" - show project structure cyber shield ai")
    print(" - show project files cyber shield ai")
    print(" - show project statistics cyber shield ai")
    print(" - show largest files cyber shield ai")
    print(" - show security report cyber shield ai")
    print(" - secure cyber shield ai")
    print(" - scan cyber shield ai")
    print(" - audit cyber shield ai")
    print(" - find vulnerabilities")
    print(" - find api keys cyber shield ai")
    print(" - find passwords cyber shield ai")
    print(" - find hardcoded secrets cyber shield ai")
    print(" - find sql injection cyber shield ai")
    print(" - find xss cyber shield ai")
    print(" - find dangerous imports cyber shield ai")
    print(" - security roadmap cyber shield ai")
    print(" - what was i working on last")
    print(" - what file did we review last")
    print(" - continue last audit")
    print(" - show last security report")
    print(" - what vulnerabilities did you find")
    print(" - what projects do you remember")
    print(" - compare remembered projects")
    print(" - memory summary")
    print(" - continue working on last project")
    print(" - what should we do next")
    print(" - plan project <project>")
    print(" - architect project <project>")
    print(" - prepare release <project>")
    print(" - prepare deployment <project>")
    print(" - production readiness <project>")
    print(" - project maturity <project>")
    print(" - what should i fix next <project>")
    print(" - highest risk vulnerabilities <project>")
    print(" - generate sprint plan <project>")
    print(" - show backups")
    print(" - review CyberShield AI")
    print(" - security audit CyberShield AI")
    print(" - release readiness CyberShield AI")
    print(" - deployment readiness CyberShield AI")
    print(" - go live report CyberShield AI")
    print(" - show enterprise dashboard")
    print(" - show executive dashboard")
    print(" - show kpi dashboard")
    print(" - show release dashboard")
    print(" - show strongest projects")
    print(" - show weakest projects")
    print(" - command history")
    print(" - error history")
    print(" - jarvis usage stats")
    print(" - export command history")
    print(" - HUD Fusion updates: project score, security score, memory, vision, Ollama")
    print(" - stop listening")
    speak("Push to talk JARVIS voice mode is ready.")

    while True:
        try:
            raw_command = recognize_once(recognizer, microphone)
            command = normalize_command(raw_command)

            print("\nYou said:", raw_command)
            print("Normalized:", command)

            update_hud(
                status="PROCESSING",
                command=command,
                result="Executing command..."
            )

            result = handle_command_text(command, recognizer, microphone)

            if result == "exit":
                speak("Shutting down. Goodbye.")
                break

            print("\nResult:\n", result)

            result_text = str(result)
            result_status = "ERROR" if (
                "error" in result_text.lower()
                or "not found" in result_text.lower()
                or "could not" in result_text.lower()
                or "cancelled" in result_text.lower()
                or "did not understand" in result_text.lower()
            ) else "SUCCESS"

            log_command_history(
                raw_command,
                command,
                result_text,
                status=result_status
            )

            if result_status == "ERROR":
                log_error_history(
                    command,
                    result_text,
                    stage="command_result"
                )

            update_hud(
                status=result_status,
                command=command,
                result=short_text(result_text),
                action="Command completed",
                ai_status="READY",
                memory_status="SYNC",
                ollama_status="READY",
                voice="0.0"
            )

            update_hud_from_command_result(command, result_text)

            speak(voice_summary(result))

            update_hud(
                status="STANDBY",
                command="Press ENTER for next command.",
                result=short_text(result_text),
                action="Waiting for next command",
                ai_status="READY",
                voice="0.0"
            )

        except sr.WaitTimeoutError:
            update_hud(
                status="ERROR",
                command="No voice detected.",
                result="Press ENTER and try again.",
                voice="0.0"
            )
            continue
        except sr.UnknownValueError:
            log_error_history(
                "voice_recognition",
                "Could not understand audio.",
                stage="speech_recognition"
            )
            print("Could not understand audio. Press ENTER and try again.")
            update_hud(
                status="ERROR",
                command="Speech not understood.",
                result="Press ENTER and repeat clearly.",
                action="Voice recognition failed",
                ai_status="READY",
                ollama_status="LOCAL",
                voice="0.0"
            )
            continue
        except sr.RequestError as e:
            log_error_history(
                "speech_service",
                e,
                stage="speech_request"
            )
            print("Speech recognition request error:", e)
            update_hud(
                status="ERROR",
                command="Speech recognition error.",
                result=short_text(e),
                voice="0.0"
            )
            speak("Speech recognition service is not available.")
            time.sleep(2)
        except KeyboardInterrupt:
            print("\nManual shutdown")
            update_hud(
                status="STANDBY",
                command="Manual shutdown.",
                result="JARVIS stopped.",
                voice="0.0"
            )
            break
        except Exception as e:
            log_error_history(
                "runtime",
                e,
                stage="main_loop"
            )
            print("Error:", e)
            update_hud(
                status="ERROR",
                command="Runtime error.",
                result=short_text(e),
                action="Runtime error",
                ai_status="ERROR",
                ollama_status="ERROR",
                voice="0.0"
            )
            speak("An error occurred. Check the terminal.")



def main():
    if sr is None:
        print("speech_recognition is not installed.")
        print("Run: pip install SpeechRecognition pyaudio")
        return

    recognizer = sr.Recognizer()

    try:
        microphone = sr.Microphone()
    except Exception as error:
        print(f"Microphone error: {error}")
        return

    with microphone as source:
        print("Calibrating microphone...")
        recognizer.adjust_for_ambient_noise(source, duration=1)

    update_hud(
        status="STANDBY",
        command="Say: Hey Jarvis",
        result="Voice wake-word mode ready.",
        action="Wake-word mode",
        ai_status="READY",
        voice="0.0"
    )

    run_wake_word_mode(recognizer, microphone)


if __name__ == "__main__":
    main()



# ==========================================================
# JARVIS VOICE TEST COMMANDS
# ==========================================================
def run_voice_self_test():
    tests = [
        "hey jay open fire",
        "hi jarvis open vs code",
        "play jarvis open project cyber",
        "create pdf report cyber",
        "make powerpoint report for cyber shield ai",
        "open you tube",
        "open git hub",
        "show downloads",
        "review cyber",
        "audit cyber",
    ]

    output = ["VOICE NORMALIZATION SELF TEST", ""]

    for raw in tests:
        try:
            normalized = normalize_command(raw)
        except Exception as error:
            normalized = f"ERROR: {error}"

        output.append(f"RAW: {raw}")
        output.append(f"NORMALIZED: {normalized}")
        output.append("")

    return "\n".join(output)


def test_voice_commands():
    return run_voice_self_test()



# ==========================================================
# J.A.R.V.I.S MULTI-PROJECT IDE VOICE ROUTER
# Added safely at the end so it overrides/extends command normalization.
#
# Supports natural voice commands:
# - open project CyberShield AI in VS Code
# - open project JARVIS in VS Code
# - open ManagerApp in IntelliJ
# - open CyberShield AI with Visual Studio Community
# - edit project MyAPI using PyCharm
# - open app.py in VS Code
# - open package.json from CyberShield AI in VS Code
#
# Also supports multiple commands in one sentence:
# - open project CyberShield AI in VS Code and open project JARVIS in VS Code
# - open CyberShield AI in VS Code then open ManagerApp in IntelliJ
# ==========================================================

MULTI_IDE_ROUTER_VERSION = "J.A.R.V.I.S Multi-Project IDE Voice Router"
VOICE_IDE_MEMORY_FILE = "voice_ide_memory.json"


def _multi_ide_safe_load(path, default=None):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            return json.load(file)
    except Exception:
        return default if default is not None else {}


def _multi_ide_safe_save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _multi_ide_clean(text):
    text = str(text or "").strip()
    text = text.replace("—", " ")
    text = text.replace("–", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _multi_ide_lower(text):
    return clean_text(_multi_ide_clean(text))


IDE_VOICE_ALIASES = {
    # VS Code
    "vs code": "VS Code",
    "vscode": "VS Code",
    "visual studio code": "VS Code",
    "visual code": "VS Code",
    "code": "VS Code",
    "code editor": "VS Code",

    # Visual Studio
    "visual studio": "Visual Studio Community",
    "visual studio community": "Visual Studio Community",
    "vs community": "Visual Studio Community",
    "vscommunity": "Visual Studio Community",
    "visual community": "Visual Studio Community",
    "visual studio professional": "Visual Studio Professional",
    "visual studio enterprise": "Visual Studio Enterprise",

    # JetBrains
    "intellij": "IntelliJ",
    "intellij idea": "IntelliJ",
    "idea": "IntelliJ",
    "intelig": "IntelliJ",
    "intelli j": "IntelliJ",
    "pycharm": "PyCharm",
    "python charm": "PyCharm",
    "webstorm": "WebStorm",
    "web storm": "WebStorm",
    "rider": "Rider",
    "clion": "CLion",
    "c lion": "CLion",

    # Java / Android
    "android studio": "Android Studio",
    "androidstudio": "Android Studio",
    "eclipse": "Eclipse",
    "eclips": "Eclipse",
    "netbeans": "NetBeans",
    "net beans": "NetBeans",

    # Modern editors
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "wind surf": "Windsurf",
    "sublime": "Sublime Text",
    "sublime text": "Sublime Text",
    "notepad plus plus": "Notepad++",
    "notepad++": "Notepad++",

    # Game engines
    "unity": "Unity Hub",
    "unity hub": "Unity Hub",
    "unreal": "Unreal Engine",
    "unreal engine": "Unreal Engine",
}


PROJECT_VOICE_ALIASES_EXTENDED = {
    "cyber": "CyberShield AI",
    "cyber shield": "CyberShield AI",
    "cyber shield ai": "CyberShield AI",
    "cybershield": "CyberShield AI",
    "cybershield ai": "CyberShield AI",
    "cybers in the": "CyberShield AI",
    "cyber security app": "CyberShield AI",

    "jarvis": "J.A.R.V.I.S",
    "jervis": "J.A.R.V.I.S",
    "jar": "J.A.R.V.I.S",
    "j a r v i s": "J.A.R.V.I.S",
    "project jar": "J.A.R.V.I.S",
    "projector": "J.A.R.V.I.S",

    "manager app": "ManagerApp",
    "managerapp": "ManagerApp",
    "manager application": "ManagerApp",
}


def normalize_ide_name(spoken_ide):
    lower = _multi_ide_lower(spoken_ide)
    lower = lower.replace("-", " ").replace("_", " ")
    lower = re.sub(r"\s+", " ", lower).strip()

    if lower in IDE_VOICE_ALIASES:
        return IDE_VOICE_ALIASES[lower]

    # Fuzzy fallback for common speech recognition mistakes.
    best = None
    best_score = 0

    for alias, canonical in IDE_VOICE_ALIASES.items():
        score = difflib.SequenceMatcher(None, lower, alias).ratio()
        if score > best_score:
            best_score = score
            best = canonical

    if best and best_score >= 0.74:
        return best

    return str(spoken_ide or "").strip()


def normalize_voice_project_any(project_name):
    raw = str(project_name or "").strip()
    lower = _multi_ide_lower(raw)
    lower = lower.replace("-", " ").replace("_", " ")
    lower = re.sub(r"\s+", " ", lower).strip()

    # Remove noisy words.
    lower = re.sub(r"^(the|my|a|an)\s+", "", lower)
    lower = re.sub(r"\s+(project|application|app)$", "", lower).strip()

    if lower in PROJECT_VOICE_ALIASES_EXTENDED:
        return PROJECT_VOICE_ALIASES_EXTENDED[lower]

    # Keep original casing for unknown projects.
    return raw.strip()


def _multi_ide_load_memory():
    data = _multi_ide_safe_load(VOICE_IDE_MEMORY_FILE, {})
    return data if isinstance(data, dict) else {}


def _multi_ide_save_memory(data):
    return _multi_ide_safe_save(VOICE_IDE_MEMORY_FILE, data)


def remember_project_ide(project_name, ide_name):
    project_name = normalize_voice_project_any(project_name)
    ide_name = normalize_ide_name(ide_name)

    data = _multi_ide_load_memory()
    data.setdefault("projects", {})
    data["projects"][project_name] = ide_name
    data["last_project"] = project_name
    data["last_ide"] = ide_name
    data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    _multi_ide_save_memory(data)


def get_last_ide_for_project(project_name=None):
    data = _multi_ide_load_memory()
    project_name = normalize_voice_project_any(project_name or data.get("last_project", ""))

    if project_name and data.get("projects", {}).get(project_name):
        return data["projects"][project_name]

    return data.get("last_ide") or "VS Code"


def get_last_voice_project():
    data = _multi_ide_load_memory()
    return data.get("last_project") or get_last_project_from_memory()


def _multi_ide_project_patterns():
    ide_names = sorted(IDE_VOICE_ALIASES.keys(), key=len, reverse=True)
    ide_pattern = "|".join(re.escape(item) for item in ide_names)

    return [
        # open project CyberShield AI in VS Code
        rf"^(?:open|launch|start|edit|load)\s+(?:the\s+|my\s+)?(?:project\s+)?(.+?)\s+(?:in|with|using|on)\s+({ide_pattern})$",

        # open CyberShield AI project in VS Code
        rf"^(?:open|launch|start|edit|load)\s+(?:the\s+|my\s+)?(.+?)\s+project\s+(?:in|with|using|on)\s+({ide_pattern})$",

        # open project CyberShield AI
        r"^(?:open|launch|start|edit|load)\s+(?:the\s+|my\s+)?project\s+(.+)$",

        # open CyberShield AI
        r"^(?:open|launch|start|edit|load)\s+(.+)$",
    ]


def parse_project_ide_voice_command(command):
    """
    Returns:
    {
      "project": "...",
      "ide": "...",
      "normalized_command": "open project X in IDE"
    }
    or None.
    """
    original = _multi_ide_clean(command)
    lower = _multi_ide_lower(original)

    # Do not steal folder/site/file/app commands.
    blocked_starts = (
        "open website ",
        "open site ",
        "go to ",
        "visit ",
        "open file ",
        "open document ",
        "open folder ",
        "open directory ",
        "open application ",
        "open app ",
        "open program ",
        "open browser ",
    )

    if lower.startswith(blocked_starts):
        return None

    # Explicit IDE command with project.
    for pattern in _multi_ide_project_patterns()[:2]:
        match = re.match(pattern, lower, flags=re.IGNORECASE)
        if match:
            project = normalize_voice_project_any(match.group(1).strip())
            ide = normalize_ide_name(match.group(2).strip())

            if not project:
                project = get_last_voice_project()

            remember_project_ide(project, ide)

            return {
                "project": project,
                "ide": ide,
                "normalized_command": f"open project {project} in {ide}",
            }

    # open project X -> default/last IDE.
    match = re.match(_multi_ide_project_patterns()[2], lower, flags=re.IGNORECASE)
    if match:
        project = normalize_voice_project_any(match.group(1).strip())
        ide = get_last_ide_for_project(project)

        remember_project_ide(project, ide)

        return {
            "project": project,
            "ide": ide,
            "normalized_command": f"open project {project} in {ide}",
        }

    # Natural shortcut: "open managerapp in vscode" can be lower and without project word handled above.
    # This fallback only triggers when target looks like a known project alias.
    match = re.match(_multi_ide_project_patterns()[3], lower, flags=re.IGNORECASE)
    if match:
        target = match.group(1).strip()

        # Avoid stealing simple app names.
        app_like = {
            "firefox", "fire", "chrome", "google", "edge", "calculator", "notepad",
            "vscode", "vs code", "visual studio code", "visual studio", "intellij",
            "pycharm", "eclipse", "downloads", "documents", "desktop"
        }
        if target in app_like:
            return None

        project = normalize_voice_project_any(target)

        # Only route as project if it is clearly an alias or contains project-style words.
        known_alias = _multi_ide_lower(target) in PROJECT_VOICE_ALIASES_EXTENDED
        projectish = any(token in target for token in ["app", "api", "project", "manager", "jarvis", "cyber", "shield"])

        if known_alias or projectish:
            ide = get_last_ide_for_project(project)
            remember_project_ide(project, ide)

            return {
                "project": project,
                "ide": ide,
                "normalized_command": f"open project {project} in {ide}",
            }

    return None


def parse_project_file_ide_voice_command(command):
    """
    Examples:
    - open app.py in VS Code
    - open package.json from CyberShield AI in VS Code
    - edit Program.cs from ManagerApp with Visual Studio
    """
    text = _multi_ide_clean(command)
    lower = _multi_ide_lower(text)

    ide_names = sorted(IDE_VOICE_ALIASES.keys(), key=len, reverse=True)
    ide_pattern = "|".join(re.escape(item) for item in ide_names)

    file_pattern = r"([A-Za-z0-9_.\-\\/]+\.[A-Za-z0-9]{1,8})"

    patterns = [
        rf"^(?:open|edit|load|start)\s+(?:file\s+)?{file_pattern}\s+(?:from|in)\s+(?:project\s+)?(.+?)\s+(?:in|with|using|on)\s+({ide_pattern})$",
        rf"^(?:open|edit|load|start)\s+(?:file\s+)?{file_pattern}\s+(?:in|with|using|on)\s+({ide_pattern})$",
        rf"^(?:open|edit|load|start)\s+(?:file\s+)?{file_pattern}$",
    ]

    match = re.match(patterns[0], lower, flags=re.IGNORECASE)
    if match:
        file_query = match.group(1).strip()
        project = normalize_voice_project_any(match.group(2).strip())
        ide = normalize_ide_name(match.group(3).strip())
        remember_project_ide(project, ide)

        return {
            "file": file_query,
            "project": project,
            "ide": ide,
            "normalized_command": f"open code file {file_query} from project {project} in {ide}",
        }

    match = re.match(patterns[1], lower, flags=re.IGNORECASE)
    if match:
        file_query = match.group(1).strip()
        ide = normalize_ide_name(match.group(2).strip())
        project = get_last_voice_project()
        remember_project_ide(project, ide)

        return {
            "file": file_query,
            "project": project,
            "ide": ide,
            "normalized_command": f"open code file {file_query} from project {project} in {ide}",
        }

    match = re.match(patterns[2], lower, flags=re.IGNORECASE)
    if match:
        file_query = match.group(1).strip()
        project = get_last_voice_project()
        ide = get_last_ide_for_project(project)

        return {
            "file": file_query,
            "project": project,
            "ide": ide,
            "normalized_command": f"open code file {file_query} from project {project} in {ide}",
        }

    return None


def split_multiple_voice_commands(command):
    """
    Splits safe chained commands:
    - open A in VS Code and open B in IntelliJ
    - open A in VS Code then open B in VS Code
    It avoids splitting inside normal phrases unless another command starts.
    """
    text = _multi_ide_clean(command)

    separators = [
        r"\s+and\s+(?=open|launch|start|edit|load|review|create|generate|make)",
        r"\s+then\s+(?=open|launch|start|edit|load|review|create|generate|make)",
        r"\s*,\s*(?=open|launch|start|edit|load|review|create|generate|make)",
        r"\s*;\s*(?=open|launch|start|edit|load|review|create|generate|make)",
    ]

    parts = [text]

    for sep in separators:
        new_parts = []
        for part in parts:
            new_parts.extend(re.split(sep, part, flags=re.IGNORECASE))
        parts = new_parts

    cleaned = [part.strip() for part in parts if part.strip()]
    return cleaned if len(cleaned) > 1 else [text]


def normalize_multi_project_ide_command(command):
    """
    Normalizes one command.
    """
    file_parsed = parse_project_file_ide_voice_command(command)
    if file_parsed:
        return file_parsed["normalized_command"]

    project_parsed = parse_project_ide_voice_command(command)
    if project_parsed:
        return project_parsed["normalized_command"]

    return None


# Keep a reference to the previous normalizer and extend it.
_PRE_MULTI_IDE_NORMALIZE_COMMAND = normalize_command


def normalize_command(command):
    original = str(command or "").strip()

    if not original:
        return ""

    # First, keep existing wake removal and corrections.
    try:
        base = _PRE_MULTI_IDE_NORMALIZE_COMMAND(original)
    except Exception:
        base = original

    # Multiple commands are handled before final single-command routing.
    parts = split_multiple_voice_commands(base)

    if len(parts) > 1:
        normalized_parts = []
        for part in parts:
            routed = normalize_multi_project_ide_command(part)
            if routed:
                normalized_parts.append(routed)
            else:
                try:
                    normalized_parts.append(_PRE_MULTI_IDE_NORMALIZE_COMMAND(part))
                except Exception:
                    normalized_parts.append(part)

        return " && ".join(normalized_parts)

    routed = normalize_multi_project_ide_command(base)
    if routed:
        return routed

    routed = normalize_multi_project_ide_command(original)
    if routed:
        return routed

    return base


def execute_multiple_voice_commands(command):
    """
    Executes commands separated by && using handle_command.
    Returns combined results.
    """
    if "&&" not in str(command):
        return None

    if handle_command is None:
        return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

    results = []
    parts = [part.strip() for part in str(command).split("&&") if part.strip()]

    for index, part in enumerate(parts, start=1):
        try:
            update_hud(status="ACTIVE", command=part, action=f"Multiple command {index}/{len(parts)}")
            result = handle_command(part)
            update_hud_from_command_result(part, result)
            log_voice_command(part, part, result)
            results.append(f"{index}. {result}")
        except Exception as error:
            results.append(f"{index}. Error: {error}")

    return "\n".join(results)


# Keep a reference to the previous safe handler and extend it.
try:
    _PRE_MULTI_IDE_SAFE_HANDLE_COMMAND = safe_handle_command
except Exception:
    _PRE_MULTI_IDE_SAFE_HANDLE_COMMAND = None


def safe_handle_command(command):
    """
    Extended safe command handler:
    - executes chained commands separated by &&
    - otherwise uses previous safe_handle_command implementation
    """
    multi_result = execute_multiple_voice_commands(command)
    if multi_result is not None:
        return multi_result

    if _PRE_MULTI_IDE_SAFE_HANDLE_COMMAND is not None:
        return _PRE_MULTI_IDE_SAFE_HANDLE_COMMAND(command)

    if handle_command is None:
        return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

    return handle_command(command)


def multi_ide_router_self_test():
    tests = [
        "open project Cybershield AI in VS Code",
        "open prject JARVIS in VS Code",
        "open project JARVIS in VS Code",
        "open ManagerApp in VS Code",
        "open ManagerApp in IntelliJ",
        "open CyberShield AI with Visual Studio Community",
        "edit CyberShield AI using PyCharm",
        "open app.py in VS Code",
        "open package.json from CyberShield AI in VS Code",
        "open project CyberShield AI in VS Code and open project JARVIS in VS Code",
        "open ManagerApp in IntelliJ then open CyberShield AI in VS Code",
    ]

    output = [
        "MULTI PROJECT IDE ROUTER SELF TEST",
        f"Version: {MULTI_IDE_ROUTER_VERSION}",
        "",
    ]

    for raw in tests:
        try:
            normalized = normalize_command(raw)
        except Exception as error:
            normalized = f"ERROR: {error}"

        output.append(f"RAW: {raw}")
        output.append(f"NORMALIZED: {normalized}")
        output.append("")

    return "\n".join(output)


def show_voice_ide_memory():
    data = _multi_ide_load_memory()
    if not data:
        return "No IDE memory saved yet."

    lines = [
        "VOICE IDE MEMORY",
        f"Last project: {data.get('last_project', 'None')}",
        f"Last IDE: {data.get('last_ide', 'None')}",
        "",
        "Projects:"
    ]

    for project, ide in data.get("projects", {}).items():
        lines.append(f"- {project}: {ide}")

    return "\n".join(lines)


# Extend voice meta commands too.
_PRE_MULTI_IDE_HANDLE_VOICE_META_COMMAND = handle_voice_meta_command


def handle_voice_meta_command(command):
    lower = clean_text(command)

    if lower in {
        "multi ide test",
        "test multi ide",
        "multi project ide test",
        "test project ide router",
    }:
        return multi_ide_router_self_test()

    if lower in {
        "show ide memory",
        "voice ide memory",
        "show voice ide memory",
        "project ide memory",
    }:
        return show_voice_ide_memory()

    match = re.match(
        r"^(?:remember|save)\s+(?:ide|editor)\s+(.+?)\s+(?:for|for project)\s+(.+)$",
        command,
        flags=re.IGNORECASE
    )

    if match:
        ide = normalize_ide_name(match.group(1).strip())
        project = normalize_voice_project_any(match.group(2).strip())
        remember_project_ide(project, ide)
        return f"IDE remembered: {project} -> {ide}"

    return _PRE_MULTI_IDE_HANDLE_VOICE_META_COMMAND(command)


# ==========================================================
# J.A.R.V.I.S PROJECT + IDE VOICE STUDIO FIX
# Fixes STT noise like:
# open project CyberShield AI studio in VS Code
# -> open project CyberShield AI in VS Code
# ==========================================================

PROJECT_IDE_STUDIO_FIX_VERSION = "J.A.R.V.I.S Project IDE Studio Fix"

IDE_CANONICAL_ALIASES = {
    "vs code": "VS Code",
    "vscode": "VS Code",
    "visual studio code": "VS Code",
    "code": "VS Code",
    "visual code": "VS Code",
    "visual studio": "Visual Studio Community",
    "visual studio community": "Visual Studio Community",
    "vs community": "Visual Studio Community",
    "intellij": "IntelliJ",
    "intellij idea": "IntelliJ",
    "intelli j": "IntelliJ",
    "idea": "IntelliJ",
    "eclipse": "Eclipse",
    "eclips": "Eclipse",
    "pycharm": "PyCharm",
    "android studio": "Android Studio",
    "webstorm": "WebStorm",
    "rider": "Rider",
    "clion": "CLion",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
}

PROJECT_CANONICAL_ALIASES = {
    "cyber": "CyberShield AI",
    "cyber shield": "CyberShield AI",
    "cyber shield ai": "CyberShield AI",
    "cybershield": "CyberShield AI",
    "cybershield ai": "CyberShield AI",
    "cybershiel ai": "CyberShield AI",
    "cyber shiel ai": "CyberShield AI",
    "cybers in the": "CyberShield AI",
    "jarvis": "J.A.R.V.I.S",
    "jervis": "J.A.R.V.I.S",
    "j a r v i s": "J.A.R.V.I.S",
    "manager app": "ManagerApp",
    "managerapp": "ManagerApp",
}

PROJECT_IDE_NOISE_WORDS = {
    "studio", "student", "students", "study", "studies",
    "steady", "stereo", "status", "stadio", "radio",
    "video", "audio"
}


def _studio_fix_clean(text):
    text = str(text or "").lower().strip()
    text = text.replace("-", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _studio_fix_normalize_ide(value):
    lower = _studio_fix_clean(value)

    if lower in IDE_CANONICAL_ALIASES:
        return IDE_CANONICAL_ALIASES[lower]

    best = None
    best_score = 0.0

    for alias, canonical in IDE_CANONICAL_ALIASES.items():
        score = difflib.SequenceMatcher(None, lower, alias).ratio()

        if score > best_score:
            best = canonical
            best_score = score

    if best and best_score >= 0.72:
        return best

    return str(value or "").strip()


def _studio_fix_normalize_project(value):
    lower = _studio_fix_clean(value)

    tokens = [
        token for token in lower.split()
        if token not in PROJECT_IDE_NOISE_WORDS
    ]

    lower = " ".join(tokens).strip()
    lower = re.sub(r"^(the|my|a|an)\s+", "", lower).strip()
    lower = re.sub(r"\s+(project|application|app)$", "", lower).strip()

    if lower in PROJECT_CANONICAL_ALIASES:
        return PROJECT_CANONICAL_ALIASES[lower]

    best = None
    best_score = 0.0

    for alias, canonical in PROJECT_CANONICAL_ALIASES.items():
        score = difflib.SequenceMatcher(None, lower, alias).ratio()

        if alias in lower or lower in alias:
            score = max(score, 0.88)

        if score > best_score:
            best = canonical
            best_score = score

    if best and best_score >= 0.72:
        return best

    return str(value or "").strip()


def _studio_fix_remove_noise_before_ide(command):
    text = _studio_fix_clean(command)

    ide_pattern = "|".join(
        re.escape(alias)
        for alias in sorted(IDE_CANONICAL_ALIASES.keys(), key=len, reverse=True)
    )

    noise_pattern = "|".join(
        re.escape(word)
        for word in sorted(PROJECT_IDE_NOISE_WORDS, key=len, reverse=True)
    )

    text = re.sub(
        rf"\s+({noise_pattern})\s+(?=(?:in|with|using|on)\s+(?:{ide_pattern})\b)",
        " ",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        rf"\s+({noise_pattern})\s+(?=(?:{ide_pattern})\b)",
        " in ",
        text,
        flags=re.IGNORECASE
    )

    return re.sub(r"\s+", " ", text).strip()


def normalize_project_ide_studio_command(command):
    text = _studio_fix_remove_noise_before_ide(command)
    lower = _studio_fix_clean(text)

    ide_pattern = "|".join(
        re.escape(alias)
        for alias in sorted(IDE_CANONICAL_ALIASES.keys(), key=len, reverse=True)
    )

    patterns = [
        rf"^(?:open|launch|start|edit|load)\s+(?:the\s+|my\s+)?(?:project\s+)?(.+?)\s+(?:in|with|using|on)\s+({ide_pattern})$",
        rf"^(?:open|launch|start|edit|load)\s+(?:the\s+|my\s+)?(.+?)\s+project\s+(?:in|with|using|on)\s+({ide_pattern})$",
    ]

    for pattern in patterns:
        match = re.match(pattern, lower, flags=re.IGNORECASE)

        if match:
            project = _studio_fix_normalize_project(match.group(1).strip())
            ide = _studio_fix_normalize_ide(match.group(2).strip())

            if not project:
                project = get_last_project_from_memory()

            return f"open project {project} in {ide}"

    return None


def split_voice_chain_studio_fix(command):
    text = str(command or "").strip()

    parts = re.split(
        r"\s+(?:and|then)\s+(?=open|launch|start|edit|load|create|generate|review|analyze)",
        text,
        flags=re.IGNORECASE
    )

    cleaned = [part.strip() for part in parts if part.strip()]
    return cleaned if cleaned else [text]


_PRE_STUDIO_FIX_NORMALIZE_COMMAND = normalize_command


def normalize_command(command):
    original = str(command or "").strip()

    if not original:
        return ""

    direct_original = normalize_project_ide_studio_command(original)
    if direct_original:
        return direct_original

    try:
        base = _PRE_STUDIO_FIX_NORMALIZE_COMMAND(original)
    except Exception:
        base = original

    direct_base = normalize_project_ide_studio_command(base)
    if direct_base:
        return direct_base

    parts = split_voice_chain_studio_fix(original)

    if len(parts) > 1:
        normalized_parts = []

        for part in parts:
            routed = normalize_project_ide_studio_command(part)

            if routed:
                normalized_parts.append(routed)
            else:
                try:
                    normalized_parts.append(_PRE_STUDIO_FIX_NORMALIZE_COMMAND(part))
                except Exception:
                    normalized_parts.append(part)

        return " && ".join(normalized_parts)

    return base


def studio_fix_self_test():
    tests = [
        "open project CyberShield AI studio in VS Code",
        "open project Cybershiel AI studio in VS Code",
        "open project cyber shield ai student in vs code",
        "open project jarvis studio in vs code",
        "open project manager app studio in intellij",
        "open CyberShield AI studio with Visual Studio Code",
        "open project CyberShield AI in VS Code and open project Jarvis studio in VS Code",
    ]

    output = [
        "PROJECT IDE STUDIO FIX SELF TEST",
        f"Version: {PROJECT_IDE_STUDIO_FIX_VERSION}",
        "",
    ]

    for raw in tests:
        try:
            normalized = normalize_command(raw)
        except Exception as error:
            normalized = f"ERROR: {error}"

        output.append(f"RAW: {raw}")
        output.append(f"NORMALIZED: {normalized}")
        output.append("")

    return "\n".join(output)


try:
    _PRE_STUDIO_FIX_HANDLE_VOICE_META_COMMAND = handle_voice_meta_command
except Exception:
    _PRE_STUDIO_FIX_HANDLE_VOICE_META_COMMAND = None


def handle_voice_meta_command(command):
    lower = clean_text(command)

    if lower in {
        "studio fix test",
        "test studio fix",
        "project ide studio test",
        "test project ide studio",
    }:
        return studio_fix_self_test()

    if _PRE_STUDIO_FIX_HANDLE_VOICE_META_COMMAND is not None:
        return _PRE_STUDIO_FIX_HANDLE_VOICE_META_COMMAND(command)

    return None



# ==========================================================
# J.A.R.V.I.S FINAL VOICE ROUTER FIX
# Added at the end so it overrides previous handlers safely.
#
# Fixes:
# 1. "open jarvis in vs code" is routed to jarvis_agent.py,
#    not to Windows as literal "jarvis in vs code".
# 2. "project jarvis" becomes "open project J.A.R.V.I.S in VS Code".
# 3. Natural screen/code commands become:
#    review code on screen / analyze my screen / explain error on screen.
# 4. Chained commands with "and" / "then" are supported.
# ==========================================================

FINAL_VOICE_ROUTER_VERSION = "J.A.R.V.I.S Final Voice Router Fix"

FINAL_IDE_ALIASES = {
    "vs": "VS Code",
    "vs code": "VS Code",
    "vscode": "VS Code",
    "visual studio code": "VS Code",
    "code": "VS Code",
    "visual code": "VS Code",

    "visual studio": "Visual Studio Community",
    "visual studio community": "Visual Studio Community",
    "vs community": "Visual Studio Community",
    "visual studio professional": "Visual Studio Professional",
    "visual studio enterprise": "Visual Studio Enterprise",

    "intellij": "IntelliJ",
    "intellij idea": "IntelliJ",
    "intelli j": "IntelliJ",
    "idea": "IntelliJ",
    "jetbrains": "IntelliJ",

    "eclipse": "Eclipse",
    "eclips": "Eclipse",
    "pycharm": "PyCharm",
    "python charm": "PyCharm",
    "android studio": "Android Studio",
    "webstorm": "WebStorm",
    "web storm": "WebStorm",
    "rider": "Rider",
    "clion": "CLion",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "wind surf": "Windsurf",
}

FINAL_PROJECT_ALIASES = {
    "cyber": "CyberShield AI",
    "cyber shield": "CyberShield AI",
    "cyber shield ai": "CyberShield AI",
    "cybershield": "CyberShield AI",
    "cybershield ai": "CyberShield AI",
    "cybershiel ai": "CyberShield AI",
    "cyber shiel ai": "CyberShield AI",
    "cyber shield a i": "CyberShield AI",
    "cybers in the": "CyberShield AI",
    "cyber security app": "CyberShield AI",

    "jarvis": "J.A.R.V.I.S",
    "jervis": "J.A.R.V.I.S",
    "jar": "J.A.R.V.I.S",
    "j a r v i s": "J.A.R.V.I.S",
    "jarvis agent": "J.A.R.V.I.S",
    "jervis agent": "J.A.R.V.I.S",
    "project jar": "J.A.R.V.I.S",
    "projector": "J.A.R.V.I.S",

    "manager app": "ManagerApp",
    "managerapp": "ManagerApp",
    "manager application": "ManagerApp",
}

FINAL_PROJECT_IDE_NOISE = {
    "studio",
    "student",
    "students",
    "study",
    "studies",
    "steady",
    "status",
    "stereo",
    "radio",
    "audio",
    "video",
}

FINAL_APP_WORDS = {
    "firefox",
    "fire fox",
    "fire",
    "chrome",
    "google chrome",
    "edge",
    "calculator",
    "notepad",
    "vscode",
    "vs code",
    "visual studio code",
    "visual studio",
    "intellij",
    "eclipse",
    "pycharm",
    "downloads",
    "documents",
    "desktop",
}


def _final_router_clean(text):
    text = str(text or "").lower().strip()
    text = text.replace("-", " ").replace("_", " ")
    text = text.replace("analyse", "analyze")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _final_router_best(value, aliases, cutoff=0.72):
    lower = _final_router_clean(value)

    if lower in aliases:
        return aliases[lower]

    best_value = None
    best_score = 0.0

    for alias, canonical in aliases.items():
        score = 0.0

        if alias in lower or lower in alias:
            score = 0.90
        else:
            try:
                score = difflib.SequenceMatcher(None, lower, alias).ratio()
            except Exception:
                score = 0.0

        if score > best_score:
            best_score = score
            best_value = canonical

    if best_value and best_score >= cutoff:
        return best_value

    return str(value or "").strip()


def _final_router_project(value):
    lower = _final_router_clean(value)

    words = [
        word for word in lower.split()
        if word not in FINAL_PROJECT_IDE_NOISE
    ]

    lower = " ".join(words).strip()
    lower = re.sub(r"^(the|my|a|an)\s+", "", lower).strip()
    lower = re.sub(r"\s+(project|application|app)$", "", lower).strip()

    return _final_router_best(lower, FINAL_PROJECT_ALIASES, cutoff=0.70)


def _final_router_ide(value):
    return _final_router_best(value, FINAL_IDE_ALIASES, cutoff=0.70)


def _final_router_strip_noise(command):
    text = _final_router_clean(command)

    ide_pattern = "|".join(
        re.escape(alias)
        for alias in sorted(FINAL_IDE_ALIASES.keys(), key=len, reverse=True)
    )
    noise_pattern = "|".join(
        re.escape(word)
        for word in sorted(FINAL_PROJECT_IDE_NOISE, key=len, reverse=True)
    )

    # CyberShield AI studio in VS Code -> CyberShield AI in VS Code
    text = re.sub(
        rf"\s+({noise_pattern})\s+(?=(?:in|with|using|on)\s+(?:{ide_pattern})\b)",
        " ",
        text,
        flags=re.IGNORECASE
    )

    # CyberShield AI studio VS Code -> CyberShield AI in VS Code
    text = re.sub(
        rf"\s+({noise_pattern})\s+(?=(?:{ide_pattern})\b)",
        " in ",
        text,
        flags=re.IGNORECASE
    )

    return re.sub(r"\s+", " ", text).strip()


def parse_final_project_ide_command(command):
    """
    Detects project + IDE commands before handle_open_command can misroute them.
    """
    text = _final_router_strip_noise(command)

    if not text:
        return None

    ide_pattern = "|".join(
        re.escape(alias)
        for alias in sorted(FINAL_IDE_ALIASES.keys(), key=len, reverse=True)
    )

    patterns = [
        # open project jarvis in vs code
        rf"^(?:open|launch|start|edit|load)\s+(?:the\s+|my\s+)?(?:project\s+)?(.+?)\s+(?:in|with|using|on)\s+({ide_pattern})$",

        # open jarvis project in vs code
        rf"^(?:open|launch|start|edit|load)\s+(?:the\s+|my\s+)?(.+?)\s+project\s+(?:in|with|using|on)\s+({ide_pattern})$",

        # project jarvis in vs code
        rf"^(?:project)\s+(.+?)\s+(?:in|with|using|on)\s+({ide_pattern})$",
    ]

    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)

        if match:
            raw_project = match.group(1).strip()
            raw_ide = match.group(2).strip()

            project = _final_router_project(raw_project)
            ide = _final_router_ide(raw_ide)

            if not project:
                return None

            return {
                "project": project,
                "ide": ide,
                "command": f"open project {project} in {ide}",
            }

    # project jarvis -> open project jarvis in last/default IDE
    match = re.match(
        r"^(?:project)\s+(.+)$",
        text,
        flags=re.IGNORECASE
    )

    if match:
        project = _final_router_project(match.group(1).strip())
        ide = "VS Code"

        return {
            "project": project,
            "ide": ide,
            "command": f"open project {project} in {ide}",
        }

    # open jarvis -> project, not app/file, for known aliases only.
    match = re.match(
        r"^(?:open|launch|start|edit|load)\s+(.+)$",
        text,
        flags=re.IGNORECASE
    )

    if match:
        target = match.group(1).strip()

        if target in FINAL_APP_WORDS:
            return None

        target_project = _final_router_project(target)
        target_lower = _final_router_clean(target)

        if target_lower in FINAL_PROJECT_ALIASES:
            return {
                "project": target_project,
                "ide": "VS Code",
                "command": f"open project {target_project} in VS Code",
            }

    return None


def normalize_final_screen_code_command(command):
    lower = _final_router_clean(command)

    if not lower:
        return None

    screen_words = {"screen", "display", "monitor", "window", "current screen"}
    code_words = {"code", "file", "script", "function", "terminal", "error"}

    # Fix very natural but imperfect STT phrases.
    replacements = {
        "analyse code you find out in my screen": "review code on screen",
        "analyze code you find out in my screen": "review code on screen",
        "analyze code you find on my screen": "review code on screen",
        "analyse code you find on my screen": "review code on screen",
        "analyze code from my screen": "review code on screen",
        "analyse code from my screen": "review code on screen",
        "review code from my screen": "review code on screen",
        "look at my code": "review code on screen",
        "look at this code": "review code on screen",
        "check my code": "review code on screen",
        "check this code": "review code on screen",
        "read my code": "read code on screen",
        "read this code": "read code on screen",
        "find issue in this code": "find bugs on screen",
        "find issues in this code": "find bugs on screen",
        "find problem in this code": "find bugs on screen",
        "find problems in this code": "find bugs on screen",
        "why this code doesn't work": "explain error on screen",
        "why this code does not work": "explain error on screen",
        "why is this not working": "explain error on screen",
        "what is wrong with this code": "explain error on screen",
        "what is wrong on screen": "explain error on screen",
        "analyze current display": "analyze my screen",
        "analyze display": "analyze my screen",
        "read display": "read screen",
        "scan screen": "analyze my screen",
        "scan current screen": "analyze my screen",
    }

    if lower in replacements:
        return replacements[lower]

    if "error" in lower and any(word in lower for word in ["explain", "what", "why", "screen", "current"]):
        return "explain error on screen"

    if "bug" in lower and any(word in lower for word in ["find", "check", "search", "screen", "code"]):
        return "find bugs on screen"

    if "code" in lower and any(word in lower for word in ["review", "analyze", "analyse", "check", "look", "read", "scan"]):
        if "read" in lower:
            return "read code on screen"
        return "review code on screen"

    if any(word in lower for word in screen_words) and any(word in lower for word in ["analyze", "analyse", "look", "read", "scan", "explain"]):
        return "analyze my screen"

    if "current" in lower and any(word in lower for word in code_words):
        return "review code on screen"

    return None


def split_final_voice_chain(command):
    text = str(command or "").strip()

    parts = re.split(
        r"\s+(?:and|then)\s+(?=open|launch|start|edit|load|create|generate|review|analyze|analyse|read|find|explain|project)",
        text,
        flags=re.IGNORECASE
    )

    cleaned = [part.strip() for part in parts if part.strip()]
    return cleaned if cleaned else [text]


_PRE_FINAL_ROUTER_NORMALIZE_COMMAND = normalize_command


def normalize_command(command):
    original = str(command or "").strip()

    if not original:
        return ""

    # 1. Highest priority: project + IDE.
    parsed = parse_final_project_ide_command(original)
    if parsed:
        return parsed["command"]

    # 2. Screen / code review commands.
    screen_command = normalize_final_screen_code_command(original)
    if screen_command:
        return screen_command

    # 3. Previous normalizer.
    try:
        base = _PRE_FINAL_ROUTER_NORMALIZE_COMMAND(original)
    except Exception:
        base = original

    # 4. Try again after previous normalization.
    parsed = parse_final_project_ide_command(base)
    if parsed:
        return parsed["command"]

    screen_command = normalize_final_screen_code_command(base)
    if screen_command:
        return screen_command

    # 5. Chained commands.
    parts = split_final_voice_chain(original)

    if len(parts) > 1:
        normalized_parts = []

        for part in parts:
            parsed_part = parse_final_project_ide_command(part)
            if parsed_part:
                normalized_parts.append(parsed_part["command"])
                continue

            screen_part = normalize_final_screen_code_command(part)
            if screen_part:
                normalized_parts.append(screen_part)
                continue

            try:
                normalized_parts.append(_PRE_FINAL_ROUTER_NORMALIZE_COMMAND(part))
            except Exception:
                normalized_parts.append(part)

        return " && ".join(normalized_parts)

    return base


_PRE_FINAL_ROUTER_HAS_CLEAR_INTENT = has_clear_intent if "has_clear_intent" in globals() else None


def has_clear_intent(command):
    lower = clean_text(command)

    if "&&" in lower:
        return True

    if parse_final_project_ide_command(command):
        return True

    if normalize_final_screen_code_command(command):
        return True

    if lower.startswith(("project ", "open project ", "open ", "review ", "analyze ", "analyse ", "read ", "find ", "explain ")):
        return True

    if _PRE_FINAL_ROUTER_HAS_CLEAR_INTENT is not None:
        try:
            return _PRE_FINAL_ROUTER_HAS_CLEAR_INTENT(command)
        except Exception:
            pass

    return bool(lower)


_PRE_FINAL_ROUTER_HANDLE_OPEN_COMMAND = handle_open_command


def handle_open_command(command):
    """
    Project + IDE commands must bypass universal open.
    Otherwise Windows tries to execute literal strings like:
    'jarvis in vs code'.
    """
    normalized = normalize_command(command)

    parsed = parse_final_project_ide_command(normalized) or parse_final_project_ide_command(command)

    if parsed:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

        return handle_command(parsed["command"])

    if "&&" in normalized:
        return None

    return _PRE_FINAL_ROUTER_HANDLE_OPEN_COMMAND(normalized)


_PRE_FINAL_ROUTER_SAFE_HANDLE_COMMAND = safe_handle_command if "safe_handle_command" in globals() else None


def safe_handle_command(command):
    normalized = normalize_command(command)

    if "&&" in normalized:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

        results = []

        for index, part in enumerate([p.strip() for p in normalized.split("&&") if p.strip()], start=1):
            try:
                result = handle_command(part)
                results.append(f"{index}. {result}")
            except Exception as error:
                results.append(f"{index}. Error: {error}")

        return "\n".join(results)

    if _PRE_FINAL_ROUTER_SAFE_HANDLE_COMMAND is not None:
        return _PRE_FINAL_ROUTER_SAFE_HANDLE_COMMAND(normalized)

    if handle_command is None:
        return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

    return handle_command(normalized)


_PRE_FINAL_ROUTER_HANDLE_COMMAND_TEXT = handle_command_text


def handle_command_text(command, recognizer=None, microphone=None):
    raw_command = str(command or "").strip()
    command = normalize_command(raw_command)

    update_hud(
        status="PROCESSING",
        command=command,
        result="Routing command...",
        action="Final voice router",
        ai_status="READY",
        voice="0.1"
    )

    if not command:
        return "I heard the wake word. Please say a command."

    if clean_text(command) in EXIT_COMMANDS:
        return "exit"

    if "&&" in command:
        result = safe_handle_command(command)
        log_voice_command(raw_command, command, result)
        return result

    # Project + IDE must go directly to jarvis_agent.py.
    parsed = parse_final_project_ide_command(command)
    if parsed:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

        result = handle_command(parsed["command"])
        log_voice_command(raw_command, parsed["command"], result)
        return result

    # Screen/code commands must go directly to jarvis_agent.py.
    screen_command = normalize_final_screen_code_command(command)
    if screen_command:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

        result = handle_command(screen_command)
        log_voice_command(raw_command, screen_command, result)
        return result

    # Keep old behavior for everything else.
    try:
        return _PRE_FINAL_ROUTER_HANDLE_COMMAND_TEXT(command, recognizer, microphone)
    except TypeError:
        return _PRE_FINAL_ROUTER_HANDLE_COMMAND_TEXT(command)


def final_voice_router_self_test():
    tests = [
        "project jarvis",
        "open jarvis",
        "open jarvis in vs code",
        "open project jarvis in vs code",
        "open cyber shield ai in vs code",
        "open project CyberShield AI studio in VS Code",
        "open manager app in intellij",
        "analyse code you find out in my screen",
        "look at my code",
        "why this code does not work",
        "open jarvis in vs code then review current code",
    ]

    output = [
        "FINAL VOICE ROUTER SELF TEST",
        f"Version: {FINAL_VOICE_ROUTER_VERSION}",
        "",
    ]

    for raw in tests:
        try:
            normalized = normalize_command(raw)
        except Exception as error:
            normalized = f"ERROR: {error}"

        output.append(f"RAW: {raw}")
        output.append(f"NORMALIZED: {normalized}")
        output.append("")

    return "\n".join(output)


try:
    _PRE_FINAL_ROUTER_HANDLE_VOICE_META_COMMAND = handle_voice_meta_command
except Exception:
    _PRE_FINAL_ROUTER_HANDLE_VOICE_META_COMMAND = None


def handle_voice_meta_command(command):
    lower = clean_text(command)

    if lower in {
        "final router test",
        "test final router",
        "voice router test",
        "test voice router",
    }:
        return final_voice_router_self_test()

    if _PRE_FINAL_ROUTER_HANDLE_VOICE_META_COMMAND is not None:
        return _PRE_FINAL_ROUTER_HANDLE_VOICE_META_COMMAND(command)

    return None



# ==========================================================
# J.A.R.V.I.S NLP PATTERN ROUTER - FINAL PROJECT/IDE FIX
# Appended at the end so it overrides older routing safely.
#
# Main goals:
# - "open jarvis in vscode" -> "open project J.A.R.V.I.S in VS Code"
# - "open cyber in vs code" -> "open project CyberShield AI in VS Code"
# - "open manager app in intellij" -> "open project ManagerApp in IntelliJ"
# - "project jarvis" -> "open project J.A.R.V.I.S in VS Code"
# - "review code on my screen" -> "review code on screen"
# - Stop Windows from opening literal strings like "jarvis in vs code".
# ==========================================================

NLP_PATTERN_ROUTER_VERSION = "J.A.R.V.I.S NLP Pattern Router"

NLP_IDE_ALIASES = {
    "vs": "VS Code",
    "vs code": "VS Code",
    "vscode": "VS Code",
    "visual studio code": "VS Code",
    "visual code": "VS Code",
    "code": "VS Code",

    "visual studio": "Visual Studio Community",
    "visual studio community": "Visual Studio Community",
    "vs community": "Visual Studio Community",
    "visual studio professional": "Visual Studio Professional",
    "visual studio enterprise": "Visual Studio Enterprise",

    "intellij": "IntelliJ",
    "intellij idea": "IntelliJ",
    "intelli j": "IntelliJ",
    "idea": "IntelliJ",
    "jetbrains": "IntelliJ",

    "eclipse": "Eclipse",
    "eclips": "Eclipse",
    "pycharm": "PyCharm",
    "python charm": "PyCharm",
    "android studio": "Android Studio",
    "webstorm": "WebStorm",
    "web storm": "WebStorm",
    "rider": "Rider",
    "clion": "CLion",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "wind surf": "Windsurf",
    "sublime": "Sublime Text",
    "sublime text": "Sublime Text",
}

NLP_PROJECT_ALIASES = {
    "cyber": "CyberShield AI",
    "cyber shield": "CyberShield AI",
    "cyber shield ai": "CyberShield AI",
    "cybershield": "CyberShield AI",
    "cybershield ai": "CyberShield AI",
    "cybershiel ai": "CyberShield AI",
    "cyber shiel ai": "CyberShield AI",
    "cyber shield a i": "CyberShield AI",
    "cybers in the": "CyberShield AI",
    "cyber security app": "CyberShield AI",

    "jarvis": "J.A.R.V.I.S",
    "jervis": "J.A.R.V.I.S",
    "jar": "J.A.R.V.I.S",
    "j a r v i s": "J.A.R.V.I.S",
    "jarvis agent": "J.A.R.V.I.S",
    "jervis agent": "J.A.R.V.I.S",
    "project jar": "J.A.R.V.I.S",
    "projector": "J.A.R.V.I.S",

    "manager app": "ManagerApp",
    "managerapp": "ManagerApp",
    "manager application": "ManagerApp",
}

NLP_APP_TARGETS = {
    "firefox", "fire fox", "fire", "fox", "mozilla",
    "chrome", "google chrome", "edge", "calculator", "calc",
    "notepad", "paint", "cmd", "powershell", "terminal",
    "downloads", "documents", "desktop", "pictures", "music", "videos",
}

NLP_NOISE_WORDS = {
    "studio",
    "student",
    "students",
    "study",
    "studies",
    "steady",
    "status",
    "stereo",
    "audio",
    "video",
    "radio",
    "assistant",
}


def nlp_clean(text):
    text = str(text or "").lower().strip()
    text = text.replace("analyse", "analyze")
    text = text.replace("-", " ")
    text = text.replace("_", " ")
    text = text.replace(".", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def nlp_strip_polite(text):
    text = nlp_clean(text)

    prefixes = [
        "please ",
        "can you ",
        "could you ",
        "would you ",
        "jarvis ",
        "hey jarvis ",
        "ok jarvis ",
        "okay jarvis ",
    ]

    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                changed = True

    return text


def nlp_best_alias(value, aliases, cutoff=0.70):
    value = nlp_clean(value)

    if value in aliases:
        return aliases[value]

    best = None
    best_score = 0.0

    for alias, canonical in aliases.items():
        if value == alias:
            score = 1.0
        elif alias in value or value in alias:
            score = 0.90
        else:
            score = difflib.SequenceMatcher(None, value, alias).ratio()

        if score > best_score:
            best_score = score
            best = canonical

    if best and best_score >= cutoff:
        return best

    return str(value or "").strip()


def nlp_normalize_project(value):
    value = nlp_clean(value)

    words = [word for word in value.split() if word not in NLP_NOISE_WORDS]
    value = " ".join(words).strip()

    value = re.sub(r"^(the|my|a|an)\s+", "", value).strip()
    value = re.sub(r"\s+(project|application|app)$", "", value).strip()

    return nlp_best_alias(value, NLP_PROJECT_ALIASES, cutoff=0.68)


def nlp_normalize_ide(value):
    return nlp_best_alias(value, NLP_IDE_ALIASES, cutoff=0.68)


def nlp_ide_pattern():
    return "|".join(
        re.escape(alias)
        for alias in sorted(NLP_IDE_ALIASES.keys(), key=len, reverse=True)
    )


def nlp_strip_project_ide_noise(text):
    text = nlp_strip_polite(text)
    ide_pattern = nlp_ide_pattern()
    noise_pattern = "|".join(
        re.escape(word)
        for word in sorted(NLP_NOISE_WORDS, key=len, reverse=True)
    )

    # CyberShield AI studio in VS Code -> CyberShield AI in VS Code
    text = re.sub(
        rf"\s+({noise_pattern})\s+(?=(?:in|with|using|on)\s+(?:{ide_pattern})\b)",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # CyberShield AI studio VS Code -> CyberShield AI in VS Code
    text = re.sub(
        rf"\s+({noise_pattern})\s+(?=(?:{ide_pattern})\b)",
        " in ",
        text,
        flags=re.IGNORECASE,
    )

    return re.sub(r"\s+", " ", text).strip()


def nlp_parse_project_ide(text):
    text = nlp_strip_project_ide_noise(text)

    if not text:
        return None

    ide_pattern = nlp_ide_pattern()

    patterns = [
        # open project jarvis in vs code
        rf"^(?:open|launch|start|edit|load|work on|continue)\s+(?:the\s+|my\s+)?(?:project\s+)?(.+?)\s+(?:in|with|using|on)\s+({ide_pattern})$",

        # open jarvis project in vs code
        rf"^(?:open|launch|start|edit|load|work on|continue)\s+(?:the\s+|my\s+)?(.+?)\s+project\s+(?:in|with|using|on)\s+({ide_pattern})$",

        # project jarvis in vs code
        rf"^project\s+(.+?)\s+(?:in|with|using|on)\s+({ide_pattern})$",
    ]

    for pattern in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        project = nlp_normalize_project(match.group(1))
        ide = nlp_normalize_ide(match.group(2))

        if not project:
            continue

        return f"open project {project} in {ide}"

    # "project jarvis" -> default VS Code
    match = re.match(r"^project\s+(.+)$", text, flags=re.IGNORECASE)
    if match:
        project = nlp_normalize_project(match.group(1))
        if project:
            return f"open project {project} in VS Code"

    # "open jarvis" -> default VS Code only if known project alias.
    match = re.match(r"^(?:open|launch|start|edit|load|work on|continue)\s+(.+)$", text, flags=re.IGNORECASE)
    if match:
        target = nlp_clean(match.group(1))
        if target in NLP_APP_TARGETS:
            return None

        if target in NLP_PROJECT_ALIASES:
            project = nlp_normalize_project(target)
            return f"open project {project} in VS Code"

    return None


def nlp_parse_screen_code(text):
    text = nlp_strip_polite(text)

    if not text:
        return None

    exact = {
        "analyze code you find out in my screen": "review code on screen",
        "analyze code you find in my screen": "review code on screen",
        "analyze code you find on my screen": "review code on screen",
        "analyze code from my screen": "review code on screen",
        "review code from my screen": "review code on screen",
        "review this code": "review code on screen",
        "review code": "review code on screen",
        "check this code": "review code on screen",
        "check my code": "review code on screen",
        "look at my code": "review code on screen",
        "look at this code": "review code on screen",
        "read this code": "read code on screen",
        "read my code": "read code on screen",
        "scan screen": "analyze my screen",
        "scan current screen": "analyze my screen",
        "look at my screen": "analyze my screen",
        "analyze display": "analyze my screen",
        "analyze current display": "analyze my screen",
        "what do you see": "analyze my screen",
        "what is wrong here": "explain error on screen",
        "what's wrong here": "explain error on screen",
        "what is wrong with this code": "explain error on screen",
        "why this code does not work": "explain error on screen",
        "why this code doesn't work": "explain error on screen",
        "why is this not working": "explain error on screen",
        "explain current error": "explain error on screen",
        "explain this error": "explain error on screen",
        "find bugs": "find bugs on screen",
        "find the bug": "find bugs on screen",
        "find bugs in this code": "find bugs on screen",
    }

    if text in exact:
        return exact[text]

    if "error" in text and any(word in text for word in ["explain", "why", "what", "screen", "current"]):
        return "explain error on screen"

    if "bug" in text and any(word in text for word in ["find", "check", "search", "scan"]):
        return "find bugs on screen"

    if "code" in text and any(word in text for word in ["review", "analyze", "check", "look", "scan"]):
        return "review code on screen"

    if "code" in text and "read" in text:
        return "read code on screen"

    if "screen" in text and any(word in text for word in ["analyze", "scan", "look", "read", "explain"]):
        return "analyze my screen"

    if "current" in text and any(word in text for word in ["file", "code"]):
        return "review code on screen"

    return None


def nlp_parse_report(text):
    text = nlp_strip_polite(text)

    if "report" not in text and "presentation" not in text and "spreadsheet" not in text:
        return None

    project = None

    # Use explicit project if present.
    for alias, canonical in NLP_PROJECT_ALIASES.items():
        if alias in text:
            project = canonical
            break

    if not project:
        if "this project" in text or "current project" in text:
            project = get_last_project_from_memory()
        else:
            project = get_last_project_from_memory()

    if any(word in text for word in ["word", "doc", "docx"]):
        fmt = "word"
    elif any(word in text for word in ["powerpoint", "ppt", "pptx", "presentation"]):
        fmt = "powerpoint"
    elif any(word in text for word in ["excel", "xls", "xlsx", "spreadsheet"]):
        fmt = "excel"
    else:
        fmt = "pdf"

    return f"create {fmt} report for project {project}"


def nlp_split_chain(text):
    text = str(text or "").strip()

    parts = re.split(
        r"\s+(?:and|then)\s+(?=open|launch|start|edit|load|work|continue|project|review|analyze|analyse|read|find|explain|create|generate|make|export|scan|check)",
        text,
        flags=re.IGNORECASE,
    )

    cleaned = [part.strip() for part in parts if part.strip()]
    return cleaned if cleaned else [text]


def nlp_route_one(text):
    for parser in [
        nlp_parse_project_ide,
        nlp_parse_screen_code,
        nlp_parse_report,
    ]:
        try:
            routed = parser(text)
            if routed:
                return routed
        except Exception:
            pass

    return None


_PRE_NLP_PATTERN_NORMALIZE_COMMAND = normalize_command


def normalize_command(command):
    raw = str(command or "").strip()

    if not raw:
        return ""

    raw_no_wake = remove_wake_word(raw)
    raw_no_wake = collapse_repeated_command_words(raw_no_wake)

    # First: pattern router on original text, before old exact rules.
    parts = nlp_split_chain(raw_no_wake)

    if len(parts) > 1:
        routed_parts = []

        for part in parts:
            routed = nlp_route_one(part)

            if routed:
                routed_parts.append(routed)
            else:
                try:
                    routed_parts.append(_PRE_NLP_PATTERN_NORMALIZE_COMMAND(part))
                except Exception:
                    routed_parts.append(part)

        return " && ".join(routed_parts)

    routed = nlp_route_one(raw_no_wake)

    if routed:
        return routed

    # Then run old normalizer.
    try:
        base = _PRE_NLP_PATTERN_NORMALIZE_COMMAND(raw)
    except Exception:
        base = raw_no_wake

    # Try again after old normalizer.
    routed = nlp_route_one(base)

    if routed:
        return routed

    return base


try:
    _PRE_NLP_PATTERN_HAS_CLEAR_INTENT = has_clear_intent
except Exception:
    _PRE_NLP_PATTERN_HAS_CLEAR_INTENT = None


def has_clear_intent(command):
    normalized = normalize_command(command)
    lower = clean_text(normalized)

    if "&&" in lower:
        return True

    if nlp_route_one(command) or nlp_route_one(normalized):
        return True

    if lower.startswith((
        "open project ",
        "review code on screen",
        "read code on screen",
        "analyze my screen",
        "explain error on screen",
        "find bugs on screen",
        "create pdf report",
        "create word report",
        "create excel report",
        "create powerpoint report",
    )):
        return True

    if _PRE_NLP_PATTERN_HAS_CLEAR_INTENT is not None:
        try:
            return _PRE_NLP_PATTERN_HAS_CLEAR_INTENT(command)
        except Exception:
            pass

    return bool(lower)


try:
    _PRE_NLP_PATTERN_HANDLE_OPEN_COMMAND = handle_open_command
except Exception:
    _PRE_NLP_PATTERN_HANDLE_OPEN_COMMAND = None


def handle_open_command(command):
    """
    Important fix:
    Project+IDE commands must be routed to jarvis_agent.handle_command(),
    not opened through Windows/open_target as literal text.
    """
    normalized = normalize_command(command)
    routed = nlp_parse_project_ide(normalized) or nlp_parse_project_ide(command)

    if routed:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

        return handle_command(routed)

    if "&&" in normalized:
        return None

    if _PRE_NLP_PATTERN_HANDLE_OPEN_COMMAND is not None:
        return _PRE_NLP_PATTERN_HANDLE_OPEN_COMMAND(normalized)

    return None


try:
    _PRE_NLP_PATTERN_SAFE_HANDLE_COMMAND = safe_handle_command
except Exception:
    _PRE_NLP_PATTERN_SAFE_HANDLE_COMMAND = None


def safe_handle_command(command):
    normalized = normalize_command(command)

    if "&&" in normalized:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

        results = []
        commands = [part.strip() for part in normalized.split("&&") if part.strip()]

        for index, part in enumerate(commands, start=1):
            try:
                result = handle_command(part)
                results.append(f"{index}. {result}")
            except Exception as error:
                results.append(f"{index}. Error: {error}")

        return "\n".join(results)

    routed = nlp_parse_project_ide(normalized)
    if routed:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"
        return handle_command(routed)

    routed = nlp_parse_screen_code(normalized)
    if routed:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"
        return handle_command(routed)

    if _PRE_NLP_PATTERN_SAFE_HANDLE_COMMAND is not None:
        return _PRE_NLP_PATTERN_SAFE_HANDLE_COMMAND(normalized)

    if handle_command is None:
        return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

    return handle_command(normalized)


try:
    _PRE_NLP_PATTERN_HANDLE_COMMAND_TEXT = handle_command_text
except Exception:
    _PRE_NLP_PATTERN_HANDLE_COMMAND_TEXT = None


def handle_command_text(command, recognizer=None, microphone=None):
    raw = str(command or "").strip()
    normalized = normalize_command(raw)

    update_hud(
        status="PROCESSING",
        command=normalized,
        result="Routing command...",
        action="NLP Pattern Router",
        ai_status="READY",
        voice="0.1",
    )

    if not normalized:
        return "I heard the wake word. Please say a command."

    if clean_text(normalized) in EXIT_COMMANDS:
        return "exit"

    if "&&" in normalized:
        result = safe_handle_command(normalized)
        log_voice_command(raw, normalized, result)
        return result

    # Force project+IDE and screen/code commands directly into jarvis_agent.
    routed = nlp_parse_project_ide(normalized)
    if routed:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"
        result = handle_command(routed)
        log_voice_command(raw, routed, result)
        return result

    screen = nlp_parse_screen_code(normalized)
    if screen:
        if handle_command is None:
            return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"
        result = handle_command(screen)
        log_voice_command(raw, screen, result)
        return result

    if _PRE_NLP_PATTERN_HANDLE_COMMAND_TEXT is not None:
        try:
            result = _PRE_NLP_PATTERN_HANDLE_COMMAND_TEXT(normalized, recognizer, microphone)
        except TypeError:
            result = _PRE_NLP_PATTERN_HANDLE_COMMAND_TEXT(normalized)

        log_voice_command(raw, normalized, result)
        return result

    if handle_command is None:
        return f"JARVIS agent not available: {JARVIS_AGENT_IMPORT_ERROR}"

    result = handle_command(normalized)
    log_voice_command(raw, normalized, result)
    return result


def nlp_pattern_router_self_test():
    tests = [
        "open jarvis in vscode",
        "open jarvis in vs code",
        "open project jarvis in vs code",
        "project jarvis",
        "open cyber in vs code",
        "open cyber shield ai studio in vs code",
        "open manager app in intellij",
        "open managerapp with eclipse",
        "analyze code you find out in my screen",
        "review this code",
        "why this code does not work",
        "open jarvis in vscode then review current code",
        "give me a report about this project in pdf",
    ]

    lines = [
        "NLP PATTERN ROUTER SELF TEST",
        f"Version: {NLP_PATTERN_ROUTER_VERSION}",
        "",
    ]

    for item in tests:
        try:
            normalized = normalize_command(item)
        except Exception as error:
            normalized = f"ERROR: {error}"

        lines.append(f"RAW: {item}")
        lines.append(f"NORMALIZED: {normalized}")
        lines.append("")

    return "\n".join(lines)


try:
    _PRE_NLP_PATTERN_HANDLE_VOICE_META_COMMAND = handle_voice_meta_command
except Exception:
    _PRE_NLP_PATTERN_HANDLE_VOICE_META_COMMAND = None


def handle_voice_meta_command(command):
    lower = clean_text(command)

    if lower in {
        "nlp router test",
        "test nlp router",
        "voice router test",
        "test voice router",
        "pattern router test",
    }:
        return nlp_pattern_router_self_test()

    if _PRE_NLP_PATTERN_HANDLE_VOICE_META_COMMAND is not None:
        return _PRE_NLP_PATTERN_HANDLE_VOICE_META_COMMAND(command)

    return None

