import os
import json
import string

INDEX_FILE = "apps_index.json"

SEARCH_PATHS = [
    r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    os.path.expandvars(
        r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"
    ),
]

EXE_SEARCH_PATHS = [
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    os.path.expandvars(r"%LOCALAPPDATA%"),
]

SKIP_DIRS = {
    "windows",
    "winsxs",
    "temp",
    "cache",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "jarvis-env",
    ".git",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".cache",
}

IMPORTANT_EXE_NAMES = {
    "chrome.exe",
    "firefox.exe",
    "msedge.exe",
    "code.exe",
    "spotify.exe",
    "steam.exe",
    "discord.exe",
    "telegram.exe",
    "whatsapp.exe",
    "winword.exe",
    "excel.exe",
    "powerpnt.exe",
    "notepad.exe",
    "mspaint.exe",
    "calc.exe",
    "cmd.exe",
    "powershell.exe",
    "wt.exe",
}


def add_app(apps, name, path):
    key = str(name).lower().strip()

    if not key:
        return

    if not path or not os.path.exists(path):
        return

    if key not in apps:
        apps[key] = path


def scan_shortcuts(apps):
    for root_path in SEARCH_PATHS:
        if not os.path.exists(root_path):
            continue

        for root, dirs, files in os.walk(root_path):
            dirs[:] = [
                d for d in dirs
                if d.lower() not in SKIP_DIRS
            ]

            for file in files:
                if file.lower().endswith(".lnk"):
                    name = os.path.splitext(file)[0]

                    add_app(
                        apps,
                        name,
                        os.path.join(root, file)
                    )


def scan_executables(apps):
    for root_path in EXE_SEARCH_PATHS:
        if not os.path.exists(root_path):
            continue

        for root, dirs, files in os.walk(root_path):
            dirs[:] = [
                d for d in dirs
                if d.lower() not in SKIP_DIRS
            ]

            for file in files:
                if not file.lower().endswith(".exe"):
                    continue

                exe_lower = file.lower()

                # Index important/common executables and executables in app-like folders.
                parent = os.path.basename(root).lower()
                if exe_lower not in IMPORTANT_EXE_NAMES and parent not in exe_lower:
                    continue

                name = os.path.splitext(file)[0]

                add_app(
                    apps,
                    name,
                    os.path.join(root, file)
                )


def scan_connected_drives(apps):
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"

        if not os.path.exists(drive):
            continue

        # C is already scanned through Program Files / LOCALAPPDATA.
        if drive.upper().startswith("C:"):
            continue

        try:
            for root, dirs, files in os.walk(drive):
                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in SKIP_DIRS
                ]

                for file in files:
                    if not file.lower().endswith(".exe"):
                        continue

                    name = os.path.splitext(file)[0]

                    add_app(
                        apps,
                        name,
                        os.path.join(root, file)
                    )

        except Exception:
            continue


def add_windows_builtin_apps(apps):
    system_root = os.environ.get("WINDIR", r"C:\Windows")
    system32 = os.path.join(system_root, "System32")

    builtins = {
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "notepad": "notepad.exe",
        "paint": "mspaint.exe",
        "mspaint": "mspaint.exe",
        "command prompt": "cmd.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "task manager": "taskmgr.exe",
        "control panel": "control.exe",
        "file explorer": "explorer.exe",
        "explorer": "explorer.exe",
    }

    for name, exe in builtins.items():
        path = os.path.join(system32, exe)

        if os.path.exists(path):
            add_app(apps, name, path)
        else:
            apps.setdefault(name, exe)


def build_index():
    apps = {}

    print("Scanning Windows built-in apps...")
    add_windows_builtin_apps(apps)

    print("Scanning Start Menu shortcuts...")
    scan_shortcuts(apps)

    print("Scanning installed applications...")
    scan_executables(apps)

    print("Scanning connected drives and USB/external storage...")
    scan_connected_drives(apps)

    with open(
        INDEX_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            apps,
            f,
            indent=4,
            ensure_ascii=False
        )

    print(f"Indexed {len(apps)} applications.")
    print(f"Saved to: {INDEX_FILE}")


if __name__ == "__main__":
    build_index()
