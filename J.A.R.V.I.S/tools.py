import os
import sys
import json
import webbrowser
import subprocess
import shutil
from pathlib import Path
import re
import difflib
import string
import time

from project_analyzer import analyze_project

ROOT_SEARCH = str(Path.home())

APP_INDEX_FILE = "apps_index.json"
PROJECT_INDEX_FILE = "projects_index.json"

# Smart Auto Indexer metadata.
# This file allows J.A.R.V.I.S to avoid rebuilding indexes at every startup.
INDEX_METADATA_FILE = "index_metadata.json"

# How long an index is considered fresh.
# 24 hours is a good balance: fast startup + still detects new projects/apps daily.
SMART_INDEX_MAX_AGE_SECONDS = 24 * 60 * 60

# ==========================================================
# JARVIS ENTERPRISE OPENING / DISPLAY HELPERS
# ==========================================================
# Goal:
# - Open apps/sites/files/folders/projects more reliably.
# - Never speak long paths when opening something.
# - Return clean messages like: "Opening Firefox", "Opening Downloads".
# ==========================================================

OPEN_CACHE_FILE = "open_cache.json"


def _safe_load_json_file(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data

    except Exception:
        return default if default is not None else {}


def _safe_save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return True

    except Exception:
        return False


def _display_name(value):
    text = str(value or "").strip().strip('"')

    if not text:
        return "item"

    text = os.path.expandvars(text)
    text = text.replace("\\", "/").rstrip("/")

    if text.startswith("http://") or text.startswith("https://"):
        try:
            text = re.sub(r"^https?://", "", text)
            text = text.split("/")[0]
        except Exception:
            pass

    if "/" in text:
        text = text.split("/")[-1]

    if not text:
        return "item"

    # Remove noisy executable suffixes for speech/display.
    clean = text
    if clean.lower().endswith(".exe"):
        clean = clean[:-4]

    pretty = {
        "chrome": "Chrome",
        "google chrome": "Chrome",
        "firefox": "Firefox",
        "msedge": "Microsoft Edge",
        "edge": "Microsoft Edge",
        "code": "VS Code",
        "vscode": "VS Code",
        "visual studio code": "VS Code",
        "devenv": "Visual Studio Community",
        "visual studio": "Visual Studio Community",
        "visual studio community": "Visual Studio Community",
        "idea64": "IntelliJ IDEA",
        "idea": "IntelliJ IDEA",
        "intellij": "IntelliJ IDEA",
        "pycharm64": "PyCharm",
        "pycharm": "PyCharm",
        "studio64": "Android Studio",
        "calc": "Calculator",
        "calculator": "Calculator",
        "notepad": "Notepad",
        "mspaint": "Paint",
        "cmd": "Command Prompt",
        "powershell": "PowerShell",
        "wt": "Windows Terminal",
        "explorer": "File Explorer",
        "taskmgr": "Task Manager",
        "winword": "Word",
        "word": "Word",
        "excel": "Excel",
        "powerpnt": "PowerPoint",
        "downloads": "Downloads",
        "documents": "Documents",
        "desktop": "Desktop",
        "pictures": "Pictures",
        "music": "Music",
        "videos": "Videos",
        "cybershield_ai_enterprise_hardened_enhanced": "CyberShield AI",
        "cybershield ai": "CyberShield AI",
        "cyber shield ai": "CyberShield AI",
        "j.a.r.v.i.s": "J.A.R.V.I.S",
        "jarvis": "J.A.R.V.I.S",
    }

    key = str(clean).lower().replace("-", " ").replace("_", " ").strip()
    compact_key = re.sub(r"\s+", " ", key)

    return pretty.get(compact_key, clean)


def _opened_message(target, fallback=None):
    name = fallback or _display_name(target)
    return f"Opening {name}"


def _not_found_message(kind, target):
    return f"{kind} not found: {_display_name(target)}"


def _cache_get(key):
    data = _safe_load_json_file(OPEN_CACHE_FILE, {})
    item = data.get(normalize_name(key))

    if not item:
        return None

    path = item.get("path", "")

    if path and os.path.exists(os.path.expandvars(path)):
        return path

    return None


def _cache_set(key, path):
    if not key or not path:
        return False

    data = _safe_load_json_file(OPEN_CACHE_FILE, {})

    data[normalize_name(key)] = {
        "query": str(key),
        "path": str(path),
        "saved_at": int(time.time()),
    }

    return _safe_save_json_file(OPEN_CACHE_FILE, data)


def _normalize_app_query(app_name):
    app_name = normalize_target_text(app_name).lower() if "normalize_target_text" in globals() else str(app_name).lower().strip()
    app_name = APP_NAME_CORRECTIONS.get(app_name, app_name) if "APP_NAME_CORRECTIONS" in globals() else app_name

    natural = {
        "fire": "firefox",
        "fox": "firefox",
        "mozilla": "firefox",
        "mozilla firefox": "firefox",
        "google": "chrome",
        "browser": "chrome",
        "google browser": "chrome",
        "code": "vscode",
        "vs": "vscode",
        "vs code": "vscode",
        "visual code": "vscode",
        "visual studio code": "vscode",
        "vs community": "visual studio community",
        "vscommunity": "visual studio community",
        "visual studio": "visual studio community",
        "visual community": "visual studio community",
        "idea": "intellij",
        "intellij idea": "intellij",
        "androidstudio": "android studio",
        "terminal": "terminal",
        "windows terminal": "terminal",
        "explorer": "file explorer",
        "files": "file explorer",
        "file manager": "file explorer",
    }

    return natural.get(app_name, app_name)


def _launch_executable_or_uri(candidate, extra_args=None):
    candidate = os.path.expandvars(str(candidate))
    extra_args = extra_args or []

    try:
        if candidate.endswith(":"):
            os.startfile(candidate)
            return True

        if os.path.exists(candidate):
            subprocess.Popen(
                [candidate] + list(extra_args),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            return True

        resolved = shutil.which(candidate)

        if resolved:
            subprocess.Popen(
                [resolved] + list(extra_args),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            return True

        if candidate.startswith("start "):
            subprocess.Popen(candidate, shell=True)
            return True

    except Exception:
        pass

    return False


# ==========================
# NORMALIZE
# ==========================
def normalize_name(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def split_words(name):
    """
    Examples:
    J.A.R.V.I.S -> ["j", "a", "r", "v", "i", "s"]
    CyberShield_AI -> ["cyber", "shield", "ai"]
    AIRecipeFinder -> ["ai", "recipe", "finder"]
    """

    text = str(name)

    text = re.sub(
        r"([a-z])([A-Z])",
        r"\1 \2",
        text
    )

    text = re.sub(
        r"[^A-Za-z0-9]+",
        " ",
        text
    )

    return [
        word.lower()
        for word in text.split()
        if word.strip()
    ]


def compact_initials(words):
    if not words:
        return ""

    if all(len(word) == 1 for word in words):
        return "".join(words)

    return ""


def build_query_aliases(text):
    words = split_words(text)

    aliases = {
        normalize_name(text)
    }

    if words:
        aliases.add(
            normalize_name(" ".join(words))
        )

        aliases.add(
            normalize_name("".join(words))
        )

    initials = compact_initials(words)

    if initials:
        aliases.add(
            normalize_name(initials)
        )

    return {
        alias
        for alias in aliases
        if alias
    }


def get_project_aliases(project):
    aliases = set()

    if not isinstance(project, dict):
        aliases.add(
            normalize_name(str(project))
        )
        return aliases

    name = project.get("name", "")
    path = project.get("path", "")

    aliases.update(
        build_query_aliases(name)
    )

    aliases.add(
        normalize_name(name)
    )

    folder = os.path.basename(path)

    if folder:
        aliases.update(
            build_query_aliases(folder)
        )

    # Aliases generated by project_indexer.py
    for key in [
        "aliases",
        "search_keys"
    ]:
        for alias in project.get(key, []):
            aliases.add(
                normalize_name(alias)
            )

    # Useful individual words from project name/folder
    for word in split_words(name):
        if len(word) >= 3:
            aliases.add(
                normalize_name(word)
            )

    for word in split_words(folder):
        if len(word) >= 3:
            aliases.add(
                normalize_name(word)
            )

    return {
        alias
        for alias in aliases
        if alias
    }


def project_match_score(project, query):
    query_aliases = build_query_aliases(query)
    project_aliases = get_project_aliases(project)

    if not query_aliases or not project_aliases:
        return 0

    best_score = 0

    for q in query_aliases:
        for alias in project_aliases:

            if q == alias:
                best_score = max(
                    best_score,
                    1.0
                )

            elif q in alias or alias in q:
                # Strong partial match
                if len(q) >= 3 and len(alias) >= 3:
                    best_score = max(
                        best_score,
                        0.90
                    )

            score = difflib.SequenceMatcher(
                None,
                q,
                alias
            ).ratio()

            best_score = max(
                best_score,
                score
            )

    return best_score


# ==========================
# WEBSITE
# ==========================
def open_website(url):
    if not url.startswith("http"):
        url = "https://" + url

    webbrowser.open(url)
    return f"Opened website: {url}"


# ==========================
# FOLDER
# ==========================
def open_folder(path):
    if os.path.exists(path):
        os.startfile(path)
        return f"Opened folder: {path}"

    return "Folder not found."


# ==========================
# FILE
# ==========================
def open_file(path):
    if os.path.exists(path):
        os.startfile(path)
        return f"Opened file: {path}"

    return "File not found."


# ==========================
# FILE SEARCH
# ==========================
def search_files(keyword, max_results=10):
    results = []
    keyword = keyword.lower()

    for root, dirs, files in os.walk(ROOT_SEARCH):
        try:
            for file in files:
                if keyword in file.lower():
                    results.append(os.path.join(root, file))

                    if len(results) >= max_results:
                        return results
        except:
            pass

    return results


# ==========================
# APPLICATION INDEX
# ==========================
def load_apps():
    try:
        with open(APP_INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


# ==========================
# WINDOWS APP ALIASES
# ==========================
APP_ALIASES = {
    "vscode": [
        "visual studio code",
        "code",
        "vs code",
        "vscode"
    ],
    "visualstudiocode": [
        "visual studio code",
        "code",
        "vs code",
        "vscode"
    ],
    "vscodeeditor": [
        "visual studio code",
        "code"
    ],
    "firefox": [
        "firefox",
        "mozilla firefox"
    ],
    "chrome": [
        "chrome",
        "google chrome"
    ],
    "edge": [
        "edge",
        "microsoft edge"
    ],
    "calculator": [
        "calculator",
        "calc"
    ],
    "calc": [
        "calculator",
        "calc"
    ],
    "camera": [
        "camera"
    ],
    "notepad": [
        "notepad"
    ],
    "paint": [
        "paint",
        "mspaint"
    ],
    "cmd": [
        "command prompt",
        "cmd"
    ],
    "powershell": [
        "powershell",
        "windows powershell"
    ],
    "terminal": [
        "windows terminal",
        "terminal"
    ],
    "word": [
        "word",
        "microsoft word"
    ],
    "excel": [
        "excel",
        "microsoft excel"
    ],
    "powerpoint": [
        "powerpoint",
        "microsoft powerpoint"
    ],
    "visualstudio": [
        "visual studio",
        "microsoft visual studio"
    ],
    "vscommunity": [
        "visual studio",
        "visual studio community",
        "microsoft visual studio"
    ],
    "intellij": [
        "intellij",
        "intellij idea",
        "idea"
    ],
    "pycharm": [
        "pycharm",
        "jetbrains pycharm"
    ],
    "androidstudio": [
        "android studio",
        "androidstudio"
    ],
    "eclipse": [
        "eclipse",
        "eclipse ide"
    ]
}


WINDOWS_COMMANDS = {
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "camera": "start microsoft.windows.camera:",
    "notepad": "notepad.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "wt.exe"
}


BLOCKED_BAD_MATCHES = {
    "narrator",
    "character map",
    "windows media player legacy",
    "steps recorder",
    "magnifier",
    "on-screen keyboard"
}


def launch_path(path):
    try:
        if path.startswith("start "):
            subprocess.Popen(
                path,
                shell=True
            )
        else:
            os.startfile(path)

        return True

    except Exception:
        return False


def launch_command(command):
    try:
        subprocess.Popen(
            command,
            shell=True
        )
        return True

    except Exception:
        return False


def get_aliases(app_name):
    query = normalize_name(app_name)

    aliases = [app_name]

    if query in APP_ALIASES:
        aliases.extend(APP_ALIASES[query])

    return aliases


def is_bad_match(name):
    normalized = name.lower()

    for bad in BLOCKED_BAD_MATCHES:
        if bad in normalized:
            return True

    return False


def open_installed_app(app_name):
    apps = load_apps()

    query = normalize_name(app_name)
    aliases = get_aliases(app_name)
    normalized_aliases = [
        normalize_name(alias)
        for alias in aliases
    ]

    # 1. Windows direct command fallback
    for alias in normalized_aliases:
        if alias in WINDOWS_COMMANDS:
            command = WINDOWS_COMMANDS[alias]

            if launch_command(command):
                return f"Opening {app_name}"

    if not apps:
        return "Application index not found. Run app_indexer.py first."

    # 2. Exact match
    for name, path in apps.items():
        normalized = normalize_name(name)

        if normalized in normalized_aliases:
            if launch_path(path):
                return f"Opening {name}"

    # 3. Safe partial match
    for name, path in apps.items():
        normalized = normalize_name(name)

        if is_bad_match(name):
            continue

        for alias in normalized_aliases:
            if alias in normalized or normalized in alias:
                if len(alias) < 4:
                    continue

                if launch_path(path):
                    return f"Opening {name}"

    # 4. Safer fuzzy match
    best_match = None
    best_score = 0

    for name, path in apps.items():
        if is_bad_match(name):
            continue

        normalized = normalize_name(name)

        for alias in normalized_aliases:
            score = difflib.SequenceMatcher(
                None,
                alias,
                normalized
            ).ratio()

            if score > best_score:
                best_score = score
                best_match = (name, path)

    if best_match and best_score >= 0.75:
        name, path = best_match

        if launch_path(path):
            return f"Opening closest match: {name}"

    return f"Could not find application: {app_name}"


def list_apps(limit=50):
    apps = load_apps()
    names = sorted(list(apps.keys()))
    return names[:limit]


def refresh_app_index():
    try:
        subprocess.run([sys.executable, "app_indexer.py"], check=True)
        return "Application index rebuilt."
    except Exception as e:
        return f"Could not rebuild application index: {e}"


# ==========================
# PROJECT INDEX
# ==========================
def load_projects():
    try:
        with open(PROJECT_INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def find_project(project_name):
    projects = load_projects()

    if not projects:
        return None

    query = normalize_name(project_name)

    # 1. Direct key match
    if query in projects:
        return projects[query]

    # 2. Smart alias scoring
    ranked = []

    for key, project in projects.items():
        if not isinstance(project, dict):
            continue

        score = project_match_score(
            project,
            project_name
        )

        # Prefer paths that still exist
        path = project.get("path", "")

        if path and os.path.exists(path):
            score += 0.05

        ranked.append(
            (score, project)
        )

    ranked.sort(
        key=lambda item: item[0],
        reverse=True
    )

    if ranked and ranked[0][0] >= 0.62:
        return ranked[0][1]

    return None


def open_project(project_name):
    projects = load_projects()

    if not projects:
        return "Project index not found. Run project_indexer.py first."

    project = find_project(project_name)

    if project:
        os.startfile(project["path"])
        return f"Opening project: {project['name']}"

    return f"Project not found: {project_name}"


def list_projects():
    projects = load_projects()

    names = []

    for project in projects.values():
        if isinstance(project, dict):
            names.append(project.get("name", "Unknown"))
        else:
            names.append(str(project))

    return sorted(names)


def get_project_drive(path):
    if not path:
        return "Unknown"

    drive, _ = os.path.splitdrive(path)

    if drive:
        return drive.upper()

    return "Unknown"


def list_projects_detailed():
    projects = load_projects()

    if not projects:
        return "No projects found. Run refresh projects first."

    rows = []

    for project in projects.values():
        if not isinstance(project, dict):
            continue

        name = project.get("name", "Unknown")
        path = project.get("path", "Unknown")
        drive = get_project_drive(path)

        rows.append(
            (drive, name, path, project.get("type", "Unknown"))
        )

    if not rows:
        return "No valid projects found."

    rows.sort(
        key=lambda item: (
            item[0],
            item[1].lower()
        )
    )

    output = [
        f"Indexed projects: {len(rows)}"
    ]

    current_drive = None

    for drive, name, path, project_type in rows:
        if drive != current_drive:
            current_drive = drive
            output.append(f"\n{drive}:")

        output.append(
            f" - {name} [{project_type}] -> {path}"
        )

    return "\n".join(output)


def list_projects_by_drive(drive_letter):
    projects = load_projects()

    if not projects:
        return "No projects found. Run refresh projects first."

    drive_letter = drive_letter.strip().upper()

    if not drive_letter.endswith(":"):
        drive_letter += ":"

    rows = []

    for project in projects.values():
        if not isinstance(project, dict):
            continue

        name = project.get("name", "Unknown")
        path = project.get("path", "")

        if get_project_drive(path) == drive_letter:
            rows.append(
                (name, path)
            )

    if not rows:
        return f"No projects found on {drive_letter}"

    rows.sort(
        key=lambda item: item[0].lower()
    )

    output = [
        f"Projects on {drive_letter}: {len(rows)}"
    ]

    for item in rows:
        if len(item) == 2:
            name, path = item
            project_type = "Unknown"
        else:
            name, path, project_type = item

        output.append(
            f" - {name} [{project_type}] -> {path}"
        )

    return "\n".join(output)


def search_projects(keyword):
    projects = load_projects()

    if not projects:
        return "No projects found. Run refresh projects first."

    keyword = keyword.strip()

    if not keyword:
        return "Missing project search keyword."

    rows = []

    for project in projects.values():
        if not isinstance(project, dict):
            continue

        score = project_match_score(
            project,
            keyword
        )

        name = project.get("name", "Unknown")
        path = project.get("path", "")
        project_type = project.get("type", "Unknown")
        drive = get_project_drive(path)

        if score >= 0.45:
            rows.append(
                (
                    score,
                    drive,
                    name,
                    path,
                    project_type
                )
            )

    if not rows:
        return f"No projects matched: {keyword}"

    rows.sort(
        key=lambda item: (
            -item[0],
            item[2].lower()
        )
    )

    output = [
        f"Project matches for '{keyword}': {len(rows)}"
    ]

    for score, drive, name, path, project_type in rows[:50]:
        output.append(
            f" - {name} [{project_type}] -> {path}"
        )

    if len(rows) > 50:
        output.append(
            f"... and {len(rows) - 50} more"
        )

    return "\n".join(output)


def refresh_project_index():
    try:
        subprocess.run([sys.executable, "project_indexer.py"], check=True)
        return "Project index rebuilt."
    except Exception as e:
        return f"Could not rebuild project index: {e}"


# ==========================
# ANALYZE PROJECT
# ==========================
def analyze_project_by_name(project_name):
    projects = load_projects()

    if not projects:
        return "Project index not found. Run project_indexer.py first."

    project = find_project(project_name)

    if not project:
        return f"Project not found: {project_name}"

    return analyze_project(
        project["name"],
        project["path"]
    )


# ==========================
# VS CODE INTEGRATION
# ==========================
def find_vscode():
    possible_paths = [
        r"C:\Users\Student\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"
        ),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None


def open_project_in_vscode(project_name):
    project = find_project(project_name)

    if not project:
        return f"Project not found: {project_name}"

    vscode_path = find_vscode()

    try:
        if vscode_path:
            subprocess.Popen(
                [vscode_path, project["path"]],
                shell=False
            )
        else:
            subprocess.Popen(
                ["code", project["path"]],
                shell=True
            )

        return f"Opening project in VS Code: {project['name']}"

    except Exception as e:
        return f"Could not open VS Code: {e}"

# ==========================================================
# UNIVERSAL TOOLS UPGRADE
# Strict, safer universal opener/resolver.
# Works across C:, D:, E:, USB sticks and external drives.
# This section intentionally overrides some older functions above.
# ==========================================================

SKIP_SEARCH_DIRS = {
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

COMMON_WEBSITES = {
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
    "twitter": "x.com",
    "x": "x.com",
    "tiktok": "tiktok.com",
    "netflix": "netflix.com",
    "discord": "discord.com",
    "teams": "teams.microsoft.com",
}

KNOWN_APP_COMMANDS = {
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "notepad": ["notepad.exe"],
    "paint": ["mspaint.exe"],
    "mspaint": ["mspaint.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "terminal": ["wt.exe", "powershell.exe"],
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
    "vs code": [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        "code",
        "code.cmd",
    ],
    "visual studio community": [
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Professional\Common7\IDE\devenv.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\devenv.exe",
        "devenv.exe",
    ],
    "visual studio": [
        r"C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Professional\Common7\IDE\devenv.exe",
        r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\Common7\IDE\devenv.exe",
        "devenv.exe",
    ],
    "intellij": [
        os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\Toolbox\scripts\idea.cmd"),
        r"C:\Program Files\JetBrains\IntelliJ IDEA Community Edition 2024.3\bin\idea64.exe",
        r"C:\Program Files\JetBrains\IntelliJ IDEA 2024.3\bin\idea64.exe",
        "idea64.exe",
        "idea",
    ],
    "intellij idea": [
        os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\Toolbox\scripts\idea.cmd"),
        r"C:\Program Files\JetBrains\IntelliJ IDEA Community Edition 2024.3\bin\idea64.exe",
        r"C:\Program Files\JetBrains\IntelliJ IDEA 2024.3\bin\idea64.exe",
        "idea64.exe",
        "idea",
    ],
    "pycharm": [
        os.path.expandvars(r"%LOCALAPPDATA%\JetBrains\Toolbox\scripts\pycharm.cmd"),
        r"C:\Program Files\JetBrains\PyCharm Community Edition 2024.3\bin\pycharm64.exe",
        r"C:\Program Files\JetBrains\PyCharm 2024.3\bin\pycharm64.exe",
        "pycharm64.exe",
        "pycharm",
    ],
    "android studio": [
        r"C:\Program Files\Android\Android Studio\bin\studio64.exe",
        "studio64.exe",
    ],
    "eclipse": [
        "eclipse.exe",
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

    "teams": [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Teams\current\Teams.exe"),
        "teams.exe",
    ],
    "discord": [
        os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe"),
        "discord.exe",
    ],
    "obs": ["obs64.exe", "obs32.exe"],
    "obs studio": ["obs64.exe", "obs32.exe"],
    "postman": [
        os.path.expandvars(r"%LOCALAPPDATA%\Postman\Postman.exe"),
        "postman.exe",
    ],
    "docker": ["Docker Desktop.exe"],
    "docker desktop": ["Docker Desktop.exe"],
}

APP_NAME_CORRECTIONS = {
    "computer": "calculator",
    "calculate": "calculator",
    "calculation": "calculator",
    "fire": "firefox",
    "browser": "chrome",
    "code": "vscode",
    "vs code": "vscode",
    "visual studio": "visual studio community",
    "vs community": "visual studio community",
    "vscommunity": "visual studio community",
    "idea": "intellij",
    "intellij idea": "intellij",
    "androidstudio": "android studio",
}

KNOWN_FOLDERS = {
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


def get_available_drives():
    drives = []

    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"

        if os.path.exists(drive):
            drives.append(drive)

    return drives


def safe_startfile(target):
    try:
        os.startfile(target)
        return True
    except Exception:
        pass

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", str(target)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        return True
    except Exception:
        return False


def normalize_target_text(text):
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" dot ", ".")
    text = text.replace(" point ", ".")
    text = text.replace(" slash ", "/")
    return text.strip()


def looks_like_website(target):
    target = normalize_target_text(target).lower()

    if target.startswith("http://") or target.startswith("https://"):
        return True

    if "." in target and " " not in target:
        return True

    return target in COMMON_WEBSITES


def open_website(url):
    url = normalize_target_text(url).lower()
    url = COMMON_WEBSITES.get(url, url)
    url = url.replace(" ", "")

    if not url:
        return "Website target is empty."

    if "." not in url:
        url += ".com"

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    webbrowser.open(url)
    return _opened_message(url)


def open_folder(path):
    original = path
    path = os.path.expandvars(str(path))

    if os.path.exists(path) and os.path.isdir(path):
        safe_startfile(path)
        return _opened_message(path)

    found = universal_find(path, want_folder=True)

    if found:
        safe_startfile(found)
        _cache_set(original, found)
        return _opened_message(found)

    return _not_found_message("Folder", original)


def open_file(path):
    original = path
    path = os.path.expandvars(str(path))

    if os.path.exists(path) and os.path.isfile(path):
        safe_startfile(path)
        return _opened_message(path)

    cached = _cache_get(original)

    if cached and os.path.isfile(cached):
        safe_startfile(cached)
        return _opened_message(cached)

    found = universal_find(path, want_file=True)

    if found:
        safe_startfile(found)
        _cache_set(original, found)
        return _opened_message(found)

    return _not_found_message("File", original)


def get_user_folder(name):
    key = normalize_target_text(name).lower()
    folder = KNOWN_FOLDERS.get(key)

    if not folder:
        return None

    path = os.path.join(str(Path.home()), folder)

    if os.path.exists(path):
        return path

    return None


def universal_score(query, candidate):
    query = normalize_target_text(query).lower()
    candidate = normalize_target_text(candidate).lower()

    if not query or not candidate:
        return 0

    if query == candidate:
        return 100

    if query in candidate:
        return 85

    query_words = set(
        query.replace("_", " ").replace("-", " ").split()
    )
    candidate_words = set(
        candidate.replace("_", " ").replace("-", " ").split()
    )

    if query_words:
        common = len(query_words & candidate_words)
        word_score = int((common / len(query_words)) * 75)
    else:
        word_score = 0

    fuzzy_score = int(
        difflib.SequenceMatcher(None, query, candidate).ratio() * 70
    )

    return max(word_score, fuzzy_score)


def universal_find(keyword, want_file=False, want_folder=False, max_seconds=40):
    keyword = normalize_target_text(keyword)

    if not keyword:
        return None

    user_known = get_user_folder(keyword)

    if user_known and not want_file:
        return user_known

    expanded = os.path.expandvars(keyword)

    if os.path.exists(expanded):
        if want_file and os.path.isfile(expanded):
            return os.path.abspath(expanded)
        if want_folder and os.path.isdir(expanded):
            return os.path.abspath(expanded)
        if not want_file and not want_folder:
            return os.path.abspath(expanded)

    roots = [
        os.getcwd(),
        str(Path.home()),
    ]
    roots.extend(get_available_drives())

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

                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in SKIP_SEARCH_DIRS
                ]

                if not want_file:
                    folder_score = universal_score(
                        keyword,
                        os.path.basename(root)
                    )

                    if folder_score > best_score:
                        best_score = folder_score
                        best_path = root

                if not want_folder:
                    for file_name in files:
                        file_score = universal_score(keyword, file_name)

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


def search_files(keyword, max_results=10):
    results = []
    keyword = normalize_target_text(keyword)

    if not keyword:
        return results

    roots = [
        os.getcwd(),
        str(Path.home()),
    ]
    roots.extend(get_available_drives())

    start = time.time()

    for root_dir in roots:
        if time.time() - start > 40:
            break

        if not os.path.exists(root_dir):
            continue

        try:
            for root, dirs, files in os.walk(root_dir):
                if time.time() - start > 40:
                    break

                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in SKIP_SEARCH_DIRS
                ]

                for file_name in files:
                    if keyword.lower() in file_name.lower():
                        results.append(os.path.join(root, file_name))

                        if len(results) >= max_results:
                            return results
        except Exception:
            continue

    return results


def open_installed_app(app_name):
    original_name = str(app_name).strip()
    app_name = _normalize_app_query(app_name)

    cached = _cache_get(app_name)

    if cached and _launch_executable_or_uri(cached):
        return _opened_message(cached, _display_name(app_name))

    # 1. Direct Windows/common commands.
    candidates = KNOWN_APP_COMMANDS.get(app_name, [])

    for candidate in candidates:
        candidate = os.path.expandvars(candidate)

        if _launch_executable_or_uri(candidate):
            _cache_set(app_name, candidate)
            return _opened_message(app_name)

    # 2. Existing index from app_indexer.py.
    apps = load_apps()
    query = normalize_name(app_name)
    aliases = get_aliases(app_name)
    normalized_aliases = [
        normalize_name(alias)
        for alias in aliases
    ]
    normalized_aliases.append(query)

    # Exact app index match.
    for name, path in apps.items():
        normalized = normalize_name(name)

        if normalized in normalized_aliases:
            if launch_path(path):
                _cache_set(app_name, path)
                return _opened_message(name)

    # Safe partial match.
    for name, path in apps.items():
        normalized = normalize_name(name)

        if is_bad_match(name):
            continue

        for alias in normalized_aliases:
            if alias and len(alias) >= 4 and (alias in normalized or normalized in alias):
                if launch_path(path):
                    _cache_set(app_name, path)
                    return _opened_message(name)

    # Safer fuzzy match.
    best_match = None
    best_score = 0

    for name, path in apps.items():
        if is_bad_match(name):
            continue

        normalized = normalize_name(name)

        for alias in normalized_aliases or [query]:
            score = difflib.SequenceMatcher(None, alias, normalized).ratio()

            if score > best_score:
                best_score = score
                best_match = (name, path)

    if best_match and best_score >= 0.75:
        name, path = best_match

        if launch_path(path):
            _cache_set(app_name, path)
            return _opened_message(name)

    # 3. Windows shell final fallback.
    if safe_startfile(app_name):
        return _opened_message(app_name)

    return f"Could not find application: {_display_name(original_name)}"


def find_project(project_name):
    projects = load_projects()

    if not projects:
        return None

    query = normalize_name(project_name)

    if query in projects:
        project = projects[query]

        if isinstance(project, dict):
            path = project.get("path", "")

            if path and os.path.exists(path):
                return project

    ranked = []

    for key, project in projects.items():
        if not isinstance(project, dict):
            continue

        score = project_match_score(
            project,
            project_name
        )

        path = project.get("path", "")

        if path and os.path.exists(path):
            score += 0.20
        elif path:
            # Stale path from another PC/stick should not win too easily.
            score -= 0.15

        ranked.append((score, project))

    ranked.sort(
        key=lambda item: item[0],
        reverse=True
    )

    if ranked and ranked[0][0] >= 0.62:
        candidate = ranked[0][1]
        path = candidate.get("path", "")

        if path and os.path.exists(path):
            return candidate

    # Fallback: search all drives by name/folder aliases.
    found_path = universal_find(project_name, want_folder=True)

    if found_path:
        return {
            "name": os.path.basename(found_path),
            "path": found_path,
            "type": "Detected"
        }

    return None


def open_project(project_name):
    project = find_project(project_name)

    if project:
        path = project.get("path", "")
        name = project.get("name", project_name)

        if path and os.path.exists(path):
            safe_startfile(path)
            _cache_set(project_name, path)
            return _opened_message(name)

        cached = _cache_get(project_name)

        if cached and os.path.isdir(cached):
            safe_startfile(cached)
            return _opened_message(name)

        found = universal_find(project_name, want_folder=True)

        if found:
            safe_startfile(found)
            _cache_set(project_name, found)
            return _opened_message(name)

    return f"Project not found: {_display_name(project_name)}"


def list_projects_by_drive(drive_letter):
    projects = load_projects()

    if not projects:
        return "No projects found. Run refresh projects first."

    drive_letter = drive_letter.strip().upper()

    if not drive_letter.endswith(":"):
        drive_letter += ":"

    rows = []

    for project in projects.values():
        if not isinstance(project, dict):
            continue

        name = project.get("name", "Unknown")
        path = project.get("path", "")
        project_type = project.get("type", "Unknown")

        if get_project_drive(path) == drive_letter:
            rows.append((name, path, project_type))

    if not rows:
        return f"No projects found on {drive_letter}"

    rows.sort(key=lambda item: item[0].lower())

    output = [
        f"Projects on {drive_letter}: {len(rows)}"
    ]

    for name, path, project_type in rows:
        output.append(
            f" - {name} [{project_type}] -> {path}"
        )

    return "\n".join(output)


def open_anything(target):
    target = normalize_target_text(target)

    if not target:
        return "Missing target."

    lower = target.lower()

    # 1. Website.
    if looks_like_website(lower):
        return open_website(lower)

    # 2. Known user folder.
    folder = get_user_folder(lower)

    if folder:
        safe_startfile(folder)
        _cache_set(target, folder)
        return _opened_message(folder)

    # 3. Project, when command target looks like a project or matches index.
    project = find_project(target)

    if project:
        path = project.get("path", "")

        if path and os.path.exists(path):
            safe_startfile(path)
            _cache_set(target, path)
            return _opened_message(project.get("name", target))

    # 4. Application.
    if lower in KNOWN_APP_COMMANDS or lower in APP_NAME_CORRECTIONS or _normalize_app_query(lower) in KNOWN_APP_COMMANDS:
        return open_installed_app(lower)

    # 5. Cache.
    cached = _cache_get(target)

    if cached:
        safe_startfile(cached)
        return _opened_message(cached)

    # 6. File/folder search.
    found = universal_find(target)

    if found:
        safe_startfile(found)
        _cache_set(target, found)
        return _opened_message(found)

    # 7. Last fallback: try as application.
    return open_installed_app(target)


# ==========================
# SMART AUTO INDEXER
# ==========================
def _smart_index_now():
    return int(time.time())


def _smart_index_file_info(path):
    try:
        p = Path(path)

        if not p.exists():
            return {
                "exists": False,
                "mtime": 0,
                "size": 0
            }

        stat = p.stat()

        return {
            "exists": True,
            "mtime": int(stat.st_mtime),
            "size": int(stat.st_size)
        }

    except Exception:
        return {
            "exists": False,
            "mtime": 0,
            "size": 0
        }


def _load_index_metadata():
    try:
        with open(INDEX_METADATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception:
        pass

    return {}


def _save_index_metadata(data):
    try:
        with open(INDEX_METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return True

    except Exception:
        return False


def _safe_count_json_entries(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return len(data)

        if isinstance(data, list):
            return len(data)

    except Exception:
        pass

    return 0


def _quick_root_signature():
    """
    Builds a lightweight signature of the environment.

    It avoids walking the whole disk at startup.
    It only checks available drives and a few known user folders.
    """
    roots = []

    try:
        roots.extend(get_available_drives())
    except Exception:
        pass

    try:
        home = str(Path.home())
        roots.append(home)

        for folder in [
            "Desktop",
            "Documents",
            "Downloads",
            "Projects",
            "source",
            "repos",
        ]:
            candidate = os.path.join(home, folder)

            if os.path.exists(candidate):
                roots.append(candidate)

    except Exception:
        pass

    signature = {}

    for root in sorted(set(roots)):
        try:
            p = Path(root)

            if not p.exists():
                continue

            stat = p.stat()

            children_count = 0
            newest_child_mtime = 0

            try:
                for index, child in enumerate(p.iterdir()):
                    if index >= 200:
                        break

                    try:
                        child_stat = child.stat()
                        newest_child_mtime = max(
                            newest_child_mtime,
                            int(child_stat.st_mtime)
                        )
                        children_count += 1
                    except Exception:
                        continue
            except Exception:
                pass

            signature[str(p)] = {
                "mtime": int(stat.st_mtime),
                "children": children_count,
                "newest_child_mtime": newest_child_mtime,
            }

        except Exception:
            continue

    return signature


def _index_is_missing_or_empty(index_file):
    info = _smart_index_file_info(index_file)

    if not info["exists"]:
        return True

    if info["size"] <= 5:
        return True

    if _safe_count_json_entries(index_file) <= 0:
        return True

    return False


def _smart_index_needs_refresh(kind, index_file, metadata, max_age_seconds=None):
    max_age_seconds = max_age_seconds or SMART_INDEX_MAX_AGE_SECONDS

    info = _smart_index_file_info(index_file)

    if _index_is_missing_or_empty(index_file):
        return True, f"{kind} index missing or empty"

    kind_meta = metadata.get(kind, {})

    last_refresh = int(kind_meta.get("last_refresh", 0) or 0)
    age = _smart_index_now() - last_refresh

    if last_refresh <= 0:
        return True, f"{kind} metadata missing"

    if age > max_age_seconds:
        return True, f"{kind} index is older than {round(age / 3600, 1)} hours"

    previous_info = kind_meta.get("index_file", {})

    if previous_info.get("mtime") != info.get("mtime") or previous_info.get("size") != info.get("size"):
        # The file changed externally. No need to force rebuild, but metadata must be updated.
        return False, f"{kind} index changed externally"

    if kind == "projects":
        previous_signature = kind_meta.get("root_signature", {})
        current_signature = _quick_root_signature()

        if previous_signature and previous_signature != current_signature:
            return True, "project roots changed"

    return False, f"{kind} index is fresh"


def _update_index_metadata_for(kind, index_file, metadata, note=None):
    metadata[kind] = {
        "last_refresh": _smart_index_now(),
        "index_file": _smart_index_file_info(index_file),
        "entries": _safe_count_json_entries(index_file),
        "note": note or "ok",
    }

    if kind == "projects":
        metadata[kind]["root_signature"] = _quick_root_signature()

    return metadata


def smart_refresh_app_index(force=False):
    metadata = _load_index_metadata()

    if not force:
        needs_refresh, reason = _smart_index_needs_refresh(
            "apps",
            APP_INDEX_FILE,
            metadata
        )

        if not needs_refresh:
            metadata = _update_index_metadata_for(
                "apps",
                APP_INDEX_FILE,
                metadata,
                reason
            )
            _save_index_metadata(metadata)

            entries = metadata.get("apps", {}).get("entries", 0)
            return f"Application index is fresh. Entries: {entries}. Reason: {reason}"

    result = refresh_app_index()

    metadata = _update_index_metadata_for(
        "apps",
        APP_INDEX_FILE,
        metadata,
        result
    )
    _save_index_metadata(metadata)

    entries = metadata.get("apps", {}).get("entries", 0)

    return f"{result} Entries: {entries}"


def smart_refresh_project_index(force=False):
    metadata = _load_index_metadata()

    if not force:
        needs_refresh, reason = _smart_index_needs_refresh(
            "projects",
            PROJECT_INDEX_FILE,
            metadata
        )

        if not needs_refresh:
            metadata = _update_index_metadata_for(
                "projects",
                PROJECT_INDEX_FILE,
                metadata,
                reason
            )
            _save_index_metadata(metadata)

            entries = metadata.get("projects", {}).get("entries", 0)
            return f"Project index is fresh. Entries: {entries}. Reason: {reason}"

    result = refresh_project_index()

    metadata = _update_index_metadata_for(
        "projects",
        PROJECT_INDEX_FILE,
        metadata,
        result
    )
    _save_index_metadata(metadata)

    entries = metadata.get("projects", {}).get("entries", 0)

    return f"{result} Entries: {entries}"


def smart_refresh_all_indexes(force=False):
    app_result = smart_refresh_app_index(force=force)
    project_result = smart_refresh_project_index(force=force)

    return (
        "Smart refresh completed.\n"
        f"Applications: {app_result}\n"
        f"Projects: {project_result}"
    )


def ensure_indexes_ready(force=False):
    """
    Smart startup index manager.

    Use this from jarvis_agent.py at startup.
    It only rebuilds indexes when:
    - index files are missing;
    - index files are empty;
    - metadata is missing;
    - index is older than SMART_INDEX_MAX_AGE_SECONDS;
    - project roots changed.
    """
    return smart_refresh_all_indexes(force=force)


def index_status():
    metadata = _load_index_metadata()

    app_info = _smart_index_file_info(APP_INDEX_FILE)
    project_info = _smart_index_file_info(PROJECT_INDEX_FILE)

    lines = [
        "JARVIS INDEX STATUS",
        "",
        f"Apps index file: {APP_INDEX_FILE}",
        f"Apps exists: {app_info['exists']}",
        f"Apps entries: {_safe_count_json_entries(APP_INDEX_FILE)}",
        f"Apps last refresh: {metadata.get('apps', {}).get('last_refresh', 'N/A')}",
        "",
        f"Projects index file: {PROJECT_INDEX_FILE}",
        f"Projects exists: {project_info['exists']}",
        f"Projects entries: {_safe_count_json_entries(PROJECT_INDEX_FILE)}",
        f"Projects last refresh: {metadata.get('projects', {}).get('last_refresh', 'N/A')}",
        "",
        f"Metadata file: {INDEX_METADATA_FILE}",
    ]

    return "\n".join(lines)


# Override old full refresh with the smart version.
def refresh_all_indexes():
    return smart_refresh_all_indexes(force=False)


def force_refresh_all_indexes():
    return smart_refresh_all_indexes(force=True)

# ==========================================================
# JARVIS DEVELOPER TOOL EXTENSIONS
# IDE/project helpers used by jarvis_agent.py and project_file_assistant.py.
# ==========================================================
IDE_COMMAND_ALIASES = {
    "vscode": "visual studio code",
    "vs code": "visual studio code",
    "visual studio code": "visual studio code",
    "code": "visual studio code",
    "visual studio": "visual studio community",
    "visual studio community": "visual studio community",
    "vs community": "visual studio community",
    "vscommunity": "visual studio community",
    "intellij": "intellij",
    "intellij idea": "intellij",
    "idea": "intellij",
    "pycharm": "pycharm",
    "android studio": "android studio",
    "androidstudio": "android studio",
    "eclipse": "eclipse",
}


def resolve_app_command(app_name):
    """
    Resolve an app/IDE to an executable path or command.
    Returns None if it cannot be found.
    """
    if not app_name:
        return None

    app_key = normalize_target_text(app_name).lower()
    app_key = APP_NAME_CORRECTIONS.get(app_key, app_key)
    app_key = IDE_COMMAND_ALIASES.get(app_key, app_key)

    candidates = KNOWN_APP_COMMANDS.get(app_key, [])

    for candidate in candidates:
        candidate = os.path.expandvars(candidate)

        if os.path.exists(candidate):
            return candidate

        found = shutil.which(candidate)

        if found:
            return found

        if candidate.endswith(":"):
            return candidate

    apps = load_apps()
    aliases = get_aliases(app_key)
    normalized_aliases = [normalize_name(alias) for alias in aliases]
    normalized_aliases.append(normalize_name(app_key))

    for name, path in apps.items():
        normalized = normalize_name(name)

        if normalized in normalized_aliases:
            return path

    best_match = None
    best_score = 0

    for name, path in apps.items():
        if is_bad_match(name):
            continue

        normalized = normalize_name(name)

        for alias in normalized_aliases:
            score = difflib.SequenceMatcher(None, alias, normalized).ratio()

            if score > best_score:
                best_score = score
                best_match = path

    if best_match and best_score >= 0.75:
        return best_match

    return None


def open_project_in_app(project_name, app_name):
    """
    Open an indexed project in a requested IDE/application.
    Examples:
    - open_project_in_app("CyberShield AI", "VS Code")
    - open_project_in_app("ManagerApp", "IntelliJ")
    """
    project = find_project(project_name)

    if not project:
        return f"Project not found: {project_name}"

    project_path = project.get("path", "")

    if not project_path or not os.path.exists(project_path):
        return f"Project path not found: {project_path}"

    app_command = resolve_app_command(app_name)

    if not app_command:
        return f"Application/IDE not found: {app_name}"

    try:
        if str(app_command).endswith(":"):
            safe_startfile(app_command)
            return _opened_message(app_name)

        subprocess.Popen(
            [app_command, project_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

        return f"Opening {project.get('name', project_name)} in {_display_name(app_name)}"

    except Exception as e:
        return f"Could not open project in {app_name}: {e}"


def open_file_in_app(file_path, app_name):
    """
    Open a file path in a requested app/IDE.
    """
    if not file_path or not os.path.exists(file_path):
        return f"File not found: {file_path}"

    app_command = resolve_app_command(app_name)

    if not app_command:
        return f"Application/IDE not found: {app_name}"

    try:
        subprocess.Popen(
            [app_command, file_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

        return f"Opening {_display_name(file_path)} in {_display_name(app_name)}"

    except Exception as e:
        return f"Could not open file in {app_name}: {e}"


def get_project_path(project_name):
    project = find_project(project_name)

    if not project:
        return None

    path = project.get("path", "")

    if path and os.path.exists(path):
        return path

    return None


def project_exists(project_name):
    return get_project_path(project_name) is not None

# ==========================================================
# JARVIS INDEPENDENT DEVELOPER HELPERS
# No dependency on jarvis_agent.py.
# These helpers are safe utility functions used by jarvis_agent.py.
# ==========================================================
JARVIS_CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".scss",
    ".json", ".md", ".txt", ".yml", ".yaml", ".env", ".ini", ".cfg",
    ".toml", ".xml", ".java", ".c", ".cpp", ".h", ".hpp", ".cs",
    ".php", ".rb", ".go", ".rs", ".sql", ".bat", ".ps1", ".sh",
}


def is_code_like_file(path):
    try:
        name = os.path.basename(str(path)).lower()
        ext = os.path.splitext(str(path))[1].lower()

        if name in {"dockerfile", ".gitignore", ".env", "makefile", "readme"}:
            return True

        return ext in JARVIS_CODE_EXTENSIONS

    except Exception:
        return False


def iter_project_code_files(project_name, max_files=5000):
    project_path = get_project_path(project_name)

    if not project_path:
        return []

    results = []

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [
            d for d in dirs
            if d.lower() not in SKIP_SEARCH_DIRS
        ]

        for filename in files:
            full_path = os.path.join(root, filename)

            if not is_code_like_file(full_path):
                continue

            results.append({
                "name": filename,
                "path": full_path,
                "relative_path": os.path.relpath(full_path, project_path),
            })

            if len(results) >= max_files:
                return results

    return results


def find_code_file_in_project(project_name, file_query):
    files = iter_project_code_files(project_name)

    if not files:
        return None

    query = normalize_target_text(file_query).replace("\\", "/").lower()
    query_base = os.path.basename(query)

    candidates = []

    for item in files:
        rel = item["relative_path"].replace("\\", "/").lower()
        name = item["name"].lower()

        score = 0

        if rel == query:
            score = 100
        elif name == query_base:
            score = 95
        elif query in rel:
            score = 85
        elif query_base and query_base in name:
            score = 75
        else:
            score = universal_score(query, rel)

        if score >= 55:
            candidates.append((score, item))

    if not candidates:
        return None

    candidates.sort(
        key=lambda row: (
            -row[0],
            row[1]["relative_path"].lower()
        )
    )

    return candidates[0][1]


def read_code_file_lines(project_name, file_query, start_line=1, end_line=None):
    item = find_code_file_in_project(project_name, file_query)

    if not item:
        return f"File not found in project {project_name}: {file_query}"

    try:
        with open(item["path"], "r", encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
    except Exception as e:
        return f"Could not read file: {e}"

    if not lines:
        return f"File is empty: {item['relative_path']}"

    start_line = max(1, int(start_line))
    end_line = len(lines) if end_line is None else min(len(lines), int(end_line))

    if start_line > end_line:
        return "Invalid line range."

    width = len(str(end_line))
    selected = "\n".join(
        f"{str(index).rjust(width)} | {lines[index - 1]}"
        for index in range(start_line, end_line + 1)
    )

    return (
        f"FILE: {item['relative_path']}\n"
        f"PATH: {item['path']}\n"
        f"LINES: {start_line}-{end_line}\n\n"
        f"{selected}"
    )


def find_symbol_in_project_file(project_name, file_query, symbol_name, symbol_type="symbol"):
    item = find_code_file_in_project(project_name, file_query)

    if not item:
        return f"File not found in project {project_name}: {file_query}"

    try:
        with open(item["path"], "r", encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
    except Exception as e:
        return f"Could not read file: {e}"

    escaped = re.escape(str(symbol_name).strip())

    if symbol_type == "function":
        patterns = [
            rf"^\s*def\s+{escaped}\b",
            rf"^\s*async\s+def\s+{escaped}\b",
            rf"^\s*function\s+{escaped}\b",
            rf"^\s*const\s+{escaped}\s*=",
            rf"^\s*let\s+{escaped}\s*=",
            rf"^\s*var\s+{escaped}\s*=",
            rf"^\s*export\s+function\s+{escaped}\b",
        ]
    elif symbol_type == "class":
        patterns = [
            rf"^\s*class\s+{escaped}\b",
            rf"^\s*export\s+class\s+{escaped}\b",
            rf"^\s*public\s+class\s+{escaped}\b",
        ]
    elif symbol_type == "import":
        patterns = [
            rf"^\s*import\s+.*{escaped}",
            rf"^\s*from\s+.*{escaped}.*\s+import",
            rf"^\s*using\s+.*{escaped}",
            rf"^\s*#include\s+.*{escaped}",
        ]
    else:
        patterns = [rf"\b{escaped}\b"]

    matches = []

    for index, line in enumerate(lines, start=1):
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in patterns):
            matches.append(f"- line {index}: {line.strip()}")

            if len(matches) >= 50:
                break

    if not matches:
        return f"{symbol_type.title()} not found: {symbol_name}"

    return (
        f"Matches for {symbol_type} '{symbol_name}'\n"
        f"FILE: {item['relative_path']}\n"
        f"PATH: {item['path']}\n\n"
        + "\n".join(matches)
    )


def find_function_in_project_file(project_name, file_query, function_name):
    return find_symbol_in_project_file(
        project_name,
        file_query,
        function_name,
        symbol_type="function"
    )


def find_class_in_project_file(project_name, file_query, class_name):
    return find_symbol_in_project_file(
        project_name,
        file_query,
        class_name,
        symbol_type="class"
    )


def find_import_in_project_file(project_name, file_query, import_name):
    return find_symbol_in_project_file(
        project_name,
        file_query,
        import_name,
        symbol_type="import"
    )


def find_todo_markers_in_project(project_name, limit=100):
    files = iter_project_code_files(project_name)

    if not files:
        return f"No code files found for project: {project_name}"

    markers = ["TODO", "FIXME", "HACK", "BUG", "XXX"]
    results = []

    for item in files:
        try:
            with open(item["path"], "r", encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()
        except Exception:
            continue

        for index, line in enumerate(lines, start=1):
            upper = line.upper()

            if any(marker in upper for marker in markers):
                results.append(f"{item['relative_path']}:{index} -> {line.strip()}")

                if len(results) >= limit:
                    break

        if len(results) >= limit:
            break

    if not results:
        return "No TODO/FIXME/HACK/BUG markers found."

    return "TODO/FIXME markers found:\n" + "\n".join(results)


def open_project_in_ide(project_name, ide_name):
    return open_project_in_app(project_name, ide_name)


def open_code_file_in_ide(project_name, file_query, ide_name="VS Code"):
    item = find_code_file_in_project(project_name, file_query)

    if not item:
        return f"File not found in project {project_name}: {file_query}"

    return open_file_in_app(item["path"], ide_name)



# ==========================================================
# JARVIS TOOLS FINAL REFINEMENT LAYER
# Appended safely at the end to override older functions.
#
# Focus:
# - faster open cache
# - better app/site/folder/file/project detection
# - cleaner spoken responses
# - safer fallbacks
# ==========================================================

RECENT_OPEN_TARGETS_FILE = "recent_open_targets.json"
MAX_RECENT_OPEN_TARGETS = 100


def _final_now():
    return int(time.time())


def _final_load_recent_targets():
    data = _safe_load_json_file(RECENT_OPEN_TARGETS_FILE, [])

    if isinstance(data, list):
        return data

    return []


def _final_save_recent_target(kind, query, resolved, display=None):
    try:
        data = _final_load_recent_targets()

        data.append({
            "time": _final_now(),
            "kind": str(kind),
            "query": str(query),
            "resolved": str(resolved),
            "display": str(display or _display_name(resolved)),
        })

        data = data[-MAX_RECENT_OPEN_TARGETS:]
        _safe_save_json_file(RECENT_OPEN_TARGETS_FILE, data)

    except Exception:
        pass


def _final_clean_query(text):
    text = normalize_target_text(text).strip()
    text = re.sub(r"^(please|can you|could you|would you|jarvis|hey jarvis)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _final_normalize_project_name(text):
    value = _final_clean_query(text)
    lower = value.lower()

    aliases = {
        "cyber": "CyberShield AI",
        "cyber shield": "CyberShield AI",
        "cyber shield ai": "CyberShield AI",
        "cybershield": "CyberShield AI",
        "cybershield ai": "CyberShield AI",
        "cybers in the": "CyberShield AI",
        "jarvis": "J.A.R.V.I.S",
        "jervis": "J.A.R.V.I.S",
        "j a r v i s": "J.A.R.V.I.S",
        "manager app": "ManagerApp",
        "managerapp": "ManagerApp",
    }

    return aliases.get(lower, value)


def _final_normalize_site(text):
    lower = _final_clean_query(text).lower()
    lower = lower.replace(" dot ", ".").replace(" point ", ".").replace(" ", "")

    aliases = {
        "youtube": "youtube.com",
        "youtu.be": "youtube.com",
        "github": "github.com",
        "git-hub": "github.com",
        "chatgpt": "chat.openai.com",
        "openai": "openai.com",
        "gmail": "gmail.com",
        "google": "google.com",
        "linkedin": "linkedin.com",
        "stackoverflow": "stackoverflow.com",
        "reddit": "reddit.com",
        "yahoo": "yahoo.com",
        "yahoomail": "mail.yahoo.com",
        "outlook": "outlook.live.com",
    }

    return COMMON_WEBSITES.get(lower, aliases.get(lower, lower))


def _final_normalize_app(text):
    lower = _final_clean_query(text).lower()

    lower = lower.replace("microsoft ", "")
    lower = lower.replace("application ", "")
    lower = lower.replace("app ", "")

    aliases = {
        "fire": "firefox",
        "fox": "firefox",
        "mozilla": "firefox",
        "mozilla firefox": "firefox",
        "google": "chrome",
        "browser": "chrome",
        "google browser": "chrome",
        "code": "vscode",
        "vs": "vscode",
        "vs code": "vscode",
        "visual code": "vscode",
        "visual studio code": "vscode",
        "visual studio": "visual studio community",
        "visual studio community": "visual studio community",
        "vs community": "visual studio community",
        "idea": "intellij",
        "intellij idea": "intellij",
        "androidstudio": "android studio",
        "android studio": "android studio",
        "files": "file explorer",
        "file manager": "file explorer",
        "explorer": "file explorer",
        "terminal": "terminal",
        "windows terminal": "terminal",
        "word": "word",
        "excel": "excel",
        "power point": "powerpoint",
        "powerpoint": "powerpoint",
        "post man": "postman",
        "docker desktop": "docker desktop",
    }

    return aliases.get(lower, lower)


def _final_display_open(kind, target, display=None):
    name = display or _display_name(target)
    return f"Opening {name}"


def _final_try_startfile(path):
    try:
        path = os.path.expandvars(str(path))

        if path.endswith(":"):
            os.startfile(path)
            return True

        if os.path.exists(path):
            os.startfile(path)
            return True

    except Exception:
        pass

    return False


def _final_try_popen(command, args=None, shell=False):
    args = args or []

    try:
        subprocess.Popen(
            [command] + list(args) if not shell else command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=shell,
        )
        return True
    except Exception:
        return False


def _final_launch_candidate(candidate, args=None):
    candidate = os.path.expandvars(str(candidate))
    args = args or []

    if _final_try_startfile(candidate) and not args:
        return True

    if os.path.exists(candidate):
        return _final_try_popen(candidate, args=args, shell=False)

    found = shutil.which(candidate)

    if found:
        return _final_try_popen(found, args=args, shell=False)

    if candidate.startswith("start "):
        return _final_try_popen(candidate, shell=True)

    return False


def open_website(url):
    original = url
    url = _final_normalize_site(url)

    if not url:
        return "Website target is empty."

    if "." not in url:
        url += ".com"

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    webbrowser.open(url)
    _cache_set(original, url)
    _final_save_recent_target("website", original, url)
    return _final_display_open("website", url)


def open_folder(path):
    original = path
    query = _final_clean_query(path)

    known = get_user_folder(query)

    if known and os.path.isdir(known):
        safe_startfile(known)
        _cache_set(original, known)
        _final_save_recent_target("folder", original, known)
        return _final_display_open("folder", known)

    expanded = os.path.expandvars(str(path))

    if os.path.exists(expanded) and os.path.isdir(expanded):
        safe_startfile(expanded)
        _cache_set(original, expanded)
        _final_save_recent_target("folder", original, expanded)
        return _final_display_open("folder", expanded)

    cached = _cache_get(original)

    if cached and os.path.isdir(cached):
        safe_startfile(cached)
        _final_save_recent_target("folder", original, cached)
        return _final_display_open("folder", cached)

    found = universal_find(query, want_folder=True, max_seconds=18)

    if found and os.path.isdir(found):
        safe_startfile(found)
        _cache_set(original, found)
        _final_save_recent_target("folder", original, found)
        return _final_display_open("folder", found)

    return _not_found_message("Folder", original)


def open_file(path):
    original = path
    query = _final_clean_query(path)
    expanded = os.path.expandvars(str(path))

    if os.path.exists(expanded) and os.path.isfile(expanded):
        safe_startfile(expanded)
        _cache_set(original, expanded)
        _final_save_recent_target("file", original, expanded)
        return _final_display_open("file", expanded)

    cached = _cache_get(original)

    if cached and os.path.isfile(cached):
        safe_startfile(cached)
        _final_save_recent_target("file", original, cached)
        return _final_display_open("file", cached)

    found = universal_find(query, want_file=True, max_seconds=18)

    if found and os.path.isfile(found):
        safe_startfile(found)
        _cache_set(original, found)
        _final_save_recent_target("file", original, found)
        return _final_display_open("file", found)

    return _not_found_message("File", original)


def open_installed_app(app_name):
    original_name = str(app_name).strip()
    app_name = _final_normalize_app(app_name)

    cached = _cache_get(app_name)

    if cached and _final_launch_candidate(cached):
        _final_save_recent_target("application", original_name, cached, _display_name(app_name))
        return _final_display_open("application", app_name)

    candidates = KNOWN_APP_COMMANDS.get(app_name, [])

    for candidate in candidates:
        if _final_launch_candidate(candidate):
            _cache_set(app_name, candidate)
            _final_save_recent_target("application", original_name, candidate, _display_name(app_name))
            return _final_display_open("application", app_name)

    # Windows direct command fallback.
    direct_commands = {
        "calculator": "calc.exe",
        "notepad": "notepad.exe",
        "paint": "mspaint.exe",
        "command prompt": "cmd.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "terminal": "wt.exe",
        "file explorer": "explorer.exe",
        "settings": "ms-settings:",
        "task manager": "taskmgr.exe",
    }

    if app_name in direct_commands and _final_launch_candidate(direct_commands[app_name]):
        _cache_set(app_name, direct_commands[app_name])
        return _final_display_open("application", app_name)

    apps = load_apps()
    query = normalize_name(app_name)
    aliases = get_aliases(app_name)
    normalized_aliases = [normalize_name(alias) for alias in aliases]
    normalized_aliases.append(query)

    best = None
    best_score = 0

    for name, path in apps.items():
        if is_bad_match(name):
            continue

        normalized = normalize_name(name)

        for alias in normalized_aliases:
            if not alias:
                continue

            if alias == normalized:
                score = 1.0
            elif len(alias) >= 4 and (alias in normalized or normalized in alias):
                score = 0.90
            else:
                score = difflib.SequenceMatcher(None, alias, normalized).ratio()

            if score > best_score:
                best_score = score
                best = (name, path)

    if best and best_score >= 0.72:
        name, path = best

        if launch_path(path):
            _cache_set(app_name, path)
            _final_save_recent_target("application", original_name, path, name)
            return _final_display_open("application", name)

    # Last fallback: try raw command only if it is a simple safe token.
    if re.match(r"^[a-zA-Z0-9_. -]{2,60}$", app_name):
        if _final_launch_candidate(app_name):
            return _final_display_open("application", app_name)

    return f"Could not find application: {_display_name(original_name)}"


def find_project(project_name):
    projects = load_projects()

    if not projects:
        return None

    project_name = _final_normalize_project_name(project_name)
    query = normalize_name(project_name)

    if query in projects and isinstance(projects[query], dict):
        project = projects[query]
        path = project.get("path", "")

        if path and os.path.exists(path):
            return project

    ranked = []

    for key, project in projects.items():
        if not isinstance(project, dict):
            continue

        score = project_match_score(project, project_name)
        name = project.get("name", "")
        path = project.get("path", "")

        aliases = [
            name,
            os.path.basename(path),
            name.replace("_", " "),
            name.replace("-", " "),
        ]

        for alias in aliases:
            alias_norm = normalize_name(alias)

            if query == alias_norm:
                score = max(score, 1.0)
            elif query and len(query) >= 3 and (query in alias_norm or alias_norm in query):
                score = max(score, 0.92)

        if path and os.path.exists(path):
            score += 0.20
        elif path:
            score -= 0.20

        ranked.append((score, project))

    ranked.sort(key=lambda item: item[0], reverse=True)

    if ranked and ranked[0][0] >= 0.60:
        candidate = ranked[0][1]
        path = candidate.get("path", "")

        if path and os.path.exists(path):
            return candidate

    found_path = universal_find(project_name, want_folder=True, max_seconds=20)

    if found_path and os.path.isdir(found_path):
        return {
            "name": os.path.basename(found_path),
            "path": found_path,
            "type": "Detected"
        }

    return None


def open_project(project_name):
    original = project_name
    project_name = _final_normalize_project_name(project_name)
    project = find_project(project_name)

    if project:
        path = project.get("path", "")
        name = project.get("name", project_name)

        if path and os.path.exists(path):
            safe_startfile(path)
            _cache_set(original, path)
            _final_save_recent_target("project", original, path, name)
            return _final_display_open("project", name)

    cached = _cache_get(original)

    if cached and os.path.isdir(cached):
        safe_startfile(cached)
        _final_save_recent_target("project", original, cached)
        return _final_display_open("project", cached)

    found = universal_find(project_name, want_folder=True, max_seconds=20)

    if found and os.path.isdir(found):
        safe_startfile(found)
        _cache_set(original, found)
        _final_save_recent_target("project", original, found)
        return _final_display_open("project", found)

    return f"Project not found: {_display_name(original)}"


def open_anything(target):
    target = _final_clean_query(target)

    if not target:
        return "Missing target."

    lower = target.lower()

    # Explicit URL/site.
    if looks_like_website(lower):
        return open_website(lower)

    # Known folder.
    folder = get_user_folder(lower)

    if folder:
        return open_folder(folder)

    # Existing path.
    expanded = os.path.expandvars(target)

    if os.path.exists(expanded):
        if os.path.isdir(expanded):
            return open_folder(expanded)
        if os.path.isfile(expanded):
            return open_file(expanded)

    # Project aliases first.
    project_name = _final_normalize_project_name(target)
    project = find_project(project_name)

    if project:
        return open_project(project_name)

    # App aliases.
    normalized_app = _final_normalize_app(target)

    if normalized_app in KNOWN_APP_COMMANDS or normalized_app in APP_NAME_CORRECTIONS or normalize_name(normalized_app) in APP_ALIASES:
        return open_installed_app(normalized_app)

    # Cache.
    cached = _cache_get(target)

    if cached and os.path.exists(cached):
        if os.path.isdir(cached):
            return open_folder(cached)
        return open_file(cached)

    # File/folder search.
    found = universal_find(target, max_seconds=18)

    if found:
        if os.path.isdir(found):
            return open_folder(found)
        return open_file(found)

    # Website fallback for simple known words.
    if lower in COMMON_WEBSITES:
        return open_website(lower)

    # Application fallback.
    return open_installed_app(target)


def open_project_in_app(project_name, app_name):
    project_name = _final_normalize_project_name(project_name)
    app_name = _final_normalize_app(app_name)
    project = find_project(project_name)

    if not project:
        return f"Project not found: {_display_name(project_name)}"

    project_path = project.get("path", "")

    if not project_path or not os.path.exists(project_path):
        return f"Project path not found: {_display_name(project_name)}"

    app_command = resolve_app_command(app_name)

    if not app_command:
        return f"Application/IDE not found: {_display_name(app_name)}"

    try:
        if str(app_command).endswith(":"):
            safe_startfile(app_command)
            return _final_display_open("application", app_name)

        subprocess.Popen(
            [app_command, project_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

        _final_save_recent_target("project_in_app", project_name, project_path, project.get("name", project_name))
        return f"Opening {project.get('name', project_name)} in {_display_name(app_name)}"

    except Exception as e:
        return f"Could not open project in {_display_name(app_name)}: {e}"


def open_file_in_app(file_path, app_name):
    app_name = _final_normalize_app(app_name)

    if not file_path or not os.path.exists(file_path):
        return f"File not found: {_display_name(file_path)}"

    app_command = resolve_app_command(app_name)

    if not app_command:
        return f"Application/IDE not found: {_display_name(app_name)}"

    try:
        subprocess.Popen(
            [app_command, file_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

        _final_save_recent_target("file_in_app", file_path, file_path, os.path.basename(file_path))
        return f"Opening {_display_name(file_path)} in {_display_name(app_name)}"

    except Exception as e:
        return f"Could not open file in {_display_name(app_name)}: {e}"


def tools_self_test():
    tests = [
        ("open_anything", "google"),
        ("open_anything", "downloads"),
        ("open_installed_app", "fire"),
        ("open_installed_app", "vs code"),
        ("open_project", "cyber"),
        ("open_project_in_app", "cyber", "vs code"),
    ]

    output = ["TOOLS SELF TEST - dry description", ""]

    for test in tests:
        try:
            name = test[0]
            args = test[1:]

            if name == "open_anything":
                output.append(f"{name}({args[0]!r}) -> would resolve via universal opener")
            elif name == "open_installed_app":
                output.append(f"{name}({args[0]!r}) -> normalized as {_final_normalize_app(args[0])}")
            elif name == "open_project":
                output.append(f"{name}({args[0]!r}) -> normalized as {_final_normalize_project_name(args[0])}")
            elif name == "open_project_in_app":
                output.append(
                    f"{name}({args[0]!r}, {args[1]!r}) -> "
                    f"{_final_normalize_project_name(args[0])} in {_final_normalize_app(args[1])}"
                )
        except Exception as error:
            output.append(f"{test} -> ERROR: {error}")

    return "\n".join(output)


def recent_open_targets():
    data = _final_load_recent_targets()

    if not data:
        return "No recent open targets."

    output = ["Recent open targets:", ""]

    for item in data[-20:]:
        output.append(
            f"- {item.get('kind')} | {item.get('display')} | query: {item.get('query')}"
        )

    return "\n".join(output)



# ==========================================================
# J.A.R.V.I.S TOOLS VOICE + FIREFOX FASTFIX
# Added at the end so it overrides older open functions safely.
#
# Fixes:
# - "open browser firefox" no longer becomes Windows command "browser firefox".
# - "open fire", "open fire fox", "open firefox" all resolve to Firefox.
# - Apps open before slow disk search.
# - Websites/folders/projects/files still work.
# - Spoken responses stay short: "Opening Firefox".
# ==========================================================

VOICE_OPEN_FASTFIX_VERSION = "J.A.R.V.I.S Tools Voice Firefox FastFix"

BROWSER_ALIASES = {
    "firefox": "firefox",
    "fire fox": "firefox",
    "fire": "firefox",
    "fox": "firefox",
    "mozilla": "firefox",
    "mozilla firefox": "firefox",

    "chrome": "chrome",
    "google chrome": "chrome",
    "google": "chrome",

    "edge": "edge",
    "microsoft edge": "edge",
}

APP_VOICE_ALIASES = {
    "browser firefox": "firefox",
    "browser fire fox": "firefox",
    "browser fire": "firefox",
    "web browser firefox": "firefox",
    "open browser firefox": "firefox",
    "open browser fire": "firefox",

    "browser chrome": "chrome",
    "web browser chrome": "chrome",
    "browser google": "chrome",

    "browser edge": "edge",
    "web browser edge": "edge",

    "visual studio code": "vscode",
    "vs code": "vscode",
    "visual code": "vscode",
    "code editor": "vscode",
    "open code": "vscode",

    "visual studio": "visual studio community",
    "vs community": "visual studio community",

    "file manager": "file explorer",
    "files": "file explorer",
    "explorer": "file explorer",

    "command line": "cmd",
    "command prompt": "cmd",
    "terminal": "terminal",
    "windows terminal": "terminal",

    "power point": "powerpoint",
    "post man": "postman",
    "docker desktop": "docker desktop",
}

FAST_FOLDER_ALIASES = {
    "download": "downloads",
    "downloads": "downloads",
    "document": "documents",
    "documents": "documents",
    "desktop": "desktop",
    "picture": "pictures",
    "pictures": "pictures",
    "image": "pictures",
    "images": "pictures",
    "music": "music",
    "video": "videos",
    "videos": "videos",
}


def _voice_fix_clean(text):
    text = normalize_target_text(text)
    text = str(text or "").strip().lower()
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)

    remove_prefixes = [
        "jarvis ",
        "hey jarvis ",
        "please ",
        "can you ",
        "could you ",
        "would you ",
        "open ",
        "launch ",
        "start ",
        "run ",
    ]

    changed = True
    while changed:
        changed = False
        for prefix in remove_prefixes:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                changed = True

    return text


def _voice_fix_app_name(text):
    raw = str(text or "").strip()
    clean = _voice_fix_clean(raw)

    if clean in APP_VOICE_ALIASES:
        return APP_VOICE_ALIASES[clean]

    if clean.startswith("browser "):
        browser_target = clean.replace("browser ", "", 1).strip()
        return BROWSER_ALIASES.get(browser_target, browser_target)

    if clean.startswith("web browser "):
        browser_target = clean.replace("web browser ", "", 1).strip()
        return BROWSER_ALIASES.get(browser_target, browser_target)

    if clean in BROWSER_ALIASES:
        return BROWSER_ALIASES[clean]

    if clean in APP_VOICE_ALIASES:
        return APP_VOICE_ALIASES[clean]

    # Existing correction dictionaries.
    if clean in APP_NAME_CORRECTIONS:
        return APP_NAME_CORRECTIONS[clean]

    try:
        normalized = _final_normalize_app(clean)
        if normalized:
            return normalized
    except Exception:
        pass

    try:
        normalized = _normalize_app_query(clean)
        if normalized:
            return normalized
    except Exception:
        pass

    return clean


def _voice_fix_project_name(text):
    clean = _voice_fix_clean(text)

    aliases = {
        "cyber": "CyberShield AI",
        "cyber shield": "CyberShield AI",
        "cyber shield ai": "CyberShield AI",
        "cybershield": "CyberShield AI",
        "cybershield ai": "CyberShield AI",
        "cybers in the": "CyberShield AI",
        "this project": "CyberShield AI",
        "current project": "CyberShield AI",
        "manager app": "ManagerApp",
        "managerapp": "ManagerApp",
        "jarvis": "J.A.R.V.I.S",
        "jervis": "J.A.R.V.I.S",
        "j a r v i s": "J.A.R.V.I.S",
    }

    return aliases.get(clean, text)


def _voice_fix_display(target):
    target = str(target or "").strip().lower()

    pretty = {
        "firefox": "Firefox",
        "chrome": "Chrome",
        "edge": "Microsoft Edge",
        "vscode": "VS Code",
        "visual studio community": "Visual Studio Community",
        "file explorer": "File Explorer",
        "cmd": "Command Prompt",
        "terminal": "Windows Terminal",
        "powershell": "PowerShell",
        "word": "Word",
        "excel": "Excel",
        "powerpoint": "PowerPoint",
        "postman": "Postman",
        "docker desktop": "Docker Desktop",
    }

    return pretty.get(target, _display_name(target))


def _voice_fix_launch_candidate(candidate, args=None):
    candidate = os.path.expandvars(str(candidate))
    args = args or []

    try:
        if candidate.endswith(":"):
            os.startfile(candidate)
            return True

        if os.path.exists(candidate):
            subprocess.Popen(
                [candidate] + list(args),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            return True

        found = shutil.which(candidate)
        if found:
            subprocess.Popen(
                [found] + list(args),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
            )
            return True

        if candidate.lower().startswith("start "):
            subprocess.Popen(candidate, shell=True)
            return True

    except Exception:
        return False

    return False


def _voice_fix_known_app_candidates(app_name):
    app_name = _voice_fix_app_name(app_name)

    extra = {
        "firefox": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
            "firefox.exe",
            "firefox",
        ],
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            "chrome.exe",
            "chrome",
        ],
        "edge": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "msedge.exe",
        ],
        "vscode": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
            "code.cmd",
            "code",
        ],
    }

    candidates = []
    candidates.extend(extra.get(app_name, []))
    candidates.extend(KNOWN_APP_COMMANDS.get(app_name, []))

    return candidates


def open_installed_app(app_name):
    original_name = str(app_name or "").strip()
    app_name = _voice_fix_app_name(original_name)

    # Never pass phrases like "browser firefox" to Windows directly.
    if app_name.startswith("browser "):
        app_name = _voice_fix_app_name(app_name)

    cached = _cache_get(app_name)
    if cached and _voice_fix_launch_candidate(cached):
        _final_save_recent_target("application", original_name, cached, _voice_fix_display(app_name))
        return f"Opening {_voice_fix_display(app_name)}"

    # 1. Known commands first. This avoids slow disk search and fixes Firefox.
    for candidate in _voice_fix_known_app_candidates(app_name):
        if _voice_fix_launch_candidate(candidate):
            _cache_set(app_name, candidate)
            _final_save_recent_target("application", original_name, candidate, _voice_fix_display(app_name))
            return f"Opening {_voice_fix_display(app_name)}"

    # 2. Windows command fallback.
    direct_commands = {
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "notepad": "notepad.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "powershell": "powershell.exe",
        "terminal": "wt.exe",
        "file explorer": "explorer.exe",
        "explorer": "explorer.exe",
        "settings": "ms-settings:",
        "task manager": "taskmgr.exe",
        "word": "winword.exe",
        "excel": "excel.exe",
        "powerpoint": "powerpnt.exe",
    }

    if app_name in direct_commands and _voice_fix_launch_candidate(direct_commands[app_name]):
        _cache_set(app_name, direct_commands[app_name])
        _final_save_recent_target("application", original_name, direct_commands[app_name], _voice_fix_display(app_name))
        return f"Opening {_voice_fix_display(app_name)}"

    # 3. App index fallback.
    apps = load_apps()
    query = normalize_name(app_name)
    aliases = get_aliases(app_name)
    normalized_aliases = [normalize_name(alias) for alias in aliases]
    normalized_aliases.append(query)

    best = None
    best_score = 0

    for name, path in apps.items():
        if is_bad_match(name):
            continue

        normalized = normalize_name(name)

        for alias in normalized_aliases:
            if not alias:
                continue

            if alias == normalized:
                score = 1.0
            elif len(alias) >= 4 and (alias in normalized or normalized in alias):
                score = 0.92
            else:
                score = difflib.SequenceMatcher(None, alias, normalized).ratio()

            if score > best_score:
                best_score = score
                best = (name, path)

    if best and best_score >= 0.72:
        name, path = best
        if launch_path(path):
            _cache_set(app_name, path)
            _final_save_recent_target("application", original_name, path, name)
            return f"Opening {_display_name(name)}"

    return f"Could not find application: {_display_name(original_name)}"


def open_website(url):
    original = url
    url = _final_normalize_site(url)

    if not url:
        return "Website target is empty."

    if "." not in url:
        url += ".com"

    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    webbrowser.open(url)
    _cache_set(original, url)
    _final_save_recent_target("website", original, url)
    return f"Opening {_display_name(url)}"


def open_folder(path):
    original = path
    clean = _voice_fix_clean(path)

    if clean in FAST_FOLDER_ALIASES:
        folder_path = get_user_folder(FAST_FOLDER_ALIASES[clean])
        if folder_path:
            safe_startfile(folder_path)
            _cache_set(original, folder_path)
            _final_save_recent_target("folder", original, folder_path)
            return f"Opening {_display_name(folder_path)}"

    expanded = os.path.expandvars(str(path))

    if os.path.exists(expanded) and os.path.isdir(expanded):
        safe_startfile(expanded)
        _cache_set(original, expanded)
        _final_save_recent_target("folder", original, expanded)
        return f"Opening {_display_name(expanded)}"

    cached = _cache_get(original)
    if cached and os.path.isdir(cached):
        safe_startfile(cached)
        _final_save_recent_target("folder", original, cached)
        return f"Opening {_display_name(cached)}"

    found = universal_find(clean or original, want_folder=True, max_seconds=12)
    if found and os.path.isdir(found):
        safe_startfile(found)
        _cache_set(original, found)
        _final_save_recent_target("folder", original, found)
        return f"Opening {_display_name(found)}"

    return _not_found_message("Folder", original)


def open_file(path):
    original = path
    clean = _voice_fix_clean(path)
    expanded = os.path.expandvars(str(path))

    if os.path.exists(expanded) and os.path.isfile(expanded):
        safe_startfile(expanded)
        _cache_set(original, expanded)
        _final_save_recent_target("file", original, expanded)
        return f"Opening {_display_name(expanded)}"

    cached = _cache_get(original)
    if cached and os.path.isfile(cached):
        safe_startfile(cached)
        _final_save_recent_target("file", original, cached)
        return f"Opening {_display_name(cached)}"

    found = universal_find(clean or original, want_file=True, max_seconds=12)
    if found and os.path.isfile(found):
        safe_startfile(found)
        _cache_set(original, found)
        _final_save_recent_target("file", original, found)
        return f"Opening {_display_name(found)}"

    return _not_found_message("File", original)


def find_project(project_name):
    project_name = _voice_fix_project_name(project_name)
    projects = load_projects()

    if not projects:
        return None

    query = normalize_name(project_name)

    if query in projects and isinstance(projects[query], dict):
        project = projects[query]
        path = project.get("path", "")

        if path and os.path.exists(path):
            return project

    ranked = []

    for key, project in projects.items():
        if not isinstance(project, dict):
            continue

        score = project_match_score(project, project_name)
        name = project.get("name", "")
        path = project.get("path", "")

        for alias in [
            name,
            os.path.basename(path),
            name.replace("_", " "),
            name.replace("-", " "),
            _voice_fix_project_name(name),
        ]:
            alias_norm = normalize_name(alias)

            if query == alias_norm:
                score = max(score, 1.0)
            elif query and len(query) >= 3 and (query in alias_norm or alias_norm in query):
                score = max(score, 0.92)

        if path and os.path.exists(path):
            score += 0.20
        elif path:
            score -= 0.20

        ranked.append((score, project))

    ranked.sort(key=lambda item: item[0], reverse=True)

    if ranked and ranked[0][0] >= 0.60:
        candidate = ranked[0][1]
        path = candidate.get("path", "")

        if path and os.path.exists(path):
            return candidate

    # Search fallback with lower timeout.
    found_path = universal_find(project_name, want_folder=True, max_seconds=12)
    if found_path and os.path.isdir(found_path):
        return {
            "name": os.path.basename(found_path),
            "path": found_path,
            "type": "Detected"
        }

    return None


def open_project(project_name):
    original = project_name
    project_name = _voice_fix_project_name(project_name)
    project = find_project(project_name)

    if project:
        path = project.get("path", "")
        name = project.get("name", project_name)

        if path and os.path.exists(path):
            safe_startfile(path)
            _cache_set(original, path)
            _final_save_recent_target("project", original, path, name)
            return f"Opening {_display_name(name)}"

    cached = _cache_get(original)
    if cached and os.path.isdir(cached):
        safe_startfile(cached)
        _final_save_recent_target("project", original, cached)
        return f"Opening {_display_name(cached)}"

    found = universal_find(project_name, want_folder=True, max_seconds=12)
    if found and os.path.isdir(found):
        safe_startfile(found)
        _cache_set(original, found)
        _final_save_recent_target("project", original, found)
        return f"Opening {_display_name(found)}"

    return f"Project not found: {_display_name(original)}"


def open_anything(target):
    target = normalize_target_text(target)

    if not target:
        return "Missing target."

    raw_lower = target.lower().strip()
    clean = _voice_fix_clean(target)

    # 1. Explicit browser command. Example: "browser firefox".
    if clean.startswith("browser ") or clean.startswith("web browser ") or clean in BROWSER_ALIASES:
        return open_installed_app(clean)

    # 2. Website.
    if looks_like_website(raw_lower) or raw_lower in COMMON_WEBSITES:
        return open_website(raw_lower)

    # 3. Known folder.
    if clean in FAST_FOLDER_ALIASES:
        return open_folder(clean)

    folder = get_user_folder(raw_lower)
    if folder:
        return open_folder(folder)

    # 4. Application before slow universal_find.
    app_name = _voice_fix_app_name(target)
    if (
        app_name in KNOWN_APP_COMMANDS
        or app_name in APP_NAME_CORRECTIONS
        or app_name in APP_VOICE_ALIASES.values()
        or app_name in BROWSER_ALIASES.values()
    ):
        return open_installed_app(app_name)

    # 5. Existing direct path.
    expanded = os.path.expandvars(target)
    if os.path.exists(expanded):
        if os.path.isdir(expanded):
            return open_folder(expanded)
        if os.path.isfile(expanded):
            return open_file(expanded)

    # 6. Project.
    project_name = _voice_fix_project_name(target)
    project = find_project(project_name)
    if project:
        return open_project(project_name)

    # 7. Cache.
    cached = _cache_get(target)
    if cached and os.path.exists(cached):
        if os.path.isdir(cached):
            return open_folder(cached)
        return open_file(cached)

    # 8. Last app attempt before disk search.
    app_result = open_installed_app(app_name)
    if not app_result.lower().startswith("could not find application"):
        return app_result

    # 9. Controlled search fallback.
    found = universal_find(target, max_seconds=12)
    if found:
        if os.path.isdir(found):
            return open_folder(found)
        return open_file(found)

    return f"Could not open: {_display_name(target)}"


def resolve_app_command(app_name):
    app_name = _voice_fix_app_name(app_name)

    for candidate in _voice_fix_known_app_candidates(app_name):
        candidate = os.path.expandvars(candidate)

        if candidate.endswith(":"):
            return candidate

        if os.path.exists(candidate):
            return candidate

        found = shutil.which(candidate)
        if found:
            return found

    apps = load_apps()
    aliases = get_aliases(app_name)
    normalized_aliases = [normalize_name(alias) for alias in aliases]
    normalized_aliases.append(normalize_name(app_name))

    best_match = None
    best_score = 0

    for name, path in apps.items():
        if is_bad_match(name):
            continue

        normalized = normalize_name(name)

        for alias in normalized_aliases:
            if normalized == alias:
                return path

            score = difflib.SequenceMatcher(None, alias, normalized).ratio()
            if score > best_score:
                best_score = score
                best_match = path

    if best_match and best_score >= 0.72:
        return best_match

    return None


def open_project_in_app(project_name, app_name):
    project_name = _voice_fix_project_name(project_name)
    app_name = _voice_fix_app_name(app_name)

    project = find_project(project_name)

    if not project:
        return f"Project not found: {_display_name(project_name)}"

    project_path = project.get("path", "")

    if not project_path or not os.path.exists(project_path):
        return f"Project path not found: {_display_name(project_name)}"

    app_command = resolve_app_command(app_name)

    if not app_command:
        return f"Application/IDE not found: {_display_name(app_name)}"

    try:
        if str(app_command).endswith(":"):
            safe_startfile(app_command)
            return f"Opening {_voice_fix_display(app_name)}"

        subprocess.Popen(
            [app_command, project_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

        _final_save_recent_target("project_in_app", project_name, project_path, project.get("name", project_name))
        return f"Opening {_display_name(project.get('name', project_name))} in {_voice_fix_display(app_name)}"

    except Exception as e:
        return f"Could not open project in {_voice_fix_display(app_name)}: {e}"


def open_file_in_app(file_path, app_name):
    app_name = _voice_fix_app_name(app_name)

    if not file_path or not os.path.exists(file_path):
        return f"File not found: {_display_name(file_path)}"

    app_command = resolve_app_command(app_name)

    if not app_command:
        return f"Application/IDE not found: {_voice_fix_display(app_name)}"

    try:
        subprocess.Popen(
            [app_command, file_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

        _final_save_recent_target("file_in_app", file_path, file_path, os.path.basename(file_path))
        return f"Opening {_display_name(file_path)} in {_voice_fix_display(app_name)}"

    except Exception as e:
        return f"Could not open file in {_voice_fix_display(app_name)}: {e}"


def tools_voice_fastfix_self_test():
    tests = [
        "open browser firefox",
        "browser firefox",
        "open fire",
        "open fire fox",
        "open firefox",
        "open browser chrome",
        "open vs code",
        "open downloads",
        "open project cyber",
    ]

    output = [
        "TOOLS VOICE FIREFOX FASTFIX SELF TEST",
        f"Version: {VOICE_OPEN_FASTFIX_VERSION}",
        "",
    ]

    for item in tests:
        clean = _voice_fix_clean(item)
        app = _voice_fix_app_name(item)
        project = _voice_fix_project_name(item)
        output.append(f"RAW: {item}")
        output.append(f" CLEAN: {clean}")
        output.append(f" APP: {app}")
        output.append(f" PROJECT: {project}")
        output.append("")

    return "\n".join(output)

