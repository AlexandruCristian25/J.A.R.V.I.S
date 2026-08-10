import os
import json
import string
import re
import time


INDEX_FILE = "projects_index.json"

PROJECT_MARKERS = [
    ".git",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile",
    "vite.config.js",
    "vite.config.ts",
    "next.config.js",
    "next.config.ts",
    "angular.json",
    "composer.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    ".csproj",
    ".sln",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
    "Cargo.toml",
    "go.mod",
    "Makefile",
    "CMakeLists.txt",
    "main.py",
    "app.py",
    "manage.py",
]

STRONG_PROJECT_MARKERS = {
    ".git",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "vite.config.js",
    "vite.config.ts",
    "next.config.js",
    "next.config.ts",
    "angular.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Cargo.toml",
    "go.mod",
    ".sln",
    "docker-compose.yml",
    "docker-compose.yaml",
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
    "site-packages",
    ".git",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".next",
    ".cache",
    ".gradle",
    ".android",
    "vendor",
    "target",
    "bin",
    "obj",
}

SKIP_PATH_PARTS = {
    "appdata",
    "local\\programs",
    "roaming\\npm",
    "android\\sdk",
    ".gradle\\caches",
    "python313\\lib\\test",
    "python312\\lib\\test",
    "python311\\lib\\test",
    "windows\\winsxs",
    "windows\\servicing",
}

PREFERRED_ROOT_NAMES = {
    "projects",
    "project",
    "work",
    "workspace",
    "repos",
    "repositories",
    "github",
    "desktop",
    "documents",
    "downloads",
    "stick",
    "stick2",
    "de facut",
    "cyber security app",
}


# ==========================
# NORMALIZE / ALIASES
# ==========================
def normalize_name(name):
    return re.sub(
        r"[^a-z0-9]",
        "",
        str(name).lower()
    )


def split_words(name):
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


def project_aliases(name, path=""):
    words = split_words(name)
    aliases = set()

    aliases.add(normalize_name(name))

    if words:
        aliases.add(normalize_name(" ".join(words)))
        aliases.add(normalize_name("_".join(words)))
        aliases.add(normalize_name("-".join(words)))
        aliases.add(normalize_name("".join(words)))

    initials = compact_initials(words)

    if initials:
        aliases.add(normalize_name(initials))

    if path:
        folder = os.path.basename(path)
        parent = os.path.basename(os.path.dirname(path))

        for value in [folder, parent]:
            if value:
                aliases.add(normalize_name(value))

                for part in split_words(value):
                    if len(part) >= 3:
                        aliases.add(normalize_name(part))

    # Useful manual aliases for your main projects
    compact = normalize_name(name)

    if "cyber" in compact or "shield" in compact:
        aliases.update({
            "cyber",
            "cybershield",
            "cybershieldai",
            "cybersecurityapp",
            "shieldai",
        })

    if "jarvis" in compact or "jervis" in compact:
        aliases.update({
            "jarvis",
            "jervis",
            "assistant",
            "voiceassistant",
        })

    return sorted(alias for alias in aliases if alias)


def should_skip_path(path):
    lower = path.lower()

    for part in SKIP_PATH_PARTS:
        if part in lower:
            return True

    return False


# ==========================
# DRIVES / ROOTS
# ==========================
def get_available_drives():
    drives = []

    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"

        if os.path.exists(drive):
            drives.append(drive)

    return drives


def get_scan_roots():
    roots = []

    # Current JARVIS folder and parent first
    cwd = os.getcwd()
    roots.append(cwd)
    roots.append(os.path.dirname(cwd))

    # User common folders
    home = os.path.expanduser("~")
    for folder in ["Desktop", "Documents", "Downloads"]:
        path = os.path.join(home, folder)

        if os.path.exists(path):
            roots.append(path)

    # All connected drives: C, D, E, USB, external HDD/SSD
    roots.extend(get_available_drives())

    # Remove duplicates while keeping order
    unique = []
    seen = set()

    for root in roots:
        normalized = os.path.abspath(root).lower()

        if normalized not in seen and os.path.exists(root):
            seen.add(normalized)
            unique.append(root)

    return unique


# ==========================
# PROJECT DETECTION
# ==========================
def is_project_folder(dirs, files):
    lower_dirs = {d.lower() for d in dirs}
    lower_files = {f.lower() for f in files}
    present = lower_dirs | lower_files

    for marker in PROJECT_MARKERS:
        marker_lower = marker.lower()

        if marker_lower in present:
            return True

    # Extra heuristic: source folder + known file types
    source_dirs = {"src", "app", "backend", "frontend", "components", "pages"}
    code_extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cs", ".cpp", ".c"}

    has_source_dir = bool(lower_dirs & source_dirs)
    has_code_files = any(
        os.path.splitext(f.lower())[1] in code_extensions
        for f in lower_files
    )

    return has_source_dir and has_code_files


def is_strong_project_folder(dirs, files):
    lower_dirs = {d.lower() for d in dirs}
    lower_files = {f.lower() for f in files}
    present = lower_dirs | lower_files

    return bool(present & {m.lower() for m in STRONG_PROJECT_MARKERS})


def get_project_type(dirs, files):
    lower_dirs = {d.lower() for d in dirs}
    lower_files = {f.lower() for f in files}

    if "angular.json" in lower_files:
        return "Angular"

    if "vite.config.js" in lower_files or "vite.config.ts" in lower_files:
        return "Vite"

    if "next.config.js" in lower_files or "next.config.ts" in lower_files:
        return "Next.js"

    if "package.json" in lower_files:
        return "Node.js / JavaScript"

    if "requirements.txt" in lower_files or "pyproject.toml" in lower_files or "poetry.lock" in lower_files:
        return "Python"

    if any(f.endswith(".csproj") for f in lower_files) or any(f.endswith(".sln") for f in lower_files):
        return "C# / .NET"

    if "pom.xml" in lower_files or "build.gradle" in lower_files or "build.gradle.kts" in lower_files:
        return "Java / Gradle / Maven"

    if "composer.json" in lower_files:
        return "PHP"

    if "cargo.toml" in lower_files:
        return "Rust"

    if "go.mod" in lower_files:
        return "Go"

    if "docker-compose.yml" in lower_files or "docker-compose.yaml" in lower_files or "dockerfile" in lower_files:
        return "Docker / DevOps"

    if ".git" in lower_dirs:
        return "Git project"

    if "src" in lower_dirs:
        return "Source project"

    return "Unknown"


def make_unique_key(projects, base_key, path):
    key = base_key

    if key not in projects:
        return key

    if projects[key].get("path", "").lower() == path.lower():
        return key

    counter = 2

    while f"{base_key}{counter}" in projects:
        counter += 1

    return f"{base_key}{counter}"


def get_project_score(root, dirs, files):
    score = 0
    lower_dirs = {d.lower() for d in dirs}
    lower_files = {f.lower() for f in files}
    present = lower_dirs | lower_files

    for marker in STRONG_PROJECT_MARKERS:
        if marker.lower() in present:
            score += 3

    for marker in PROJECT_MARKERS:
        if marker.lower() in present:
            score += 1

    if "src" in lower_dirs:
        score += 1

    if "backend" in lower_dirs or "frontend" in lower_dirs:
        score += 1

    path_parts = root.lower().replace("\\", "/").split("/")

    for part in path_parts:
        if part in PREFERRED_ROOT_NAMES:
            score += 1

    return score


def scan_root(root, projects, start_time, max_seconds):
    for current_root, dirs, files in os.walk(root, topdown=True):
        if time.time() - start_time > max_seconds:
            return

        if should_skip_path(current_root):
            dirs[:] = []
            continue

        dirs[:] = [
            d for d in dirs
            if d.lower() not in SKIP_DIRS
        ]

        try:
            if is_project_folder(dirs, files):
                name = os.path.basename(current_root)

                if not name:
                    continue

                base_key = normalize_name(name)
                key = make_unique_key(projects, base_key, current_root)

                aliases = project_aliases(name, current_root)
                project_type = get_project_type(dirs, files)
                project_score = get_project_score(current_root, dirs, files)

                projects[key] = {
                    "name": name,
                    "path": current_root,
                    "drive": os.path.splitdrive(current_root)[0].upper(),
                    "type": project_type,
                    "aliases": aliases,
                    "search_keys": aliases,
                    "score": project_score,
                    "strong": is_strong_project_folder(dirs, files),
                    "indexed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

                # If this is a strong project root, do not go deeper.
                # This avoids indexing node_modules/build/subprojects as separate projects.
                if is_strong_project_folder(dirs, files):
                    dirs[:] = []

        except PermissionError:
            continue
        except Exception:
            continue


def build_project_index(max_seconds=180):
    projects = {}
    roots = get_scan_roots()

    print("Scanning project roots:")

    for root in roots:
        print(" -", root)

    start_time = time.time()

    for root in roots:
        if time.time() - start_time > max_seconds:
            print("Project scan timeout reached.")
            break

        scan_root(root, projects, start_time, max_seconds)

    # Prefer existing paths and stronger project markers
    projects = dict(
        sorted(
            projects.items(),
            key=lambda item: (
                -item[1].get("score", 0),
                item[1].get("name", "").lower()
            )
        )
    )

    with open(
        INDEX_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            projects,
            f,
            indent=4,
            ensure_ascii=False
        )

    print(f"Indexed {len(projects)} projects.")
    print(f"Saved to: {INDEX_FILE}")


if __name__ == "__main__":
    build_project_index()
