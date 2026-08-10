import os
import re
import difflib
import string
import shutil

from llm_local import ask_llm

from tools import (
    load_projects,
    find_project,
    normalize_name,
    project_match_score
)


TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".scss", ".sass",
    ".json", ".md", ".txt", ".yml", ".yaml",
    ".xml", ".csv", ".sql", ".env",
    ".toml", ".ini", ".cfg",
    ".java", ".kt", ".kts",
    ".cs", ".cpp", ".c", ".h", ".hpp",
    ".php", ".go", ".rs",
    ".sh", ".bat", ".ps1",
}

SKIP_DIRS = {
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
    ".gradle",
    "site-packages",
}

MAX_READ_CHARS = 14000

LAST_FILE_MATCHES = []


# ==========================
# BASIC HELPERS
# ==========================
def normalize_path_text(text):
    return (
        str(text)
        .replace("\\", "/")
        .replace("//", "/")
        .strip()
        .lower()
    )


def clean_path(text):
    text = str(text).strip()
    text = text.strip('"').strip("'")
    text = os.path.expandvars(text)
    text = os.path.expanduser(text)
    return text


def is_direct_path(text):
    text = clean_path(text)

    if os.path.isabs(text):
        return True

    if ":" in text[:4]:
        return True

    if text.startswith("\\\\"):
        return True

    return False


def parse_file_project_query(query):
    """
    Supports:
    auth.py
    routes/auth.py
    auth.py from cyber
    routes/auth.py from CyberShield AI
    E:\\path\\file.py
    """

    text = query.strip()
    lower = text.lower()

    if " from " in lower:
        index = lower.rfind(" from ")

        file_query = text[:index].strip()
        project_query = text[index + len(" from "):].strip()

        return file_query, project_query

    return text, None


def safe_read_file(path, max_chars=MAX_READ_CHARS):
    path = clean_path(path)

    if not os.path.exists(path):
        return None, f"File not found on disk: {path}"

    if not os.path.isfile(path):
        return None, f"Path is not a file: {path}"

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
            errors="ignore"
        ) as f:
            return f.read(max_chars), None

    except Exception as e:
        return None, f"Could not read file: {e}"


def should_skip_dir(dirname):
    return dirname.lower() in SKIP_DIRS


def is_readable_candidate(filename):
    ext = os.path.splitext(filename)[1].lower()

    if ext in TEXT_EXTENSIONS:
        return True

    # Allow extensionless scripts/config files.
    if "." not in filename:
        return True

    return False


# ==========================
# PROJECT SELECTION
# ==========================
def get_candidate_projects(project_query=None):
    projects = load_projects()

    if not projects:
        return [], "No projects found. Run refresh projects first."

    if project_query:
        project = find_project(project_query)

        if not project:
            return [], f"Project not found: {project_query}"

        return [project], None

    result = []

    for project in projects.values():
        if not isinstance(project, dict):
            continue

        path = project.get("path", "")

        if path and os.path.exists(path):
            result.append(project)

    return result, None


# ==========================
# FILE MATCHING
# ==========================
def score_file_match(file_query, relative_path, filename):
    query_path = normalize_path_text(file_query)
    rel = normalize_path_text(relative_path)
    name = normalize_path_text(filename)

    query_norm = normalize_name(file_query)
    rel_norm = normalize_name(relative_path)
    name_norm = normalize_name(filename)

    if query_path == rel:
        return 1.00

    if query_path == name:
        return 0.98

    if query_norm == rel_norm:
        return 1.00

    if query_norm == name_norm:
        return 0.98

    if query_path in rel and len(query_path) >= 3:
        return 0.90

    if query_norm in rel_norm and len(query_norm) >= 3:
        return 0.86

    if query_norm in name_norm and len(query_norm) >= 3:
        return 0.82

    fuzzy_name = difflib.SequenceMatcher(
        None,
        query_norm,
        name_norm
    ).ratio()

    fuzzy_rel = difflib.SequenceMatcher(
        None,
        query_norm,
        rel_norm
    ).ratio()

    return max(fuzzy_name, fuzzy_rel)


def scan_project_for_file(project, file_query):
    project_path = project.get("path", "")

    matches = []

    if not project_path or not os.path.exists(project_path):
        return matches

    for root, dirs, files in os.walk(project_path, topdown=True):
        dirs[:] = [
            d for d in dirs
            if not should_skip_dir(d)
        ]

        for filename in files:
            if not is_readable_candidate(filename):
                continue

            full_path = os.path.join(root, filename)
            relative_path = os.path.relpath(full_path, project_path)

            score = score_file_match(
                file_query,
                relative_path,
                filename
            )

            if score >= 0.62:
                matches.append({
                    "score": score,
                    "project": project,
                    "project_name": project.get("name", "Unknown"),
                    "project_path": project_path,
                    "relative_path": relative_path,
                    "full_path": full_path,
                    "filename": filename,
                })

    return matches


def find_universal_file_matches(query, limit=50):
    file_query, project_query = parse_file_project_query(query)

    # Direct disk path
    if is_direct_path(file_query):
        path = clean_path(file_query)

        if os.path.exists(path) and os.path.isfile(path):
            return [{
                "score": 1.0,
                "project": {
                    "name": "Direct path",
                    "path": os.path.dirname(path)
                },
                "project_name": "Direct path",
                "project_path": os.path.dirname(path),
                "relative_path": path,
                "full_path": path,
                "filename": os.path.basename(path),
            }], None

        return [], f"File not found on disk: {path}"

    projects, error = get_candidate_projects(project_query)

    if error:
        return [], error

    matches = []

    for project in projects:
        matches.extend(
            scan_project_for_file(
                project,
                file_query
            )
        )

    matches.sort(
        key=lambda item: (
            -item["score"],
            item["project_name"].lower(),
            item["relative_path"].lower()
        )
    )

    return matches[:limit], None


def select_best_match(query):
    matches, error = find_universal_file_matches(query)

    if error:
        return None, error

    if not matches:
        return None, f"File not found: {query}"

    if len(matches) == 1:
        return matches[0], None

    top = matches[0]
    second = matches[1]

    # If the best match is clearly better, use it.
    if top["score"] >= 0.95 and top["score"] > second["score"]:
        return top, None

    # Exact same file can appear multiple times in duplicate projects.
    # Ask user to choose if there are multiple strong candidates.
    preview = []

    for item in matches[:15]:
        preview.append(
            f"{item['project_name']} -> {item['relative_path']} "
            f"({item['full_path']})"
        )

    return None, (
        "Multiple files matched. Use a more specific command:\n"
        "open file <file> from <project>\n"
        "read file <file> from <project>\n"
        "or use a full path.\n\n"
        + "\n".join(preview)
    )


def select_best_match_force(query):
    """
    Always selects the highest scoring match.
    Used by commands like:
    open best auth.py from cyber
    read best auth.py from cyber
    """

    matches, error = find_universal_file_matches(query)

    if error:
        return None, error

    if not matches:
        return None, f"File not found: {query}"

    return matches[0], None


def remember_last_matches(matches):
    global LAST_FILE_MATCHES

    LAST_FILE_MATCHES = matches or []


def get_last_match(number):
    if not LAST_FILE_MATCHES:
        return None, (
            "No ranked file matches stored yet.\n"
            "Run: rank file <file>\n"
            "or: find file <file>"
        )

    try:
        index = int(str(number).strip().replace("#", "")) - 1
    except Exception:
        return None, "Invalid file number. Example: open file #2"

    if index < 0 or index >= len(LAST_FILE_MATCHES):
        return None, (
            f"File number out of range. "
            f"Available: 1 - {len(LAST_FILE_MATCHES)}"
        )

    return LAST_FILE_MATCHES[index], None


def format_ranked_matches(query, matches):
    output = [
        f"Ranked file matches for '{query}': {len(matches)}"
    ]

    for index, item in enumerate(matches[:50], start=1):
        output.append(
            f"{index}. {item['project_name']} -> "
            f"{item['relative_path']} "
            f"[score {item['score']:.2f}]"
        )

    if len(matches) > 50:
        output.append(
            f"... and {len(matches) - 50} more"
        )

    output.append(
        "\nUse one of these commands:\n"
        "open file #<number>\n"
        "read file #<number>\n"
        "review file #<number>\n"
        "security review file #<number>"
    )

    return "\n".join(output)


def select_match_by_number(query):
    text = str(query).strip()

    if text.startswith("#"):
        text = text[1:].strip()

    return get_last_match(text)


def format_match(match):
    return (
        f"{match['project_name']} -> "
        f"{match['relative_path']}"
    )


# ==========================
# USER COMMAND FUNCTIONS
# ==========================
def find_universal_file(query):
    matches, error = find_universal_file_matches(query)

    if error:
        return error

    if not matches:
        remember_last_matches([])
        return f"No file matched: {query}"

    remember_last_matches(matches)

    output = [
        f"File matches for '{query}': {len(matches)}"
    ]

    for index, item in enumerate(matches[:50], start=1):
        output.append(
            f"{index}. {item['project_name']} -> "
            f"{item['relative_path']} "
            f"[score {item['score']:.2f}]"
        )

    if len(matches) > 50:
        output.append(
            f"... and {len(matches) - 50} more"
        )

    output.append(
        "\nTip: use open file #<number> or read file #<number>."
    )

    return "\n".join(output)


def rank_universal_file(query):
    matches, error = find_universal_file_matches(query)

    if error:
        return error

    if not matches:
        remember_last_matches([])
        return f"No file matched: {query}"

    remember_last_matches(matches)

    return format_ranked_matches(query, matches)


def open_universal_file(query):
    if str(query).strip().startswith("#"):
        match, error = select_match_by_number(query)
    else:
        match, error = select_best_match(query)

    if error:
        return error

    path = match["full_path"]

    try:
        os.startfile(path)

        return (
            "Opening file:\n"
            f"{match['project_name']} -> {match['relative_path']}\n"
            f"Score: {match['score']:.2f}"
        )

    except Exception as e:
        return f"Could not open file: {e}"


def read_universal_file(query):
    if str(query).strip().startswith("#"):
        match, error = select_match_by_number(query)
    else:
        match, error = select_best_match(query)

    if error:
        return error

    content, read_error = safe_read_file(match["full_path"])

    if read_error:
        return read_error

    return (
        f"Project: {match['project_name']}\n"
        f"File: {match['relative_path']}\n"
        f"Path: {match['full_path']}\n"
        f"Score: {match['score']:.2f}\n\n"
        f"{content}"
    )


def open_best_universal_file(query):
    match, error = select_best_match_force(query)

    if error:
        return error

    path = match["full_path"]

    try:
        os.startfile(path)

        return (
            "Opening best file match:\n"
            f"{format_match(match)}\n"
            f"Score: {match['score']:.2f}"
        )

    except Exception as e:
        return f"Could not open file: {e}"


def read_best_universal_file(query):
    match, error = select_best_match_force(query)

    if error:
        return error

    content, read_error = safe_read_file(match["full_path"])

    if read_error:
        return read_error

    return (
        "Best file match selected:\n"
        f"Project: {match['project_name']}\n"
        f"File: {match['relative_path']}\n"
        f"Path: {match['full_path']}\n"
        f"Score: {match['score']:.2f}\n\n"
        f"{content}"
    )


def analyze_best_universal_file(query):
    match, error = select_best_match_force(query)

    if error:
        return error

    return analyze_universal_file(
        f"{match['relative_path']} from {match['project_name']}"
    )


def review_best_universal_file(query):
    match, error = select_best_match_force(query)

    if error:
        return error

    return review_universal_file(
        f"{match['relative_path']} from {match['project_name']}"
    )


def security_review_best_universal_file(query):
    match, error = select_best_match_force(query)

    if error:
        return error

    return security_review_universal_file(
        f"{match['relative_path']} from {match['project_name']}"
    )


def build_file_prompt(query, role, task):
    if str(query).strip().startswith("#"):
        match, error = select_match_by_number(query)
    else:
        match, error = select_best_match(query)

    if error:
        return None, error

    content, read_error = safe_read_file(match["full_path"])

    if read_error:
        return None, read_error

    prompt = f"""
You are JARVIS, {role}.

IMPORTANT:
- Use ONLY the code below.
- Do NOT invent missing files, frameworks, APIs, databases, or features.
- If something is not visible in the file, say: "Not visible in this file."
- Be practical and specific.

Project:
{match['project_name']}

File:
{match['relative_path']}

Path:
{match['full_path']}

Code:
{content}

Task:
{task}
"""

    return prompt, None


def analyze_universal_file(query):
    prompt, error = build_file_prompt(
        query,
        "a senior software engineer and cybersecurity reviewer",
        """
Return:
1. File purpose
2. Code quality score from 1 to 10
3. Security issues
4. Performance issues
5. Bugs or risky logic
6. Maintainability issues
7. Concrete improvements
8. Final recommendation
"""
    )

    if error:
        return error

    return ask_llm(prompt)


def review_universal_file(query):
    prompt, error = build_file_prompt(
        query,
        "a strict code reviewer",
        """
Return:
1. Main problems
2. Bugs
3. Security risks
4. Bad practices
5. Refactoring suggestions
6. Priority fixes
"""
    )

    if error:
        return error

    return ask_llm(prompt)


def improve_universal_file(query):
    prompt, error = build_file_prompt(
        query,
        "a senior developer",
        """
Improve this file without changing its core behavior.

Return:
1. Main weaknesses
2. Better approach
3. Improved code if possible
4. Explanation of changes
5. Any risks
"""
    )

    if error:
        return error

    return ask_llm(prompt)


def optimize_universal_file(query):
    prompt, error = build_file_prompt(
        query,
        "a performance-focused software engineer",
        """
Return:
1. Performance problems
2. Memory concerns
3. Complexity issues
4. Optimized snippets
5. Risks of optimization
6. Final recommendation
"""
    )

    if error:
        return error

    return ask_llm(prompt)


def security_review_universal_file(query):
    prompt, error = build_file_prompt(
        query,
        "a cybersecurity code reviewer",
        """
Return:
1. Security risk level: Low / Medium / High
2. Vulnerabilities found
3. Authentication/authorization issues
4. Input validation issues
5. Secret/key handling issues
6. Logging/privacy issues
7. Concrete fixes
8. Final recommendation
"""
    )

    if error:
        return error

    return ask_llm(prompt)


# ==========================
# NUMBERED MATCH ALIASES
# ==========================
def open_numbered_file(number):
    return open_universal_file(f"#{number}")


def read_numbered_file(number):
    return read_universal_file(f"#{number}")


def analyze_numbered_file(number):
    return analyze_universal_file(f"#{number}")


def review_numbered_file(number):
    return review_universal_file(f"#{number}")


def security_review_numbered_file(number):
    return security_review_universal_file(f"#{number}")


def improve_numbered_file(number):
    return improve_universal_file(f"#{number}")


def optimize_numbered_file(number):
    return optimize_universal_file(f"#{number}")


# ==========================================================
# UNIVERSAL FILE RESOLVER UPGRADE
# Strict resolver for files/folders across all drives.
# Overrides selected functions above.
# ==========================================================

SYSTEM_SKIP_DIRS = {
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
    ".gradle",
    "site-packages",
}

PROJECT_MARKERS = {
    ".git",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "vite.config.js",
    "next.config.js",
    "angular.json",
    "composer.json",
    "pom.xml",
    "build.gradle",
    ".csproj",
    ".sln",
}

COMMON_USER_FOLDERS = {
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

COMMON_PROJECT_ALIASES = {
    "cyber": [
        "CyberShield_AI_Enterprise_Hardened_Enhanced",
        "CyberShield AI",
        "Cyber Security App",
        "CyberShield",
    ],
    "cyber shield": [
        "CyberShield_AI_Enterprise_Hardened_Enhanced",
        "CyberShield AI",
        "Cyber Security App",
        "CyberShield",
    ],
    "cybershield": [
        "CyberShield_AI_Enterprise_Hardened_Enhanced",
        "CyberShield AI",
        "Cyber Security App",
        "CyberShield",
    ],
    "jarvis": [
        "J.A.R.V.I.S",
        "JARVIS",
        "Jarvis",
    ],
    "jervis": [
        "J.A.R.V.I.S",
        "JARVIS",
        "Jarvis",
    ],
}


def get_available_drives():
    drives = []

    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"

        if os.path.exists(drive):
            drives.append(drive)

    return drives


def normalize_search_text(text):
    text = str(text).strip().strip('"').strip("'")
    text = text.replace("\\", "/")
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def normalize_project_query(text):
    lower = normalize_search_text(text)

    for key, aliases in COMMON_PROJECT_ALIASES.items():
        if key in lower:
            return aliases

    return [text]


def get_user_folder(name):
    lower = normalize_search_text(name)
    folder = COMMON_USER_FOLDERS.get(lower)

    if not folder:
        return None

    path = os.path.join(os.path.expanduser("~"), folder)

    if os.path.exists(path):
        return path

    return None


def should_skip_dir(dirname):
    return dirname.lower() in SYSTEM_SKIP_DIRS


def is_project_root(root, dirs, files):
    present = set(dirs) | set(files)
    return bool(present & PROJECT_MARKERS)


def universal_score(query, candidate):
    query = normalize_search_text(query)
    candidate = normalize_search_text(candidate)

    if not query or not candidate:
        return 0.0

    if query == candidate:
        return 1.0

    if query in candidate:
        return 0.92

    query_compact = normalize_name(query)
    candidate_compact = normalize_name(candidate)

    if query_compact == candidate_compact:
        return 1.0

    if query_compact and query_compact in candidate_compact:
        return 0.90

    query_words = set(query.replace("_", " ").replace("-", " ").split())
    candidate_words = set(candidate.replace("_", " ").replace("-", " ").split())

    word_score = 0.0

    if query_words:
        common = len(query_words & candidate_words)
        word_score = common / len(query_words)

    fuzzy = difflib.SequenceMatcher(
        None,
        query_compact,
        candidate_compact
    ).ratio()

    return max(word_score * 0.82, fuzzy)


def scan_all_drives_for_path(query, want_file=False, want_folder=False, max_seconds=45):
    query = str(query).strip()

    if not query:
        return []

    direct = clean_path(query)

    if os.path.exists(direct):
        if want_file and os.path.isfile(direct):
            return [direct]
        if want_folder and os.path.isdir(direct):
            return [direct]
        if not want_file and not want_folder:
            return [direct]

    known = get_user_folder(query)

    if known and not want_file:
        return [known]

    roots = [
        os.getcwd(),
        os.path.expanduser("~"),
    ]
    roots.extend(get_available_drives())

    results = []
    start_time = __import__("time").time()

    for root_dir in roots:
        if __import__("time").time() - start_time > max_seconds:
            break

        if not os.path.exists(root_dir):
            continue

        try:
            for root, dirs, files in os.walk(root_dir, topdown=True):
                if __import__("time").time() - start_time > max_seconds:
                    break

                dirs[:] = [
                    d for d in dirs
                    if not should_skip_dir(d)
                ]

                if not want_file:
                    folder_score = universal_score(
                        query,
                        os.path.basename(root)
                    )

                    if folder_score >= 0.55:
                        results.append({
                            "score": folder_score,
                            "path": root,
                            "type": "folder",
                            "name": os.path.basename(root),
                        })

                if not want_folder:
                    for filename in files:
                        file_score = universal_score(query, filename)

                        if file_score >= 0.55:
                            full_path = os.path.join(root, filename)
                            results.append({
                                "score": file_score,
                                "path": full_path,
                                "type": "file",
                                "name": filename,
                            })

        except Exception:
            continue

    results.sort(
        key=lambda item: (
            -item["score"],
            item["type"],
            item["path"].lower()
        )
    )

    return results


def scan_all_drives_for_project(project_query, max_seconds=45):
    aliases = normalize_project_query(project_query)

    roots = [
        os.getcwd(),
        os.path.expanduser("~"),
    ]
    roots.extend(get_available_drives())

    results = []
    start_time = __import__("time").time()

    for root_dir in roots:
        if __import__("time").time() - start_time > max_seconds:
            break

        if not os.path.exists(root_dir):
            continue

        try:
            for root, dirs, files in os.walk(root_dir, topdown=True):
                if __import__("time").time() - start_time > max_seconds:
                    break

                dirs[:] = [
                    d for d in dirs
                    if not should_skip_dir(d)
                ]

                if not is_project_root(root, dirs, files):
                    continue

                base = os.path.basename(root)
                full = root

                best_score = 0.0

                for alias in aliases:
                    best_score = max(
                        best_score,
                        universal_score(alias, base),
                        universal_score(alias, full)
                    )

                if best_score >= 0.50:
                    results.append({
                        "score": best_score,
                        "project": {
                            "name": base,
                            "path": root,
                            "type": "Detected"
                        },
                        "project_name": base,
                        "project_path": root,
                    })

        except Exception:
            continue

    results.sort(
        key=lambda item: (
            -item["score"],
            item["project_name"].lower()
        )
    )

    return results


def get_candidate_projects(project_query=None):
    projects = load_projects()

    result = []

    if projects:
        if project_query:
            project = find_project(project_query)

            if project and isinstance(project, dict):
                path = project.get("path", "")

                if path and os.path.exists(path):
                    return [project], None

        else:
            for project in projects.values():
                if not isinstance(project, dict):
                    continue

                path = project.get("path", "")

                if path and os.path.exists(path):
                    result.append(project)

    if project_query:
        detected = scan_all_drives_for_project(project_query)

        if detected:
            return [
                item["project"]
                for item in detected[:10]
            ], None

        return [], f"Project not found on current laptop/PC/stick/external drive: {project_query}"

    if result:
        return result, None

    detected = scan_all_drives_for_project("")

    if detected:
        return [
            item["project"]
            for item in detected[:50]
        ], None

    return [], "No projects found. Run refresh projects first or connect the drive/stick."


def find_universal_file_matches(query, limit=50):
    file_query, project_query = parse_file_project_query(query)

    if is_direct_path(file_query):
        path = clean_path(file_query)

        if os.path.exists(path) and os.path.isfile(path):
            return [{
                "score": 1.0,
                "project": {
                    "name": "Direct path",
                    "path": os.path.dirname(path)
                },
                "project_name": "Direct path",
                "project_path": os.path.dirname(path),
                "relative_path": path,
                "full_path": path,
                "filename": os.path.basename(path),
            }], None

        return [], f"File not found on disk: {path}"

    projects, error = get_candidate_projects(project_query)

    matches = []

    if not error:
        for project in projects:
            matches.extend(
                scan_project_for_file(
                    project,
                    file_query
                )
            )

    # Fallback: if no project match or no results, search all drives.
    if not matches:
        global_matches = scan_all_drives_for_path(
            file_query,
            want_file=True
        )

        for item in global_matches[:limit]:
            path = item["path"]
            project_path = os.path.dirname(path)

            matches.append({
                "score": item["score"],
                "project": {
                    "name": "Global search",
                    "path": project_path
                },
                "project_name": "Global search",
                "project_path": project_path,
                "relative_path": path,
                "full_path": path,
                "filename": os.path.basename(path),
            })

    if not matches and error:
        return [], error

    matches.sort(
        key=lambda item: (
            -item["score"],
            item["project_name"].lower(),
            item["relative_path"].lower()
        )
    )

    return matches[:limit], None


def open_universal_folder(query):
    matches = scan_all_drives_for_path(
        query,
        want_folder=True
    )

    if not matches:
        return f"Folder not found: {query}"

    best = matches[0]
    path = best["path"]

    try:
        os.startfile(path)

        return (
            "Opening folder:\n"
            f"{path}\n"
            f"Score: {best['score']:.2f}"
        )

    except Exception as e:
        return f"Could not open folder: {e}"


def rank_universal_folder(query):
    matches = scan_all_drives_for_path(
        query,
        want_folder=True
    )

    if not matches:
        return f"No folder matched: {query}"

    output = [
        f"Ranked folder matches for '{query}': {len(matches)}"
    ]

    for index, item in enumerate(matches[:50], start=1):
        output.append(
            f"{index}. {item['path']} [score {item['score']:.2f}]"
        )

    return "\n".join(output)


def open_project_folder_universal(project_query):
    projects, error = get_candidate_projects(project_query)

    if error:
        return error

    if not projects:
        return f"Project not found: {project_query}"

    project = projects[0]
    path = project.get("path", "")

    if path and os.path.exists(path):
        try:
            os.startfile(path)
            return f"Opening project folder: {project.get('name', project_query)} -> {path}"
        except Exception as e:
            return f"Could not open project folder: {e}"

    return f"Project path does not exist anymore: {path}"


def safe_preview_file(query, chars=2500):
    match, error = select_best_match_force(query)

    if error:
        return error

    content, read_error = safe_read_file(
        match["full_path"],
        max_chars=chars
    )

    if read_error:
        return read_error

    return (
        "Safe preview only. No changes made.\n"
        f"Project: {match['project_name']}\n"
        f"File: {match['relative_path']}\n"
        f"Path: {match['full_path']}\n"
        f"Score: {match['score']:.2f}\n\n"
        f"{content}"
    )
