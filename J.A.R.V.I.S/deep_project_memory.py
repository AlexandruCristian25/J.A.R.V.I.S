import os
import json
import difflib
from datetime import datetime

from llm_local import ask_llm


MEMORY_DIR = "memory"
DEEP_PROJECT_FILE = os.path.join(
    MEMORY_DIR,
    "deep_projects_db.json"
)


CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".scss", ".json",
    ".md", ".txt", ".env", ".yml", ".yaml",
    ".ini", ".cfg", ".toml", ".xml",
    ".java", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".php", ".go", ".rs", ".sql",
    ".bat", ".ps1", ".sh"
}


SKIP_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    "jarvis-env",
    "__pycache__",
    ".git",
    "dist",
    "build",
    ".next",
    ".idea",
    ".vscode",
    ".cache",
    "site-packages"
}


MAX_FILES = 80
MAX_CHARS_PER_FILE = 4000


# ==========================
# NORMALIZE / MATCHING
# ==========================
def normalize_name(name):

    return "".join(
        ch for ch in name.lower()
        if ch.isalnum()
    )


def project_aliases(name):

    normalized = normalize_name(name)

    aliases = {
        normalized,
        normalize_name(name.replace("_", " ")),
        normalize_name(name.replace("-", " ")),
    }

    words = (
        name.replace("_", " ")
        .replace("-", " ")
        .split()
    )

    if words:
        aliases.add(
            normalize_name(" ".join(words))
        )

    return aliases


def project_match_score(
    stored_name,
    stored_path,
    query_name,
    query_path=None
):
    """
    Returns a score used to decide if two remembered projects
    represent the same real project.
    """

    stored_aliases = project_aliases(stored_name)
    stored_aliases.add(normalize_name(stored_path))

    query_aliases = project_aliases(query_name)

    if query_path:
        query_aliases.add(normalize_name(query_path))

    # Exact/partial alias match
    for q in query_aliases:
        for s in stored_aliases:
            if q == s:
                return 1.0

            if q in s or s in q:
                return 0.90

    # Fuzzy match
    best_score = 0

    for q in query_aliases:
        for s in stored_aliases:
            score = difflib.SequenceMatcher(
                None,
                q,
                s
            ).ratio()

            if score > best_score:
                best_score = score

    return best_score


def is_same_project(
    stored_item,
    project_name,
    project_path=None
):
    stored_name = stored_item.get(
        "name",
        ""
    )

    stored_path = stored_item.get(
        "path",
        ""
    )

    score = project_match_score(
        stored_name,
        stored_path,
        project_name,
        project_path
    )

    return score >= 0.75


def remove_old_project_entries(
    data,
    project_name,
    project_path=None
):
    """
    Removes only the old memories that refer to the same project.
    Other projects are kept untouched.
    """

    cleaned = []

    removed_count = 0

    for item in data:

        if is_same_project(
            item,
            project_name,
            project_path
        ):
            removed_count += 1
            continue

        cleaned.append(item)

    return cleaned, removed_count




def find_deep_project(project_name):

    data = load_deep_projects()

    if not data:
        return None

    query = normalize_name(project_name)

    matches = []

    # 1. Exact / alias / partial match
    for item in reversed(data):

        name = item.get("name", "")
        path = item.get("path", "")

        aliases = project_aliases(name)
        aliases.add(normalize_name(path))

        matched = False
        score = 0

        if query in aliases:
            matched = True
            score = 1.0

        if not matched:
            for alias in aliases:
                if query in alias or alias in query:
                    matched = True
                    score = 0.90
                    break

        if matched:
            # Prefer entries whose path still exists on disk.
            path_exists_bonus = 0.20 if os.path.exists(path) else 0

            matches.append(
                (
                    score + path_exists_bonus,
                    item
                )
            )

    if matches:
        matches.sort(
            key=lambda x: x[0],
            reverse=True
        )

        return matches[0][1]

    # 2. Smart fuzzy match
    best_item = None
    best_score = 0

    for item in reversed(data):

        name = item.get("name", "")
        path = item.get("path", "")

        candidates = list(project_aliases(name))
        candidates.append(normalize_name(path))

        for candidate in candidates:

            score = difflib.SequenceMatcher(
                None,
                query,
                candidate
            ).ratio()

            if os.path.exists(path):
                score += 0.05

            if score > best_score:
                best_score = score
                best_item = item

    if best_item and best_score >= 0.55:
        return best_item

    return None


def split_project_and_keyword(query):

    data = load_deep_projects()

    if not data:
        return None, query.strip()

    query = query.strip()

    best_project = None
    best_name = ""

    for item in data:

        name = item.get("name", "")

        possible_names = {
            name,
            name.replace("_", " "),
            name.replace("-", " "),
        }

        for possible in possible_names:

            if query.lower().startswith(
                possible.lower() + " "
            ):
                if len(possible) > len(best_name):
                    best_name = possible
                    best_project = item

    if best_project:

        keyword = query[len(best_name):].strip()

        return best_project, keyword

    # Fallback: if first words roughly match a project, use it
    words = query.split()

    for i in range(
        min(len(words), 6),
        0,
        -1
    ):

        candidate = " ".join(words[:i])
        project = find_deep_project(candidate)

        if project:
            keyword = " ".join(words[i:]).strip()

            if keyword:
                return project, keyword

    return None, query


# ==========================
# LOAD / SAVE
# ==========================
def load_deep_projects():

    if not os.path.exists(DEEP_PROJECT_FILE):
        return []

    try:
        with open(
            DEEP_PROJECT_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return []


def save_deep_projects(data):

    os.makedirs(
        MEMORY_DIR,
        exist_ok=True
    )

    with open(
        DEEP_PROJECT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )


# ==========================
# TECH STACK DETECTION
# ==========================
def detect_tech_stack(files):

    text = " ".join(
        item["relative_path"].lower()
        + " "
        + item["content"].lower()[:1000]
        for item in files
    )

    stack = []

    checks = {
        "Python": ["import flask", "def ", ".py"],
        "Flask": ["from flask", "flask(", "app.route", "@app.route"],
        "FastAPI": ["fastapi", "from fastapi", "apirouter"],
        "React": ["react", "jsx", "tsx", "usestate", "useeffect"],
        "Next.js": ["next.config", "next/router", "next/navigation"],
        "Angular": ["angular.json", "@angular", "ngmodule"],
        "Node.js": ["express", "package.json", "node_modules"],
        "Express": ["express()", "app.get(", "app.post(", "router.get("],
        "TypeScript": [".ts", ".tsx", "typescript"],
        "JavaScript": [".js", ".jsx"],
        "HTML": ["<html", ".html"],
        "CSS": [".css", ".scss"],
        "SQLite": ["sqlite", ".db"],
        "SQLAlchemy": ["sqlalchemy"],
        "MongoDB": ["mongodb", "mongoose"],
        "JWT": ["jwt", "jsonwebtoken"],
        "Docker": ["dockerfile", "docker-compose"],
        "Tailwind": ["tailwind"],
        "Vite": ["vite.config"],
        "Jest": ["jest", "describe(", "test("],
        "Pytest": ["pytest", "test_"],
    }

    for tech, keywords in checks.items():
        if any(k in text for k in keywords):
            stack.append(tech)

    return sorted(list(set(stack)))


# ==========================
# COLLECT FILES
# ==========================
def collect_project_files(project_path):

    collected = []

    project_path = os.path.abspath(
        project_path
    )

    for root, dirs, files in os.walk(project_path):

        dirs[:] = [
            d for d in dirs
            if d.lower() not in SKIP_DIRS
        ]

        for file in files:

            ext = os.path.splitext(file)[1].lower()

            if ext not in CODE_EXTENSIONS:
                continue

            full_path = os.path.join(
                root,
                file
            )

            relative_path = os.path.relpath(
                full_path,
                project_path
            )

            try:
                with open(
                    full_path,
                    "r",
                    encoding="utf-8",
                    errors="ignore"
                ) as f:
                    content = f.read(
                        MAX_CHARS_PER_FILE
                    )

                collected.append({
                    "relative_path": relative_path,
                    "extension": ext,
                    "content": content
                })

                if len(collected) >= MAX_FILES:
                    return collected

            except Exception:
                pass

    return collected


# ==========================
# SUMMARY
# ==========================
def summarize_project(
    project_name,
    project_path,
    files,
    tech_stack
):

    context = ""

    for item in files[:25]:

        context += (
            f"\n\nFILE: "
            f"{item['relative_path']}\n"
        )

        context += item["content"][:1500]

    prompt = f"""
You are JARVIS, a senior software engineer.

Create a technical memory profile for this project.

Project name:
{project_name}

Project path:
{project_path}

Detected tech stack:
{", ".join(tech_stack)}

Project files:
{context}

Return:

1. Short project purpose
2. Tech stack
3. Main folders and files
4. Important features
5. Security-relevant parts
6. APIs/routes if visible
7. Database usage if visible
8. Recommended next improvements

Be concise but useful.
"""

    return ask_llm(prompt)


# ==========================
# REMEMBER DEEP PROJECT
# ==========================
def remember_deep_project(
    project_name,
    project_path
):

    if not os.path.exists(project_path):
        return f"Project path not found: {project_path}"

    files = collect_project_files(
        project_path
    )

    if not files:
        return "No readable project files found."

    tech_stack = detect_tech_stack(
        files
    )

    summary = summarize_project(
        project_name,
        project_path,
        files,
        tech_stack
    )

    data = load_deep_projects()

    data, removed_count = remove_old_project_entries(
        data,
        project_name,
        project_path
    )

    data.append({
        "timestamp": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "name": project_name,
        "path": os.path.abspath(project_path),
        "aliases": list(project_aliases(project_name)),
        "tech_stack": tech_stack,
        "files_count": len(files),
        "files": [
            {
                "relative_path": item["relative_path"],
                "extension": item["extension"],
                "content": item["content"]
            }
            for item in files
        ],
        "summary": summary
    })

    save_deep_projects(data)

    return (
        f"Deep project remembered: {project_name}\n"
        f"Old entries replaced: {removed_count}\n"
        f"Files indexed: {len(files)}\n"
        f"Tech stack: {', '.join(tech_stack)}"
    )


# ==========================
# LIST / STATS
# ==========================
def list_deep_projects():

    data = load_deep_projects()

    if not data:
        return "No deep projects remembered."

    seen = set()
    output = []

    for item in reversed(data):

        name = item["name"]
        key = normalize_name(name)

        if key in seen:
            continue

        seen.add(key)

        output.append(
            f"{item['timestamp']} -> "
            f"{item['name']} "
            f"({item['files_count']} files)"
        )

    return "\n".join(output)


def deep_project_stats():

    data = load_deep_projects()

    if not data:
        return "Deep project memories: 0"

    unique = set(
        normalize_name(item.get("name", ""))
        for item in data
    )

    return (
        f"Deep project memories: {len(data)}\n"
        f"Unique projects: {len(unique)}"
    )


# ==========================
# GET PROJECT INFO
# ==========================
def get_deep_project(project_name):

    item = find_deep_project(project_name)

    if not item:
        return "Deep project not found."

    return (
        f"Project: {item['name']}\n"
        f"Timestamp: {item['timestamp']}\n"
        f"Path: {item['path']}\n"
        f"Files indexed: {item['files_count']}\n"
        f"Tech stack: {', '.join(item['tech_stack'])}\n\n"
        f"{item['summary']}"
    )


def show_project_files(project_name):

    item = find_deep_project(project_name)

    if not item:
        return "Project not found."

    files = [
        f["relative_path"]
        for f in item["files"]
    ]

    return "\n".join(files)


def show_project_tech_stack(project_name):

    item = find_deep_project(project_name)

    if not item:
        return "Project not found."

    if not item["tech_stack"]:
        return "No tech stack detected."

    return "\n".join(
        item["tech_stack"]
    )


# ==========================
# SEARCH CODE
# ==========================
def search_deep_project_code(
    query
):

    data = load_deep_projects()

    if not data:
        return "No deep projects remembered."

    project_filter, keyword = split_project_and_keyword(query)

    if not keyword:
        return "Missing search keyword."

    keyword_lower = keyword.lower()

    results = []

    projects = [project_filter] if project_filter else data

    for project in projects:

        for file in project["files"]:

            content = file["content"].lower()
            path = file["relative_path"]

            if (
                keyword_lower in content
                or keyword_lower in path.lower()
            ):
                results.append(
                    f"{project['name']} -> {path}"
                )

    if not results:
        return "No code match found."

    return "\n".join(results[-30:])


# ==========================
# STEP 9 - CONVERSATIONAL DEEP MEMORY
# ==========================
def last_deep_project():
    data = load_deep_projects()

    if not data:
        return "No deep projects remembered."

    item = data[-1]

    return (
        f"Last deep project:\n"
        f"{item['name']}\n"
        f"Files indexed: {item['files_count']}\n"
        f"Tech stack: {', '.join(item['tech_stack'])}"
    )


def continue_last_deep_project():
    data = load_deep_projects()

    if not data:
        return "No deep project found."

    item = data[-1]

    return (
        f"Continue project: {item['name']}\n\n"
        f"{item['summary'][:6000]}"
    )


def last_project_summary():
    data = load_deep_projects()

    if not data:
        return "No project summary found."

    return data[-1].get("summary", "No summary available.")


def compare_remembered_projects():
    data = load_deep_projects()

    if len(data) < 2:
        return "At least two remembered projects are required."

    output = []

    for item in reversed(data[-10:]):
        output.append(
            f"{item['name']} | "
            f"{item['files_count']} files | "
            f"{', '.join(item['tech_stack'])}"
        )

    return "\n".join(output)


def what_projects_do_you_remember():
    return list_deep_projects()


def what_was_i_working_on_last():
    return last_deep_project()


def resume_last_project():
    return continue_last_deep_project()

# ==========================
# STEP 10 - DEEP MEMORY INTEGRATION
# Project timeline / audit history / vulnerability history / evolution
# ==========================
PROJECT_EVENTS_FILE = os.path.join(
    MEMORY_DIR,
    "deep_project_events.json"
)


def load_deep_project_events():
    if not os.path.exists(PROJECT_EVENTS_FILE):
        return []

    try:
        with open(
            PROJECT_EVENTS_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return []


def save_deep_project_events(data):
    os.makedirs(
        MEMORY_DIR,
        exist_ok=True
    )

    with open(
        PROJECT_EVENTS_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )


def remember_project_event(
    project_name,
    event_type,
    title,
    content,
    tags=None,
    metadata=None
):
    if tags is None:
        tags = []

    if metadata is None:
        metadata = {}

    project = find_deep_project(project_name)

    if project:
        real_name = project.get("name", project_name)
        project_path = project.get("path", "")
    else:
        real_name = project_name
        project_path = ""

    data = load_deep_project_events()

    data.append({
        "timestamp": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "project": real_name,
        "project_path": project_path,
        "event_type": event_type,
        "title": title,
        "content": str(content),
        "tags": tags,
        "metadata": metadata
    })

    save_deep_project_events(data)

    return f"Deep project event remembered: {real_name} -> {title}"


def _event_matches_project(event, project_name):
    query = normalize_name(project_name)

    candidates = [
        event.get("project", ""),
        event.get("project_path", "")
    ]

    for candidate in candidates:
        normalized = normalize_name(candidate)

        if query and (
            query == normalized
            or query in normalized
            or normalized in query
        ):
            return True

    project = find_deep_project(project_name)

    if project:
        project_key = normalize_name(project.get("name", ""))

        if project_key and project_key == normalize_name(event.get("project", "")):
            return True

    return False


def get_project_events(project_name=None, event_type=None, limit=20):
    data = load_deep_project_events()

    if project_name:
        data = [
            event for event in data
            if _event_matches_project(event, project_name)
        ]

    if event_type:
        data = [
            event for event in data
            if event.get("event_type", "").lower() == event_type.lower()
        ]

    return data[-limit:]


def project_timeline(project_name, limit=30):
    events = get_project_events(
        project_name,
        limit=limit
    )

    if not events:
        return f"No timeline events found for project: {project_name}"

    output = [
        f"Project timeline: {project_name}",
        ""
    ]

    for event in events:
        output.append(
            f"- {event.get('timestamp', 'Unknown')} | "
            f"{event.get('event_type', 'event')} | "
            f"{event.get('title', '')}"
        )

    return "\n".join(output)


def audit_history(project_name=None, limit=20):
    events = get_project_events(
        project_name,
        event_type="audit",
        limit=limit
    )

    if not events:
        return "No audit history found."

    output = [
        "Audit history:"
    ]

    for event in events:
        output.append(
            f"- {event.get('timestamp', 'Unknown')} | "
            f"{event.get('project', 'Unknown')} | "
            f"{event.get('title', '')}"
        )

    return "\n".join(output)


def vulnerability_history(project_name=None, limit=20):
    data = load_deep_project_events()

    results = []

    for event in data:
        text = (
            event.get("title", "") + " " +
            event.get("content", "") + " " +
            " ".join(event.get("tags", []))
        ).lower()

        if project_name and not _event_matches_project(event, project_name):
            continue

        if (
            "vulnerab" in text
            or "security" in text
            or "risk" in text
            or "xss" in text
            or "sql injection" in text
            or "api key" in text
            or "password" in text
            or "secret" in text
        ):
            results.append(event)

    if not results:
        return "No vulnerability history found."

    output = [
        "Vulnerability history:"
    ]

    for event in results[-limit:]:
        output.append(
            f"- {event.get('timestamp', 'Unknown')} | "
            f"{event.get('project', 'Unknown')} | "
            f"{event.get('title', '')}"
        )

    return "\n".join(output)


def remembered_fixes(project_name=None, limit=20):
    data = load_deep_project_events()

    results = []

    for event in data:
        text = (
            event.get("title", "") + " " +
            event.get("content", "") + " " +
            " ".join(event.get("tags", []))
        ).lower()

        if project_name and not _event_matches_project(event, project_name):
            continue

        if (
            "fix" in text
            or "patch" in text
            or "improve" in text
            or "roadmap" in text
        ):
            results.append(event)

    if not results:
        return "No remembered fixes found."

    output = [
        "Remembered fixes / improvements:"
    ]

    for event in results[-limit:]:
        output.append(
            f"- {event.get('timestamp', 'Unknown')} | "
            f"{event.get('project', 'Unknown')} | "
            f"{event.get('title', '')}"
        )

    return "\n".join(output)


def project_evolution(project_name):
    project = find_deep_project(project_name)

    if not project:
        return f"Project not found in deep memory: {project_name}"

    timeline = project_timeline(
        project_name,
        limit=15
    )

    audits = audit_history(
        project_name,
        limit=10
    )

    vulnerabilities = vulnerability_history(
        project_name,
        limit=10
    )

    fixes = remembered_fixes(
        project_name,
        limit=10
    )

    return (
        f"Project evolution: {project.get('name', project_name)}\n"
        f"Path: {project.get('path', '')}\n"
        f"Files indexed: {project.get('files_count', 0)}\n"
        f"Tech stack: {', '.join(project.get('tech_stack', []))}\n\n"
        f"{timeline}\n\n"
        f"{audits}\n\n"
        f"{vulnerabilities}\n\n"
        f"{fixes}"
    )


def session_summary(limit=15):
    events = load_deep_project_events()

    if not events:
        return "No deep project session events found."

    output = [
        "Recent JARVIS engineering session summary:",
        ""
    ]

    for event in events[-limit:]:
        output.append(
            f"- {event.get('timestamp', 'Unknown')} | "
            f"{event.get('project', 'Unknown')} | "
            f"{event.get('event_type', 'event')} | "
            f"{event.get('title', '')}"
        )

    return "\n".join(output)


def continue_previous_session():
    events = load_deep_project_events()

    if not events:
        return continue_last_deep_project()

    last = events[-1]

    project_name = last.get("project", "Unknown")

    return (
        f"Continue previous session:\n"
        f"Project: {project_name}\n"
        f"Last event: {last.get('title', '')}\n"
        f"Timestamp: {last.get('timestamp', 'Unknown')}\n\n"
        f"Context:\n{last.get('content', '')[:6000]}\n\n"
        f"Suggested next commands:\n"
        f"- project evolution {project_name}\n"
        f"- autonomous improve {project_name}\n"
        f"- full security audit {project_name}"
    )


def last_20_audits():
    return audit_history(
        project_name=None,
        limit=20
    )


def last_vulnerabilities(project_name=None):
    return vulnerability_history(
        project_name=project_name,
        limit=20
    )


def last_improvements(project_name=None):
    return remembered_fixes(
        project_name=project_name,
        limit=20
    )

# ==========================
# STEP 17 - CROSS PROJECT LEARNING ENGINE
# Learns reusable patterns, repeated risks, tech habits, and portfolio standards.
# Safe analysis only. No automatic code changes.
# ==========================
def _latest_unique_deep_projects():
    data = load_deep_projects()

    latest = {}

    for item in data:
        name = item.get("name", "").strip()

        if not name:
            continue

        latest[normalize_name(name)] = item

    return list(latest.values())


def _all_project_text(project, max_chars_per_project=50000):
    chunks = [
        project.get("name", ""),
        project.get("path", ""),
        " ".join(project.get("tech_stack", [])),
        project.get("summary", "")
    ]

    total = 0

    for file in project.get("files", []):
        path = file.get("relative_path", "")
        content = file.get("content", "")

        if total >= max_chars_per_project:
            break

        piece = f"\nFILE: {path}\n{content[:2500]}"
        chunks.append(piece)
        total += len(piece)

    return "\n".join(chunks).lower()


def _project_has_any(project, keywords):
    text = _all_project_text(project)

    return any(
        keyword.lower() in text
        for keyword in keywords
    )


def _files_containing_keywords(project, keywords, limit=20):
    results = []

    for file in project.get("files", []):
        path = file.get("relative_path", "")
        content = file.get("content", "").lower()
        path_lower = path.lower()

        if any(keyword.lower() in content or keyword.lower() in path_lower for keyword in keywords):
            results.append(path)

        if len(results) >= limit:
            break

    return results


def cross_project_tech_patterns():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    tech_counter = {}
    project_lines = []

    for project in projects:
        stack = project.get("tech_stack", [])

        for tech in stack:
            tech_counter[tech] = tech_counter.get(tech, 0) + 1

        project_lines.append(
            f"- {project.get('name')} -> {', '.join(stack) if stack else 'No stack detected'}"
        )

    ranked = sorted(
        tech_counter.items(),
        key=lambda item: item[1],
        reverse=True
    )

    output = [
        "CROSS PROJECT TECH PATTERNS",
        "Mode: rule-based / based on remembered deep projects",
        "",
        f"Projects analyzed: {len(projects)}",
        "",
        "Technologies used most:"
    ]

    if ranked:
        for tech, count in ranked:
            output.append(f"- {tech}: {count} project(s)")
    else:
        output.append("- No technologies detected.")

    output.append("")
    output.append("Per-project stack:")
    output.extend(project_lines)

    return "\n".join(output)


def repeated_security_mistakes():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    checks = [
        (
            "Weak/default secrets",
            ["your-secret-key", "changeme", "changeme123", "password123", "secure123", "secret_key = \"secret"],
            "Move secrets to environment variables and rotate demo values."
        ),
        (
            "Hardcoded credentials or tokens",
            ["api_key", "apikey", "password =", "token =", "secret =", "access_token"],
            "Review all matches and avoid committing credentials."
        ),
        (
            "Debug mode / development config",
            ["debug=true", "debug = true", "app.run(debug", "vite --host"],
            "Disable debug mode in production and separate dev/prod config."
        ),
        (
            "Missing strong auth evidence",
            ["fake_users_db", "demo user", "test user"],
            "Replace demo users with persistent user storage and real auth flow."
        ),
        (
            "Upload/file handling risk",
            ["upload", "multipart", "formdata", "file"],
            "Validate file type, size, content, storage path, and logging."
        ),
        (
            "Logging/privacy risk",
            ["print(", "logger", "audit", "ip", "username", "email"],
            "Use structured logs and review personal data retention."
        ),
    ]

    output = [
        "REPEATED SECURITY MISTAKES",
        "Mode: heuristic cross-project scan / verify manually",
        ""
    ]

    found_any = False

    for title, keywords, recommendation in checks:
        affected = []

        for project in projects:
            files = _files_containing_keywords(project, keywords, limit=8)

            if files:
                affected.append(
                    (
                        project.get("name", "Unknown"),
                        files
                    )
                )

        if affected:
            found_any = True
            output.append(f"\n{title}")
            output.append(f"Recommendation: {recommendation}")

            for project_name, files in affected:
                output.append(f"- {project_name}:")
                for file in files[:8]:
                    output.append(f"  - {file}")

    if not found_any:
        output.append("No repeated security patterns detected by the current heuristic scan.")

    return "\n".join(output)


def repeated_architecture_mistakes():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    checks = [
        (
            "Mixed backend frameworks",
            ["from flask", "flask(", "fastapi", "apirouter"],
            "Verify if mixed Flask/FastAPI usage is intentional or legacy."
        ),
        (
            "Scattered configuration",
            [".env", "config", "settings", "api_url", "base_url", "localhost"],
            "Centralize configuration and document environment variables."
        ),
        (
            "Frontend/backend coupling",
            ["axios.", "fetch(", "http://127.0.0.1", "localhost"],
            "Centralize API clients and avoid hardcoded local URLs."
        ),
        (
            "Missing deployment structure",
            ["dockerfile", "docker-compose", ".github", "workflow"],
            "Standardize Docker/CI/deployment files across projects."
        ),
        (
            "Large single-file tendency",
            ["app.py", "main.py", "server.py"],
            "Split large entry files into routes, services, models, config, and utils."
        ),
    ]

    output = [
        "REPEATED ARCHITECTURE MISTAKES",
        "Mode: heuristic cross-project scan / verify manually",
        ""
    ]

    found_any = False

    for title, keywords, recommendation in checks:
        affected = []

        for project in projects:
            files = _files_containing_keywords(project, keywords, limit=10)

            if files:
                affected.append(
                    (
                        project.get("name", "Unknown"),
                        files
                    )
                )

        if affected:
            found_any = True
            output.append(f"\n{title}")
            output.append(f"Recommendation: {recommendation}")

            for project_name, files in affected:
                output.append(f"- {project_name}:")
                for file in files[:8]:
                    output.append(f"  - {file}")

    if not found_any:
        output.append("No repeated architecture patterns detected by the current heuristic scan.")

    return "\n".join(output)


def reusable_modules_across_projects():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    reusable_keywords = [
        "auth",
        "jwt",
        "token",
        "security",
        "logger",
        "audit",
        "backup",
        "config",
        "database",
        "db",
        "api",
        "service",
        "utils",
        "helpers",
        "validator",
        "scanner",
        "dashboard",
        "memory",
        "indexer",
    ]

    module_map = {}

    for project in projects:
        project_name = project.get("name", "Unknown")

        for file in project.get("files", []):
            path = file.get("relative_path", "")
            lower_path = path.lower()

            for keyword in reusable_keywords:
                if keyword in lower_path:
                    module_map.setdefault(keyword, []).append(
                        f"{project_name} -> {path}"
                    )

    output = [
        "REUSABLE MODULES ACROSS PROJECTS",
        "Mode: path-based heuristic / verify before extraction",
        ""
    ]

    found = False

    for keyword, paths in sorted(
        module_map.items(),
        key=lambda item: len(item[1]),
        reverse=True
    ):
        if len(paths) < 2:
            continue

        found = True
        output.append(f"\nReusable pattern: {keyword}")
        for path in paths[:15]:
            output.append(f"- {path}")

    if not found:
        output.append("No reusable module pattern repeated across at least two projects.")

    output.append("")
    output.append("Recommendation:")
    output.append("Extract reusable modules only after tests exist and behavior is stable.")

    return "\n".join(output)


def engineering_standards():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    tech = cross_project_tech_patterns()

    return (
        "JARVIS ENGINEERING STANDARDS\n"
        "Generated from remembered project patterns.\n\n"
        f"{tech}\n\n"
        "Recommended standards:\n"
        "1. Every project should have README.md with setup, run, test, and deployment instructions.\n"
        "2. Every project should have .env.example and should ignore real .env files.\n"
        "3. Secrets, API keys, JWT keys, and passwords must use environment variables.\n"
        "4. Every backend route should validate input and return safe errors.\n"
        "5. Authentication, authorization, upload validation, and logging should have tests.\n"
        "6. API base URLs should be centralized in one config/service file.\n"
        "7. Large app.py/main.py/server.py files should be split into routes/services/config/models.\n"
        "8. Every project should have a release checklist and production readiness review.\n"
        "9. Every project should be re-indexed in JARVIS after major changes.\n"
        "10. Before applying AI-generated code changes: create backup, review diff, run tests."
    )


def coding_standards():
    return (
        "JARVIS CODING STANDARDS\n\n"
        "Python:\n"
        "- Keep routes/controllers thin; move business logic into services.\n"
        "- Use environment variables for secrets and config.\n"
        "- Use structured logging instead of print-based production logs.\n"
        "- Validate user input at API boundaries.\n"
        "- Avoid broad exception swallowing without safe logging.\n\n"
        "JavaScript/TypeScript/React:\n"
        "- Centralize API calls in service modules.\n"
        "- Avoid hardcoded localhost URLs in components.\n"
        "- Keep components focused; move repeated logic into hooks/utilities.\n"
        "- Validate form input both client-side and server-side.\n"
        "- Use clear loading/error states for API calls.\n\n"
        "Security:\n"
        "- Never commit real secrets.\n"
        "- Use strong password hashing where user accounts exist.\n"
        "- Add JWT/session expiration and authorization checks.\n"
        "- Validate uploads by size, type, extension, and content where possible.\n"
        "- Review logs for personal/sensitive data.\n\n"
        "Testing:\n"
        "- Add tests around auth, permissions, uploads, critical routes, and project startup.\n"
        "- Run tests after every patch."
    )


def portfolio_best_practices():
    return (
        "PORTFOLIO BEST PRACTICES\n\n"
        "1. Keep every project runnable from a clear README.\n"
        "2. Add screenshots or demo GIFs for frontend projects.\n"
        "3. Add architecture diagrams for complex apps.\n"
        "4. Add security notes for cybersecurity projects.\n"
        "5. Add tests before advertising production readiness.\n"
        "6. Keep dependencies documented and remove unused packages.\n"
        "7. Use consistent folder structure across projects.\n"
        "8. Keep a changelog or project evolution notes.\n"
        "9. Use JARVIS workflow project <name> before release.\n"
        "10. Promote strongest projects first in CV/portfolio."
    )


def what_should_i_standardize():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    output = [
        "WHAT SHOULD BE STANDARDIZED ACROSS PROJECTS",
        "Mode: cross-project recommendation",
        "",
        "Standardize these first:"
    ]

    standards = [
        "README.md structure: purpose, setup, run, test, deployment.",
        ".env.example and environment variable naming.",
        "API service/client structure.",
        "Authentication/JWT/security configuration.",
        "Logging and audit logging format.",
        "Backup/restore naming and folder structure.",
        "Test folder naming and minimum test coverage.",
        "Docker/CI/release checklist format.",
        "Project scoring and security audit workflow.",
        "Consistent folder names: routes, services, models, utils, config, tests."
    ]

    for index, item in enumerate(standards, start=1):
        output.append(f"{index}. {item}")

    output.append("")
    output.append("Supporting reports to run:")
    output.append("- repeated security mistakes")
    output.append("- repeated architecture mistakes")
    output.append("- reusable modules")
    output.append("- generate engineering standards")

    return "\n".join(output)


def cross_project_learning_report():
    return (
        "CROSS PROJECT LEARNING REPORT\n\n"
        + cross_project_tech_patterns()
        + "\n\n"
        + repeated_security_mistakes()
        + "\n\n"
        + repeated_architecture_mistakes()
        + "\n\n"
        + reusable_modules_across_projects()
        + "\n\n"
        + what_should_i_standardize()
    )


# Friendly aliases
def what_patterns_do_all_projects_use():
    return cross_project_tech_patterns()


def what_security_mistakes_repeat():
    return repeated_security_mistakes()


def what_architecture_mistakes_repeat():
    return repeated_architecture_mistakes()


def what_technologies_do_i_use_most():
    return cross_project_tech_patterns()


def what_reusable_modules_do_i_have():
    return reusable_modules_across_projects()


def generate_engineering_standards():
    return engineering_standards()


def generate_coding_standards():
    return coding_standards()


def generate_portfolio_best_practices():
    return portfolio_best_practices()


def cross_project_learning():
    return cross_project_learning_report()

# ==========================
# STEP 20 - PROJECT COMMANDER DASHBOARD & GLOBAL INTELLIGENCE
# Global portfolio health / rankings / dashboards exported to reports/
# Safe intelligence only. No automatic code changes.
# ==========================
GLOBAL_REPORTS_DIR = "reports"


def _dashboard_safe_filename(name):
    cleaned = "".join(
        ch if ch.isalnum() or ch in "._-" else "_"
        for ch in str(name).strip()
    ).strip("_")

    return cleaned or "dashboard"


def _dashboard_timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _save_global_dashboard(filename, content):
    os.makedirs(GLOBAL_REPORTS_DIR, exist_ok=True)

    path = os.path.join(
        GLOBAL_REPORTS_DIR,
        filename
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path


def _simple_project_health(project):
    text = _all_project_text(project)

    score = 0
    notes = []

    if project.get("files_count", 0) >= 20:
        score += 10
        notes.append("Non-trivial project size detected.")

    if project.get("tech_stack"):
        score += 10
        notes.append("Tech stack detected.")

    if "readme" in text:
        score += 10
        notes.append("README/documentation evidence detected.")

    if "test" in text or "pytest" in text or "jest" in text:
        score += 12
        notes.append("Test evidence detected.")

    if "docker" in text or "dockerfile" in text or "docker-compose" in text:
        score += 10
        notes.append("Docker/deployment evidence detected.")

    if ".github" in text or "workflow" in text or "ci" in text:
        score += 8
        notes.append("CI/workflow evidence detected.")

    if "jwt" in text or "token" in text or "auth" in text:
        score += 12
        notes.append("Authentication/token/security evidence detected.")

    if "bcrypt" in text or "argon2" in text or "passlib" in text:
        score += 10
        notes.append("Password hashing evidence detected.")

    if "your-secret-key" in text or "changeme" in text or "password123" in text:
        score -= 15
        notes.append("Weak/demo secret pattern detected.")

    if "localhost" in text or "127.0.0.1" in text:
        score -= 5
        notes.append("Localhost/hardcoded local URL evidence detected.")

    score = max(0, min(100, score))

    if score >= 75:
        level = "STRONG"
    elif score >= 55:
        level = "GOOD"
    elif score >= 35:
        level = "NEEDS_ATTENTION"
    else:
        level = "WEAK"

    return {
        "name": project.get("name", "Unknown"),
        "path": project.get("path", ""),
        "files_count": project.get("files_count", 0),
        "tech_stack": project.get("tech_stack", []),
        "score": score,
        "level": level,
        "notes": notes
    }


def _all_project_health_cards():
    projects = _latest_unique_deep_projects()

    cards = [
        _simple_project_health(project)
        for project in projects
    ]

    cards.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return cards


def _format_health_card(card):
    return (
        f"{card['name']} | "
        f"health {card['score']}/100 | "
        f"{card['level']} | "
        f"files {card['files_count']} | "
        f"stack: {', '.join(card['tech_stack']) if card['tech_stack'] else 'Unknown'}"
    )


def show_all_projects_health():
    cards = _all_project_health_cards()

    if not cards:
        return "No deep projects remembered."

    output = [
        "ALL PROJECTS HEALTH DASHBOARD",
        "Mode: rule-based global intelligence / verify manually",
        "",
        f"Projects analyzed: {len(cards)}",
        "",
        "Health ranking:"
    ]

    for index, card in enumerate(cards, start=1):
        output.append(f"{index}. {_format_health_card(card)}")

        for note in card["notes"][:4]:
            output.append(f"   - {note}")

    return "\n".join(output)


def show_strongest_projects(limit=10):
    cards = _all_project_health_cards()

    if not cards:
        return "No deep projects remembered."

    output = [
        "STRONGEST PROJECTS",
        "Mode: rule-based health ranking",
        ""
    ]

    for index, card in enumerate(cards[:limit], start=1):
        output.append(f"{index}. {_format_health_card(card)}")

    return "\n".join(output)


def show_weakest_projects(limit=10):
    cards = _all_project_health_cards()

    if not cards:
        return "No deep projects remembered."

    cards = list(reversed(cards))

    output = [
        "WEAKEST PROJECTS",
        "Mode: rule-based health ranking",
        ""
    ]

    for index, card in enumerate(cards[:limit], start=1):
        output.append(f"{index}. {_format_health_card(card)}")

        for note in card["notes"][:6]:
            output.append(f"   - {note}")

    return "\n".join(output)


def show_projects_needing_attention():
    cards = _all_project_health_cards()

    if not cards:
        return "No deep projects remembered."

    attention = [
        card for card in cards
        if card["score"] < 60
        or card["level"] in {"WEAK", "NEEDS_ATTENTION"}
    ]

    if not attention:
        return "No projects needing urgent attention detected."

    output = [
        "PROJECTS NEEDING ATTENTION",
        "Mode: rule-based / no automatic changes",
        ""
    ]

    for card in attention:
        output.append(f"- {_format_health_card(card)}")
        output.append(f"  Suggested command: workflow project {card['name']}")

    return "\n".join(output)


def show_security_ranking():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    ranking = []

    for project in projects:
        text = _all_project_text(project)
        score = 0
        notes = []

        if "auth" in text:
            score += 15
            notes.append("Auth evidence.")
        if "jwt" in text or "token" in text:
            score += 15
            notes.append("JWT/token evidence.")
        if "bcrypt" in text or "argon2" in text or "passlib" in text:
            score += 20
            notes.append("Password hashing evidence.")
        if "test" in text or "pytest" in text or "jest" in text:
            score += 10
            notes.append("Test evidence.")
        if "docker" in text or ".github" in text or "workflow" in text:
            score += 10
            notes.append("Deployment/CI evidence.")
        if "your-secret-key" in text or "changeme" in text or "password123" in text:
            score -= 25
            notes.append("Weak/demo secret pattern.")

        score = max(0, min(100, score))

        ranking.append({
            "name": project.get("name", "Unknown"),
            "score": score,
            "notes": notes
        })

    ranking.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    output = [
        "GLOBAL SECURITY RANKING",
        "Mode: heuristic / verify with full security audit",
        ""
    ]

    for index, item in enumerate(ranking, start=1):
        output.append(
            f"{index}. {item['name']} -> security health {item['score']}/100"
        )
        for note in item["notes"][:4]:
            output.append(f"   - {note}")

    return "\n".join(output)


def show_architecture_ranking():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    ranking = []

    for project in projects:
        text = _all_project_text(project)
        stack = project.get("tech_stack", [])
        score = 0
        notes = []

        if stack:
            score += 15
            notes.append("Tech stack detected.")
        if "routes" in text or "api" in text or "controller" in text:
            score += 15
            notes.append("Route/API structure evidence.")
        if "service" in text or "services" in text:
            score += 15
            notes.append("Service layer evidence.")
        if "models" in text or "schemas" in text:
            score += 10
            notes.append("Models/schemas evidence.")
        if "config" in text or "settings" in text:
            score += 10
            notes.append("Config/settings evidence.")
        if "docker" in text or "workflow" in text:
            score += 10
            notes.append("Deployment/CI structure evidence.")
        if "localhost" in text or "127.0.0.1" in text:
            score -= 8
            notes.append("Hardcoded local URL evidence.")

        score = max(0, min(100, score))

        ranking.append({
            "name": project.get("name", "Unknown"),
            "score": score,
            "notes": notes
        })

    ranking.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    output = [
        "GLOBAL ARCHITECTURE RANKING",
        "Mode: heuristic / verify with architecture report",
        ""
    ]

    for index, item in enumerate(ranking, start=1):
        output.append(
            f"{index}. {item['name']} -> architecture health {item['score']}/100"
        )
        for note in item["notes"][:4]:
            output.append(f"   - {note}")

    return "\n".join(output)


def show_production_readiness_ranking():
    cards = _all_project_health_cards()

    if not cards:
        return "No deep projects remembered."

    output = [
        "GLOBAL PRODUCTION READINESS RANKING",
        "Mode: heuristic / run production workflow before real release",
        ""
    ]

    for index, card in enumerate(cards, start=1):
        readiness = "LOW"

        if card["score"] >= 75:
            readiness = "HIGH"
        elif card["score"] >= 55:
            readiness = "MEDIUM"

        output.append(
            f"{index}. {card['name']} -> readiness {readiness} "
            f"(health {card['score']}/100)"
        )

    output.append("")
    output.append("Recommended command for real validation:")
    output.append("production workflow <project>")

    return "\n".join(output)


def show_technical_debt_ranking():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    ranking = []

    for project in projects:
        debt = 0
        notes = []

        for file in project.get("files", []):
            path = file.get("relative_path", "")
            content = file.get("content", "")
            lines = len(content.splitlines())

            if lines >= 160:
                debt += 10
                notes.append(f"Oversized file: {path}")

            lower = content.lower()

            if "todo" in lower or "fixme" in lower:
                debt += 5
                notes.append(f"TODO/FIXME found: {path}")

            if "localhost" in lower or "127.0.0.1" in lower:
                debt += 4
                notes.append(f"Localhost config: {path}")

            if "print(" in lower:
                debt += 2

        debt = min(100, debt)

        ranking.append({
            "name": project.get("name", "Unknown"),
            "debt": debt,
            "notes": notes
        })

    ranking.sort(
        key=lambda item: item["debt"],
        reverse=True
    )

    output = [
        "GLOBAL TECHNICAL DEBT RANKING",
        "Mode: heuristic / verify with refactoring planner",
        ""
    ]

    for index, item in enumerate(ranking, start=1):
        output.append(
            f"{index}. {item['name']} -> debt score {item['debt']}/100"
        )

        for note in item["notes"][:5]:
            output.append(f"   - {note}")

    return "\n".join(output)


def show_engineering_dashboard():
    return (
        "JARVIS ENGINEERING DASHBOARD\n\n"
        + show_all_projects_health()
        + "\n\n"
        + show_security_ranking()
        + "\n\n"
        + show_architecture_ranking()
        + "\n\n"
        + show_production_readiness_ranking()
        + "\n\n"
        + show_technical_debt_ranking()
        + "\n\n"
        + show_projects_needing_attention()
    )


def show_portfolio_dashboard():
    return (
        "JARVIS PORTFOLIO DASHBOARD\n\n"
        + cross_project_tech_patterns()
        + "\n\n"
        + show_strongest_projects()
        + "\n\n"
        + show_weakest_projects()
        + "\n\n"
        + what_should_i_standardize()
        + "\n\n"
        + portfolio_best_practices()
    )


def export_engineering_dashboard():
    content = (
        "# JARVIS Engineering Dashboard\n\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "```text\n"
        + show_engineering_dashboard()
        + "\n```"
    )

    path = _save_global_dashboard(
        f"engineering_dashboard_{_dashboard_timestamp()}.md",
        content
    )

    return f"{content}\n\nDASHBOARD EXPORTED:\n{path}"


def export_portfolio_dashboard():
    content = (
        "# JARVIS Portfolio Dashboard\n\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "```text\n"
        + show_portfolio_dashboard()
        + "\n```"
    )

    path = _save_global_dashboard(
        f"portfolio_dashboard_{_dashboard_timestamp()}.md",
        content
    )

    return f"{content}\n\nDASHBOARD EXPORTED:\n{path}"


def export_security_dashboard():
    content = (
        "# JARVIS Security Dashboard\n\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "```text\n"
        + show_security_ranking()
        + "\n\n"
        + repeated_security_mistakes()
        + "\n```"
    )

    path = _save_global_dashboard(
        f"security_dashboard_{_dashboard_timestamp()}.md",
        content
    )

    return f"{content}\n\nDASHBOARD EXPORTED:\n{path}"


def export_global_dashboards():
    engineering = export_engineering_dashboard()
    portfolio = export_portfolio_dashboard()
    security = export_security_dashboard()

    return (
        "GLOBAL DASHBOARDS EXPORTED\n\n"
        + engineering.split("DASHBOARD EXPORTED:")[-1].strip()
        + "\n"
        + portfolio.split("DASHBOARD EXPORTED:")[-1].strip()
        + "\n"
        + security.split("DASHBOARD EXPORTED:")[-1].strip()
    )


def global_intelligence_summary():
    cards = _all_project_health_cards()

    if not cards:
        return "No deep projects remembered."

    best = cards[0]
    weakest = cards[-1]

    return (
        "GLOBAL INTELLIGENCE SUMMARY\n\n"
        f"Projects analyzed: {len(cards)}\n"
        f"Strongest project: {best['name']} ({best['score']}/100)\n"
        f"Weakest project: {weakest['name']} ({weakest['score']}/100)\n\n"
        "Recommended next actions:\n"
        f"1. Run workflow project {weakest['name']}.\n"
        f"2. Run production workflow {best['name']}.\n"
        "3. Export engineering dashboard.\n"
        "4. Standardize README, .env.example, tests, CI, and release checklists across all projects."
    )


# Friendly aliases
def show_all_projects_dashboard():
    return show_all_projects_health()


def show_global_dashboard():
    return show_engineering_dashboard()


def show_global_intelligence():
    return global_intelligence_summary()


def show_weakest_project_dashboard():
    return show_weakest_projects()


def show_strongest_project_dashboard():
    return show_strongest_projects()


def security_ranking():
    return show_security_ranking()


def architecture_ranking():
    return show_architecture_ranking()


def production_readiness_ranking():
    return show_production_readiness_ranking()


def technical_debt_ranking():
    return show_technical_debt_ranking()



# ==========================
# STEP 22 - DEPENDENCY INTELLIGENCE
# Python / Node / React / Angular / Next / Flask / FastAPI dependency analyzer.
# Offline, rule-based, safe analysis only. No package installation or updates.
# ==========================
def _dependency_project(project_name):
    project = find_deep_project(project_name)

    if not project:
        return None, f"Project not found in deep memory: {project_name}"

    return project, None


def _iter_project_dependency_files(project):
    dependency_names = {
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "pipfile",
        "pipfile.lock",
        "poetry.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
    }

    results = []

    for file in project.get("files", []):
        path = file.get("relative_path", "")
        name = os.path.basename(path).lower()

        if name in dependency_names:
            results.append(file)

        if "requirements" in name and name.endswith(".txt"):
            results.append(file)

    return results


def _parse_package_json(content):
    try:
        data = json.loads(content)
    except Exception:
        return {
            "error": "Invalid package.json"
        }

    result = {
        "dependencies": data.get("dependencies", {}),
        "devDependencies": data.get("devDependencies", {}),
        "peerDependencies": data.get("peerDependencies", {}),
        "optionalDependencies": data.get("optionalDependencies", {}),
        "scripts": data.get("scripts", {}),
        "engines": data.get("engines", {}),
    }

    return result


def _parse_requirements(content):
    deps = []

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if " #" in line:
            line = line.split(" #", 1)[0].strip()

        deps.append(line)

    return deps


def _parse_pyproject(content):
    sections = {}
    current = None

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current = line.strip("[]")
            sections[current] = []
            continue

        if current:
            sections.setdefault(current, []).append(line)

    return sections


def extract_project_dependencies(project_name):
    project, error = _dependency_project(project_name)

    if error:
        return None, error

    dependency_files = _iter_project_dependency_files(project)

    result = {
        "project": project.get("name", project_name),
        "path": project.get("path", ""),
        "tech_stack": project.get("tech_stack", []),
        "files": [],
        "node": {},
        "python": {},
        "docker": [],
        "locks": [],
        "package_managers": set(),
    }

    for file in dependency_files:
        path = file.get("relative_path", "")
        name = os.path.basename(path).lower()
        content = file.get("content", "")

        result["files"].append(path)

        if name == "package.json":
            parsed = _parse_package_json(content)
            result["node"][path] = parsed
            result["package_managers"].add("npm/node package.json")

        elif name == "requirements.txt" or ("requirements" in name and name.endswith(".txt")):
            result["python"][path] = _parse_requirements(content)
            result["package_managers"].add("pip requirements.txt")

        elif name == "pyproject.toml":
            result["python"][path] = _parse_pyproject(content)
            result["package_managers"].add("pyproject.toml")

        elif name in {"pipfile", "pipfile.lock"}:
            result["python"][path] = content[:3000]
            result["package_managers"].add("pipenv")

        elif name in {"poetry.lock"}:
            result["python"][path] = content[:3000]
            result["package_managers"].add("poetry")

        elif name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}:
            result["locks"].append(path)

            if name == "package-lock.json":
                result["package_managers"].add("npm")
            elif name == "yarn.lock":
                result["package_managers"].add("yarn")
            elif name == "pnpm-lock.yaml":
                result["package_managers"].add("pnpm")

        elif name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
            result["docker"].append(path)

    result["package_managers"] = sorted(result["package_managers"])

    return result, None


def show_dependencies(project_name):
    data, error = extract_project_dependencies(project_name)

    if error:
        return error

    output = [
        "DEPENDENCY OVERVIEW",
        "Mode: offline / rule-based / no internet vulnerability database",
        f"Project: {data['project']}",
        f"Path: {data['path']}",
        f"Tech stack: {', '.join(data['tech_stack'])}",
        "",
        "Dependency files detected:"
    ]

    if data["files"]:
        output.extend(f"- {path}" for path in data["files"])
    else:
        output.append("- No dependency files detected.")

    output.append("")
    output.append("Package managers detected:")

    if data["package_managers"]:
        output.extend(f"- {manager}" for manager in data["package_managers"])
    else:
        output.append("- None detected.")

    output.append("")
    output.append("Node dependencies:")

    if data["node"]:
        for path, parsed in data["node"].items():
            output.append(f"\n{path}")

            for section in [
                "dependencies",
                "devDependencies",
                "peerDependencies",
                "optionalDependencies"
            ]:
                deps = parsed.get(section, {})

                output.append(f"  {section}: {len(deps)}")

                for name, version in list(deps.items())[:80]:
                    output.append(f"   - {name}: {version}")
    else:
        output.append("- None detected.")

    output.append("")
    output.append("Python dependencies:")

    if data["python"]:
        for path, parsed in data["python"].items():
            output.append(f"\n{path}")

            if isinstance(parsed, list):
                for dep in parsed[:120]:
                    output.append(f"   - {dep}")
            elif isinstance(parsed, dict):
                for section, lines in parsed.items():
                    output.append(f"  [{section}]")
                    for line in lines[:40]:
                        output.append(f"   - {line}")
            else:
                output.append(str(parsed)[:3000])
    else:
        output.append("- None detected.")

    return "\n".join(output)


def show_package_managers(project_name):
    data, error = extract_project_dependencies(project_name)

    if error:
        return error

    output = [
        "PACKAGE MANAGERS",
        f"Project: {data['project']}",
        ""
    ]

    if data["package_managers"]:
        output.extend(f"- {manager}" for manager in data["package_managers"])
    else:
        output.append("No package managers detected.")

    if data["locks"]:
        output.append("")
        output.append("Lock files:")
        output.extend(f"- {path}" for path in data["locks"])

    return "\n".join(output)


def dependency_health_report(project_name):
    data, error = extract_project_dependencies(project_name)

    if error:
        return error

    issues = []
    positives = []

    if not data["files"]:
        issues.append("No dependency manifest files detected.")

    if data["node"] and not data["locks"]:
        issues.append("Node package.json detected but no lock file found in indexed files.")
    elif data["locks"]:
        positives.append("Lock file evidence detected.")

    if data["python"]:
        positives.append("Python dependency manifest detected.")

    if data["node"]:
        positives.append("Node/package.json dependency manifest detected.")

    if data["docker"]:
        positives.append("Docker/deployment dependency evidence detected.")

    for path, parsed in data["node"].items():
        if isinstance(parsed, dict):
            deps = parsed.get("dependencies", {})
            dev_deps = parsed.get("devDependencies", {})

            if len(deps) + len(dev_deps) > 80:
                issues.append(f"{path}: large dependency surface detected ({len(deps) + len(dev_deps)} packages).")

            scripts = parsed.get("scripts", {})
            if not scripts:
                issues.append(f"{path}: no npm scripts detected.")
            else:
                positives.append(f"{path}: npm scripts detected.")

    for path, parsed in data["python"].items():
        if isinstance(parsed, list):
            if len(parsed) > 80:
                issues.append(f"{path}: large Python dependency surface detected ({len(parsed)} packages).")

            unpinned = [
                dep for dep in parsed
                if not any(operator in dep for operator in ["==", ">=", "<=", "~=", ">", "<"])
                and not dep.startswith("-")
            ]

            if unpinned:
                issues.append(f"{path}: unpinned dependencies detected: {', '.join(unpinned[:15])}")

    output = [
        "DEPENDENCY HEALTH REPORT",
        "Mode: offline / rule-based / verify with npm audit, pip-audit, safety, or Snyk",
        f"Project: {data['project']}",
        "",
        "Positive evidence:"
    ]

    if positives:
        output.extend(f"- {item}" for item in positives)
    else:
        output.append("- None detected.")

    output.append("")
    output.append("Issues / warnings:")

    if issues:
        output.extend(f"- {item}" for item in issues)
    else:
        output.append("- No major dependency hygiene issues detected by offline rules.")

    output.append("")
    output.append("Recommended validation commands:")
    output.append("- Node: npm audit")
    output.append("- Node: npm outdated")
    output.append("- Python: pip list --outdated")
    output.append("- Python: pip-audit")
    output.append("- Python: safety check")
    output.append("- General: review lock files before production")

    return "\n".join(output)


def find_vulnerable_dependencies(project_name):
    data, error = extract_project_dependencies(project_name)

    if error:
        return error

    risky_names = {
        "lodash",
        "moment",
        "request",
        "node-sass",
        "serialize-javascript",
        "minimist",
        "debug",
        "axios",
        "jsonwebtoken",
        "express",
        "flask",
        "django",
        "fastapi",
        "jinja2",
        "pyjwt",
        "cryptography",
        "pillow",
        "urllib3",
        "requests",
        "pyyaml",
        "sqlalchemy",
    }

    output = [
        "POSSIBLE VULNERABLE / SECURITY-SENSITIVE DEPENDENCIES",
        "Mode: offline heuristic. This is NOT a real CVE scan.",
        f"Project: {data['project']}",
        "",
        "Matches to verify manually:"
    ]

    matches = []

    for path, parsed in data["node"].items():
        if not isinstance(parsed, dict):
            continue

        for section in ["dependencies", "devDependencies"]:
            for name, version in parsed.get(section, {}).items():
                if name.lower() in risky_names:
                    matches.append(f"{path} -> {section} -> {name}: {version}")

    for path, parsed in data["python"].items():
        if isinstance(parsed, list):
            for dep in parsed:
                dep_name = re.split(r"[=<>~! ]+", dep.strip())[0].lower()

                if dep_name in risky_names:
                    matches.append(f"{path} -> {dep}")

    if matches:
        output.extend(f"- {item}" for item in matches)
    else:
        output.append("- No security-sensitive dependency names matched offline rules.")

    output.append("")
    output.append("Important:")
    output.append("- Run real scanners before production: npm audit, pip-audit, safety, Snyk, Dependabot.")
    output.append("- This function only flags dependency names that commonly require extra attention.")

    return "\n".join(output)


def find_outdated_dependencies(project_name):
    data, error = extract_project_dependencies(project_name)

    if error:
        return error

    output = [
        "OUTDATED DEPENDENCIES CHECK",
        "Mode: offline guidance only. Exact outdated versions require internet/tooling.",
        f"Project: {data['project']}",
        "",
        "Detected manifests:"
    ]

    if data["files"]:
        output.extend(f"- {path}" for path in data["files"])
    else:
        output.append("- No manifests detected.")

    output.append("")
    output.append("Run these commands locally:")
    output.append("- Node/npm: npm outdated")
    output.append("- Node/npm: npm audit")
    output.append("- Yarn: yarn outdated")
    output.append("- PNPM: pnpm outdated")
    output.append("- Python: pip list --outdated")
    output.append("- Python: pip-audit")
    output.append("- Python/Poetry: poetry show --outdated")

    return "\n".join(output)


def find_unused_dependencies(project_name):
    data, error = extract_project_dependencies(project_name)

    if error:
        return error

    project, _ = _dependency_project(project_name)
    all_text = _all_project_text(project)

    unused = []

    for path, parsed in data["node"].items():
        if not isinstance(parsed, dict):
            continue

        for section in ["dependencies", "devDependencies"]:
            for name, version in parsed.get(section, {}).items():
                short_name = name.split("/")[-1].lower()

                if short_name not in all_text and name.lower() not in all_text:
                    unused.append(f"{path} -> {section} -> {name}: {version}")

    for path, parsed in data["python"].items():
        if isinstance(parsed, list):
            for dep in parsed:
                dep_name = re.split(r"[=<>~! ]+", dep.strip())[0].lower()

                if dep_name and dep_name not in all_text:
                    unused.append(f"{path} -> {dep}")

    output = [
        "POSSIBLE UNUSED DEPENDENCIES",
        "Mode: heuristic only. Do NOT uninstall automatically.",
        f"Project: {data['project']}",
        "",
        "Possible unused dependencies:"
    ]

    if unused:
        output.extend(f"- {item}" for item in unused[:80])
        if len(unused) > 80:
            output.append(f"... and {len(unused) - 80} more")
    else:
        output.append("- No obvious unused dependencies detected by text search.")

    output.append("")
    output.append("Before removing anything:")
    output.append("- Search imports/usages manually.")
    output.append("- Check dynamic imports and framework plugins.")
    output.append("- Run tests.")
    output.append("- Create a backup.")
    output.append("- Remove one dependency at a time.")

    return "\n".join(output)


def show_dependency_tree(project_name):
    data, error = extract_project_dependencies(project_name)

    if error:
        return error

    output = [
        "DEPENDENCY TREE / MANIFEST MAP",
        "Mode: simplified tree based on manifests only",
        f"Project: {data['project']}",
        ""
    ]

    for path, parsed in data["node"].items():
        output.append(f"{path}")
        if isinstance(parsed, dict):
            for section in ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]:
                deps = parsed.get(section, {})
                output.append(f"  {section}")
                if deps:
                    for name, version in list(deps.items())[:80]:
                        output.append(f"    - {name}@{version}")
                else:
                    output.append("    - none")

    for path, parsed in data["python"].items():
        output.append(f"{path}")
        if isinstance(parsed, list):
            for dep in parsed[:120]:
                output.append(f"  - {dep}")
        elif isinstance(parsed, dict):
            for section, lines in parsed.items():
                output.append(f"  [{section}]")
                for line in lines[:40]:
                    output.append(f"    - {line}")
        else:
            output.append(str(parsed)[:2000])

    if not data["node"] and not data["python"]:
        output.append("No Node/Python dependency tree could be generated.")

    return "\n".join(output)


# Friendly aliases
def dependencies(project_name):
    return show_dependencies(project_name)


def dependency_report(project_name):
    return dependency_health_report(project_name)


def vulnerable_dependencies(project_name):
    return find_vulnerable_dependencies(project_name)


def outdated_dependencies(project_name):
    return find_outdated_dependencies(project_name)


def unused_dependencies(project_name):
    return find_unused_dependencies(project_name)


def package_managers(project_name):
    return show_package_managers(project_name)


def dependency_tree(project_name):
    return show_dependency_tree(project_name)



# ==========================
# STEP 30 - ENTERPRISE ENGINEERING DASHBOARD
# Global executive / engineering / security / production / debt dashboard.
# Works across all remembered deep projects.
# Safe reporting only. No automatic code changes.
# ==========================
ENTERPRISE_DASHBOARD_DIR = "reports"


def _step30_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _step30_timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _step30_safe_filename(name):
    cleaned = "".join(
        ch if ch.isalnum() or ch in "._-" else "_"
        for ch in str(name).strip()
    ).strip("_")

    return cleaned or "enterprise_dashboard"


def _step30_save_dashboard(name, content):
    os.makedirs(
        ENTERPRISE_DASHBOARD_DIR,
        exist_ok=True
    )

    path = os.path.join(
        ENTERPRISE_DASHBOARD_DIR,
        f"{_step30_safe_filename(name)}_{_step30_timestamp()}.md"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path


def _step30_projects():
    try:
        return _latest_unique_deep_projects()
    except Exception:
        data = load_deep_projects()
        latest = {}

        for item in data:
            name = item.get("name", "").strip()

            if name:
                latest[normalize_name(name)] = item

        return list(latest.values())


def _step30_project_text(project):
    try:
        return _all_project_text(project)
    except Exception:
        chunks = [
            project.get("name", ""),
            project.get("path", ""),
            " ".join(project.get("tech_stack", [])),
            project.get("summary", "")
        ]

        for file in project.get("files", []):
            chunks.append(file.get("relative_path", ""))
            chunks.append(file.get("content", ""))

        return "\n".join(chunks).lower()


def _step30_count_files(project, keywords):
    results = []

    for file in project.get("files", []):
        path = file.get("relative_path", "")
        content = file.get("content", "")
        haystack = (path + "\n" + content).lower()

        if any(keyword.lower() in haystack for keyword in keywords):
            results.append(path)

    return results


def _step30_card(project):
    text = _step30_project_text(project)
    files_count = project.get(
        "files_count",
        len(project.get("files", []))
    )
    stack = project.get("tech_stack", [])

    security = 0
    architecture = 0
    testing = 0
    devops = 0
    documentation = 0
    performance = 0
    technical_debt = 0

    notes = []
    blockers = []

    # Security score
    if "auth" in text or "login" in text:
        security += 18
    if "jwt" in text or "token" in text or "access_token" in text:
        security += 18
    if "bcrypt" in text or "argon2" in text or "passlib" in text:
        security += 20
    if ".env" in text or "os.getenv" in text or "process.env" in text:
        security += 12
    if "upload" in text or "multipart" in text or "formdata" in text:
        security += 8
    if "your-secret-key" in text or "changeme" in text or "password123" in text:
        security -= 25
        blockers.append("Weak/demo secret or password pattern detected.")

    # Architecture score
    if stack:
        architecture += 15
    if "routes" in text or "api" in text or "controller" in text:
        architecture += 15
    if "service" in text or "services" in text:
        architecture += 12
    if "models" in text or "schemas" in text or "database" in text:
        architecture += 12
    if "config" in text or "settings" in text:
        architecture += 10
    if files_count >= 20:
        architecture += 10

    # Testing score
    if "pytest" in text or "jest" in text or "vitest" in text:
        testing += 25
    if "test_" in text or ".test." in text or ".spec." in text or "/tests/" in text:
        testing += 25
    if "coverage" in text:
        testing += 15
    if testing == 0:
        blockers.append("No strong testing evidence detected.")

    # DevOps score
    if "dockerfile" in text or "docker-compose" in text:
        devops += 25
    if ".github" in text or "workflow" in text or "ci" in text:
        devops += 25
    if "deploy" in text or "production" in text:
        devops += 10
    if "healthcheck" in text or "health check" in text:
        devops += 10

    # Documentation score
    if "readme" in text:
        documentation += 25
    if "docs" in text or "documentation" in text:
        documentation += 15
    if "architecture" in text:
        documentation += 15
    if "changelog" in text or "release notes" in text:
        documentation += 10

    # Performance score
    if "pagination" in text or "limit" in text:
        performance += 12
    if "cache" in text:
        performance += 10
    if "background" in text or "worker" in text:
        performance += 10
    if "time.sleep" in text or "readlines()" in text:
        performance -= 10

    # Debt score
    for file in project.get("files", []):
        content = file.get("content", "")
        path = file.get("relative_path", "")
        lower = content.lower()
        lines = len(content.splitlines())

        if lines >= 160:
            technical_debt += 8
            notes.append(f"Oversized file: {path}")

        if "todo" in lower or "fixme" in lower:
            technical_debt += 5

        if "localhost" in lower or "127.0.0.1" in lower:
            technical_debt += 4

        if "print(" in lower:
            technical_debt += 2

    security = max(0, min(100, security))
    architecture = max(0, min(100, architecture))
    testing = max(0, min(100, testing))
    devops = max(0, min(100, devops))
    documentation = max(0, min(100, documentation))
    performance = max(0, min(100, performance))
    technical_debt = max(0, min(100, technical_debt))

    health = round(
        (
            security
            + architecture
            + testing
            + devops
            + documentation
            + performance
            + (100 - technical_debt)
        ) / 7,
        1
    )

    if health >= 80 and not blockers:
        status = "ENTERPRISE_READY"
    elif health >= 65:
        status = "STRONG"
    elif health >= 45:
        status = "NEEDS_ATTENTION"
    else:
        status = "WEAK"

    return {
        "name": project.get("name", "Unknown"),
        "path": project.get("path", ""),
        "files_count": files_count,
        "tech_stack": stack,
        "security": security,
        "architecture": architecture,
        "testing": testing,
        "devops": devops,
        "documentation": documentation,
        "performance": performance,
        "technical_debt": technical_debt,
        "health": health,
        "status": status,
        "notes": notes[:10],
        "blockers": blockers,
    }


def _step30_cards():
    cards = [
        _step30_card(project)
        for project in _step30_projects()
    ]

    cards.sort(
        key=lambda card: card["health"],
        reverse=True
    )

    return cards


def _step30_format_card(card):
    return (
        f"{card['name']} | health {card['health']}/100 | {card['status']} | "
        f"security {card['security']} | arch {card['architecture']} | "
        f"tests {card['testing']} | devops {card['devops']} | "
        f"docs {card['documentation']} | perf {card['performance']} | "
        f"debt {card['technical_debt']}"
    )


def enterprise_engineering_dashboard():
    cards = _step30_cards()

    if not cards:
        return "No deep projects remembered."

    output = [
        "ENTERPRISE ENGINEERING DASHBOARD",
        "Mode: global portfolio intelligence / rule-based / verify manually",
        f"Generated: {_step30_now()}",
        "",
        f"Projects analyzed: {len(cards)}",
        "",
        "Overall ranking:"
    ]

    for index, card in enumerate(cards, start=1):
        output.append(f"{index}. {_step30_format_card(card)}")

        if card["blockers"]:
            for blocker in card["blockers"][:3]:
                output.append(f"   BLOCKER: {blocker}")

        for note in card["notes"][:3]:
            output.append(f"   NOTE: {note}")

    best = cards[0]
    weakest = cards[-1]

    output.extend([
        "",
        "Executive summary:",
        f"- Strongest project: {best['name']} ({best['health']}/100)",
        f"- Weakest project: {weakest['name']} ({weakest['health']}/100)",
        f"- Projects needing attention: {len([c for c in cards if c['status'] in {'WEAK', 'NEEDS_ATTENTION'}])}",
        "",
        "Recommended next actions:",
        f"1. Run full workflow on weakest project: {weakest['name']}",
        "2. Add tests where testing score is low.",
        "3. Add CI/Docker/release docs where DevOps score is low.",
        "4. Fix blockers before calling any project production-ready.",
    ])

    return "\n".join(output)


def executive_portfolio_dashboard():
    cards = _step30_cards()

    if not cards:
        return "No deep projects remembered."

    total_health = round(
        sum(card["health"] for card in cards) / len(cards),
        1
    )

    production_candidates = [
        card for card in cards
        if card["health"] >= 70 and not card["blockers"]
    ]

    output = [
        "EXECUTIVE PORTFOLIO DASHBOARD",
        "Mode: management-level summary",
        f"Generated: {_step30_now()}",
        "",
        f"Projects analyzed: {len(cards)}",
        f"Average portfolio health: {total_health}/100",
        f"Production candidates: {len(production_candidates)}",
        "",
        "Top projects:"
    ]

    for card in cards[:5]:
        output.append(
            f"- {card['name']} -> {card['health']}/100 ({card['status']})"
        )

    output.append("")
    output.append("Projects needing immediate attention:")

    weak = [
        card for card in cards
        if card["health"] < 55 or card["blockers"]
    ]

    if weak:
        for card in weak[:10]:
            output.append(
                f"- {card['name']} -> {card['health']}/100 | blockers: {len(card['blockers'])}"
            )
    else:
        output.append("- None detected by current rules.")

    output.append("")
    output.append("Portfolio recommendation:")
    output.append("- Promote strongest projects in CV/portfolio.")
    output.append("- Improve tests and DevOps before production claims.")
    output.append("- Export reports, diagrams, and README files for presentation.")

    return "\n".join(output)


def engineering_kpi_dashboard():
    cards = _step30_cards()

    if not cards:
        return "No deep projects remembered."

    def avg(key):
        return round(
            sum(card[key] for card in cards) / len(cards),
            1
        )

    output = [
        "ENGINEERING KPI DASHBOARD",
        "Mode: global engineering metrics",
        f"Generated: {_step30_now()}",
        "",
        f"Average security: {avg('security')}/100",
        f"Average architecture: {avg('architecture')}/100",
        f"Average testing: {avg('testing')}/100",
        f"Average DevOps: {avg('devops')}/100",
        f"Average documentation: {avg('documentation')}/100",
        f"Average performance: {avg('performance')}/100",
        f"Average technical debt: {avg('technical_debt')}/100",
        "",
        "Lowest KPI categories:"
    ]

    categories = [
        ("security", avg("security")),
        ("architecture", avg("architecture")),
        ("testing", avg("testing")),
        ("devops", avg("devops")),
        ("documentation", avg("documentation")),
        ("performance", avg("performance")),
        ("technical_debt_inverse", 100 - avg("technical_debt")),
    ]

    categories.sort(key=lambda item: item[1])

    for name, value in categories:
        output.append(f"- {name}: {value}/100")

    output.append("")
    output.append("Recommended standards:")
    output.append("- Every project should have README, tests, dependency manifest, CI, and release checklist.")
    output.append("- Every serious backend should have auth/security tests.")
    output.append("- Every portfolio project should have diagrams and setup instructions.")

    return "\n".join(output)


def enterprise_security_dashboard():
    cards = _step30_cards()

    if not cards:
        return "No deep projects remembered."

    cards = sorted(
        cards,
        key=lambda card: card["security"],
        reverse=True
    )

    output = [
        "ENTERPRISE SECURITY DASHBOARD",
        "Mode: global security overview",
        f"Generated: {_step30_now()}",
        "",
        "Security ranking:"
    ]

    for index, card in enumerate(cards, start=1):
        output.append(
            f"{index}. {card['name']} -> security {card['security']}/100"
        )

        for blocker in card["blockers"][:3]:
            output.append(f"   BLOCKER: {blocker}")

    output.append("")
    output.append("Cross-project repeated security patterns:")
    output.append(repeated_security_mistakes())

    return "\n".join(output)


def enterprise_release_dashboard():
    cards = _step30_cards()

    if not cards:
        return "No deep projects remembered."

    output = [
        "ENTERPRISE RELEASE DASHBOARD",
        "Mode: portfolio release readiness",
        f"Generated: {_step30_now()}",
        "",
        "Release readiness ranking:"
    ]

    ranked = sorted(
        cards,
        key=lambda card: (
            card["health"],
            card["devops"],
            card["testing"],
            card["security"]
        ),
        reverse=True
    )

    for index, card in enumerate(ranked, start=1):
        if card["health"] >= 80 and not card["blockers"]:
            decision = "GO"
        elif card["health"] >= 65:
            decision = "CONDITIONAL_GO"
        elif card["health"] >= 45:
            decision = "NOT_READY"
        else:
            decision = "BLOCKED"

        output.append(
            f"{index}. {card['name']} -> {decision} | health {card['health']}/100"
        )

    output.append("")
    output.append("Release rule:")
    output.append("- GO requires high health and no blockers.")
    output.append("- CONDITIONAL_GO requires manual validation.")
    output.append("- NOT_READY/BLOCKED requires fixes before release.")

    return "\n".join(output)


def enterprise_debt_dashboard():
    cards = _step30_cards()

    if not cards:
        return "No deep projects remembered."

    ranked = sorted(
        cards,
        key=lambda card: card["technical_debt"],
        reverse=True
    )

    output = [
        "ENTERPRISE TECHNICAL DEBT DASHBOARD",
        "Mode: cross-project technical debt",
        f"Generated: {_step30_now()}",
        "",
        "Debt ranking:"
    ]

    for index, card in enumerate(ranked, start=1):
        output.append(
            f"{index}. {card['name']} -> debt {card['technical_debt']}/100"
        )

        for note in card["notes"][:4]:
            output.append(f"   - {note}")

    output.append("")
    output.append("Debt reduction standard:")
    output.append("- Add tests before refactoring.")
    output.append("- Split oversized files.")
    output.append("- Centralize config/API clients.")
    output.append("- Remove TODO/FIXME only after confirming scope.")

    return "\n".join(output)


def enterprise_dashboard_full():
    return (
        "JARVIS ENTERPRISE DASHBOARD PACK\n\n"
        + enterprise_engineering_dashboard()
        + "\n\n"
        + executive_portfolio_dashboard()
        + "\n\n"
        + engineering_kpi_dashboard()
        + "\n\n"
        + enterprise_security_dashboard()
        + "\n\n"
        + enterprise_release_dashboard()
        + "\n\n"
        + enterprise_debt_dashboard()
    )


def export_enterprise_engineering_dashboard():
    content = (
        "# JARVIS Enterprise Engineering Dashboard\n\n"
        f"Generated: {_step30_now()}\n\n"
        "```text\n"
        + enterprise_dashboard_full()
        + "\n```"
    )

    path = _step30_save_dashboard(
        "enterprise_engineering_dashboard",
        content
    )

    return f"{content}\n\nDASHBOARD EXPORTED:\n{path}"


def export_executive_portfolio_dashboard():
    content = (
        "# JARVIS Executive Portfolio Dashboard\n\n"
        f"Generated: {_step30_now()}\n\n"
        "```text\n"
        + executive_portfolio_dashboard()
        + "\n```"
    )

    path = _step30_save_dashboard(
        "executive_portfolio_dashboard",
        content
    )

    return f"{content}\n\nDASHBOARD EXPORTED:\n{path}"


def export_all_enterprise_dashboards():
    outputs = [
        export_enterprise_engineering_dashboard(),
        export_executive_portfolio_dashboard(),
    ]

    paths = []

    for output in outputs:
        marker = "DASHBOARD EXPORTED:"

        if marker in output:
            paths.append(output.split(marker)[-1].strip())

    return (
        "ENTERPRISE DASHBOARDS EXPORTED\n\n"
        + "\n".join(f"- {path}" for path in paths)
    )


# Friendly aliases
def show_enterprise_dashboard():
    return enterprise_engineering_dashboard()


def show_executive_dashboard():
    return executive_portfolio_dashboard()


def show_kpi_dashboard():
    return engineering_kpi_dashboard()


def show_release_dashboard():
    return enterprise_release_dashboard()


def show_debt_dashboard():
    return enterprise_debt_dashboard()


def show_enterprise_security_dashboard():
    return enterprise_security_dashboard()


def export_enterprise_dashboard():
    return export_enterprise_engineering_dashboard()


def enterprise_dashboard():
    return enterprise_dashboard_full()



# ==========================
# STEP 32 - SELF-IMPROVEMENT INTELLIGENCE
# JARVIS Evolution Engine: recurring mistakes, strengths, learning roadmap,
# developer evolution, portfolio improvement, and global recommendations.
# Safe analysis only. No automatic code changes.
# ==========================
SELF_IMPROVEMENT_REPORTS_DIR = "reports"


def _step32_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _step32_timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _step32_safe_filename(name):
    cleaned = "".join(
        ch if ch.isalnum() or ch in "._-" else "_"
        for ch in str(name).strip()
    ).strip("_")

    return cleaned or "self_improvement_report"


def _step32_save_report(name, content):
    os.makedirs(
        SELF_IMPROVEMENT_REPORTS_DIR,
        exist_ok=True
    )

    path = os.path.join(
        SELF_IMPROVEMENT_REPORTS_DIR,
        f"{_step32_safe_filename(name)}_{_step32_timestamp()}.md"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path


def _step32_projects():
    try:
        return _latest_unique_deep_projects()
    except Exception:
        data = load_deep_projects()
        latest = {}

        for item in data:
            name = item.get("name", "").strip()

            if name:
                latest[normalize_name(name)] = item

        return list(latest.values())


def _step32_text(project):
    try:
        return _all_project_text(project)
    except Exception:
        chunks = [
            project.get("name", ""),
            project.get("path", ""),
            " ".join(project.get("tech_stack", [])),
            project.get("summary", "")
        ]

        for file in project.get("files", []):
            chunks.append(file.get("relative_path", ""))
            chunks.append(file.get("content", ""))

        return "\n".join(chunks).lower()


def _step32_find_files(project, keywords, limit=10):
    results = []

    for file in project.get("files", []):
        path = file.get("relative_path", "")
        content = file.get("content", "")
        haystack = (path + "\n" + content).lower()

        if any(keyword.lower() in haystack for keyword in keywords):
            results.append(path)

        if len(results) >= limit:
            break

    return results


def _step32_pattern_scan():
    projects = _step32_projects()

    patterns = [
        {
            "name": "Hardcoded localhost / local URLs",
            "keywords": ["localhost", "127.0.0.1", "http://localhost"],
            "recommendation": "Centralize API URLs in config and use environment variables."
        },
        {
            "name": "Weak/demo secrets",
            "keywords": ["your-secret-key", "changeme", "password123", "secure123", "secret_key = \"secret"],
            "recommendation": "Move secrets to .env and rotate demo values before production."
        },
        {
            "name": "Print/debug logging",
            "keywords": ["print(", "console.log("],
            "recommendation": "Use structured logging and remove noisy debug output."
        },
        {
            "name": "Missing/weak tests",
            "keywords": ["pytest", "jest", ".test.", ".spec.", "/tests/", "test_"],
            "recommendation": "Add tests for auth, routes, uploads, critical services, and startup."
        },
        {
            "name": "Upload/file handling",
            "keywords": ["upload", "multipart", "formdata", "file"],
            "recommendation": "Validate file size, type, content, path, and logging."
        },
        {
            "name": "Authentication/security modules",
            "keywords": ["auth", "jwt", "token", "login", "permission", "admin"],
            "recommendation": "Standardize auth/JWT/permissions and test them."
        },
        {
            "name": "Deployment/CI gaps",
            "keywords": ["dockerfile", "docker-compose", ".github", "workflow", "deploy"],
            "recommendation": "Add Docker, CI, build/test/security checks, and release checklist."
        },
        {
            "name": "Large entrypoint / monolith tendency",
            "keywords": ["app.py", "main.py", "server.py"],
            "recommendation": "Split big entry files into routes, services, models, config, utils."
        },
        {
            "name": "Documentation evidence",
            "keywords": ["readme", "docs", "documentation", "architecture"],
            "recommendation": "Keep README, architecture docs, API docs, and onboarding docs updated."
        },
    ]

    report = []

    for pattern in patterns:
        affected = []

        for project in projects:
            files = _step32_find_files(
                project,
                pattern["keywords"],
                limit=8
            )

            # For missing/weak tests, invert logic.
            if pattern["name"] == "Missing/weak tests":
                text = _step32_text(project)
                has_tests = any(
                    keyword.lower() in text
                    for keyword in pattern["keywords"]
                )

                if not has_tests:
                    affected.append(
                        (
                            project.get("name", "Unknown"),
                            ["No strong test evidence detected."]
                        )
                    )
                continue

            if files:
                affected.append(
                    (
                        project.get("name", "Unknown"),
                        files
                    )
                )

        report.append({
            "name": pattern["name"],
            "recommendation": pattern["recommendation"],
            "affected": affected
        })

    return report


def most_common_project_issues():
    patterns = _step32_pattern_scan()

    output = [
        "MOST COMMON PROJECT ISSUES",
        "Mode: cross-project self-improvement scan / verify manually",
        f"Generated: {_step32_now()}",
        ""
    ]

    ranked = sorted(
        patterns,
        key=lambda item: len(item["affected"]),
        reverse=True
    )

    found_any = False

    for item in ranked:
        if not item["affected"]:
            continue

        found_any = True
        output.append(f"\n{item['name']}")
        output.append(f"Affected projects: {len(item['affected'])}")
        output.append(f"Recommendation: {item['recommendation']}")

        for project_name, files in item["affected"][:8]:
            output.append(f"- {project_name}:")
            for file in files[:6]:
                output.append(f"  - {file}")

    if not found_any:
        output.append("No common issues detected by current rules.")

    return "\n".join(output)


def what_mistakes_do_i_repeat():
    return (
        "REPEATED DEVELOPER MISTAKES / HABITS\n"
        "Mode: inferred from remembered projects only\n\n"
        + most_common_project_issues()
        + "\n\n"
        "Interpretation:\n"
        "- These are not personal judgments; they are engineering patterns detected in project files.\n"
        "- Use them as a checklist before publishing or presenting projects."
    )


def what_are_my_strengths_as_developer():
    projects = _step32_projects()

    if not projects:
        return "No deep projects remembered."

    strengths = []

    tech_counter = {}

    for project in projects:
        for tech in project.get("tech_stack", []):
            tech_counter[tech] = tech_counter.get(tech, 0) + 1

    common_tech = sorted(
        tech_counter.items(),
        key=lambda item: item[1],
        reverse=True
    )

    if common_tech:
        strengths.append(
            "You repeatedly build with: "
            + ", ".join(f"{tech} ({count})" for tech, count in common_tech[:8])
        )

    if any(_step32_find_files(p, ["auth", "jwt", "security", "audit"]) for p in projects):
        strengths.append("Security-focused thinking appears across your projects.")

    if any(_step32_find_files(p, ["dashboard", "frontend", "components", "react", "angular"]) for p in projects):
        strengths.append("You build dashboard/UI-oriented applications, not only scripts.")

    if any(_step32_find_files(p, ["memory", "agent", "jarvis", "voice", "assistant"]) for p in projects):
        strengths.append("You are developing AI assistant / automation style systems.")

    if any(_step32_find_files(p, ["docker", "workflow", ".github", "deploy"]) for p in projects):
        strengths.append("You have deployment/DevOps awareness in at least some projects.")

    output = [
        "DEVELOPER STRENGTHS REPORT",
        "Mode: based on remembered project evidence",
        f"Projects analyzed: {len(projects)}",
        ""
    ]

    if strengths:
        output.extend(f"- {item}" for item in strengths)
    else:
        output.append("- Not enough project evidence to identify strengths.")

    output.append("")
    output.append("How to present this in interviews:")
    output.append("- Emphasize practical full-project thinking.")
    output.append("- Mention security, architecture, dashboards, automation, and AI assistant workflows.")
    output.append("- Show real demos and generated reports rather than only describing features.")

    return "\n".join(output)


def what_should_i_learn_next():
    issues = most_common_project_issues().lower()

    recommendations = []

    if "missing/weak tests" in issues or "test" in issues:
        recommendations.append("Testing: pytest, Jest/Vitest, React Testing Library, API route tests.")

    if "deployment" in issues or "ci" in issues or "docker" in issues:
        recommendations.append("DevOps: Docker, GitHub Actions, CI pipelines, release workflows.")

    if "localhost" in issues or "config" in issues:
        recommendations.append("Configuration management: .env, environment-specific config, API clients.")

    if "secret" in issues or "auth" in issues or "jwt" in issues:
        recommendations.append("Security engineering: JWT, password hashing, authorization, secret handling.")

    if "documentation" in issues:
        recommendations.append("Technical writing: README, API docs, architecture docs, onboarding guides.")

    if not recommendations:
        recommendations = [
            "Advanced testing and CI/CD.",
            "Software architecture patterns.",
            "Secure coding and threat modeling.",
            "Performance profiling.",
            "Professional documentation and release management.",
        ]

    output = [
        "WHAT SHOULD I LEARN NEXT",
        "Mode: learning roadmap from project patterns",
        ""
    ]

    for index, item in enumerate(recommendations, start=1):
        output.append(f"{index}. {item}")

    output.append("")
    output.append("Best practical order:")
    output.append("1. Add tests to one existing project.")
    output.append("2. Add CI pipeline to the same project.")
    output.append("3. Add Docker and README run instructions.")
    output.append("4. Add security regression tests.")
    output.append("5. Generate architecture diagrams and release reports.")

    return "\n".join(output)


def developer_evolution_report():
    projects = _step32_projects()
    events = []

    try:
        events = load_deep_project_events()
    except Exception:
        events = []

    output = [
        "DEVELOPER EVOLUTION REPORT",
        "Mode: portfolio/project memory based",
        f"Generated: {_step32_now()}",
        "",
        f"Projects remembered: {len(projects)}",
        f"Engineering events remembered: {len(events)}",
        ""
    ]

    if projects:
        output.append("Project timeline by memory timestamp:")

        for project in sorted(projects, key=lambda p: p.get("timestamp", ""))[-20:]:
            output.append(
                f"- {project.get('timestamp', 'Unknown')} | "
                f"{project.get('name', 'Unknown')} | "
                f"{project.get('files_count', 0)} files | "
                f"{', '.join(project.get('tech_stack', []))}"
            )

    output.append("")
    output.append("Evolution summary:")
    output.append("- You moved from project-specific assistance toward global project intelligence.")
    output.append("- Your JARVIS system now contains memory, audits, dashboards, dependency checks, release checks, and voice routing.")
    output.append("- The next improvement is not adding endless features, but validating quality with tests, docs, and real demos.")

    output.append("")
    output.append("Recommended next evolution:")
    output.append("1. Stabilize commands.")
    output.append("2. Add tests for command routing.")
    output.append("3. Prepare demo scripts.")
    output.append("4. Record a short video demo.")
    output.append("5. Package the project cleanly for portfolio/GitHub.")

    return "\n".join(output)


def self_improvement_scorecard():
    projects = _step32_projects()

    if not projects:
        return "No deep projects remembered."

    pattern_report = _step32_pattern_scan()

    issue_count = sum(
        len(item["affected"])
        for item in pattern_report
    )

    project_count = len(projects)

    strengths = 0

    for project in projects:
        text = _step32_text(project)

        if "readme" in text:
            strengths += 1
        if "auth" in text or "jwt" in text:
            strengths += 1
        if "test" in text or "pytest" in text or "jest" in text:
            strengths += 1
        if "docker" in text or "workflow" in text:
            strengths += 1

    score = 50 + min(30, strengths * 2) - min(35, issue_count * 2)
    score = max(0, min(100, score))

    if score >= 80:
        level = "STRONG_ENGINEERING_GROWTH"
    elif score >= 60:
        level = "GOOD_PROGRESS"
    elif score >= 40:
        level = "NEEDS_MORE_STABILIZATION"
    else:
        level = "HIGH_IMPROVEMENT_NEEDED"

    return (
        "SELF-IMPROVEMENT SCORECARD\n"
        f"Projects analyzed: {project_count}\n"
        f"Pattern issue count: {issue_count}\n"
        f"Strength signals: {strengths}\n"
        f"Growth score: {score}/100\n"
        f"Level: {level}\n\n"
        "Note: This is a heuristic score. Use it as a direction indicator, not as an absolute truth."
    )


def jarvis_self_improvement_plan():
    return (
        "JARVIS SELF-IMPROVEMENT PLAN\n"
        "Mode: safe planning / no automatic code changes\n\n"
        "Phase 1 - Stabilize:\n"
        "- Run syntax checks on all modified files.\n"
        "- Test 10 important voice commands.\n"
        "- Test 10 project review commands.\n"
        "- Fix command routing bugs before adding features.\n\n"
        "Phase 2 - Validate:\n"
        "- Run JARVIS on at least 3 different projects.\n"
        "- Export dashboards and compare outputs.\n"
        "- Verify false positives manually.\n\n"
        "Phase 3 - Productize:\n"
        "- Create README.\n"
        "- Add screenshots.\n"
        "- Add demo video.\n"
        "- Add architecture diagram.\n"
        "- Add setup guide.\n\n"
        "Phase 4 - Improve intelligence:\n"
        "- Store command success/failure history.\n"
        "- Track most-used commands.\n"
        "- Track recurring errors.\n"
        "- Generate monthly engineering improvement report.\n\n"
        "Phase 5 - Portfolio polish:\n"
        "- Prepare interview explanation.\n"
        "- Create 2-minute demo script.\n"
        "- Show enterprise dashboard and voice review."
    )


def jarvis_evolution_report():
    return (
        "JARVIS EVOLUTION ENGINE REPORT\n\n"
        + self_improvement_scorecard()
        + "\n\n"
        + what_are_my_strengths_as_developer()
        + "\n\n"
        + what_mistakes_do_i_repeat()
        + "\n\n"
        + what_should_i_learn_next()
        + "\n\n"
        + developer_evolution_report()
        + "\n\n"
        + jarvis_self_improvement_plan()
    )


def export_self_improvement_report():
    content = (
        "# JARVIS Self-Improvement Report\n\n"
        f"Generated: {_step32_now()}\n\n"
        "```text\n"
        + jarvis_evolution_report()
        + "\n```"
    )

    path = _step32_save_report(
        "jarvis_self_improvement_report",
        content
    )

    return f"{content}\n\nREPORT EXPORTED:\n{path}"


# Friendly aliases
def self_improvement_report():
    return jarvis_evolution_report()


def evolution_report():
    return jarvis_evolution_report()


def developer_evolution():
    return developer_evolution_report()


def repeated_mistakes():
    return what_mistakes_do_i_repeat()


def developer_strengths():
    return what_are_my_strengths_as_developer()


def learn_next():
    return what_should_i_learn_next()


def jarvis_improvement_plan():
    return jarvis_self_improvement_plan()


def export_evolution_report():
    return export_self_improvement_report()



# ==========================================================
# JARVIS ENTERPRISE DEEP PROJECT MEMORY UPGRADE
# Appended safely at the end so it overrides/enhances older functions.
#
# Adds:
# - stronger fuzzy project search
# - spoken-name aliases
# - latest/recent project context
# - search by technology
# - search authentication/JWT/Docker/Ollama/etc. across all projects
# - project intelligence summaries
# ==========================================================

ENTERPRISE_CONTEXT_FILE = os.path.join(
    MEMORY_DIR,
    "deep_project_context.json"
)


def _enterprise_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _enterprise_safe_load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            return json.load(file)
    except Exception:
        return default if default is not None else {}


def _enterprise_safe_save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)

        return True
    except Exception:
        return False


def _enterprise_context_get(key, default=None):
    data = _enterprise_safe_load_json(ENTERPRISE_CONTEXT_FILE, {})
    return data.get(key, default)


def _enterprise_context_set(**kwargs):
    data = _enterprise_safe_load_json(ENTERPRISE_CONTEXT_FILE, {})

    for key, value in kwargs.items():
        if value is not None:
            data[key] = value

    data["updated_at"] = _enterprise_now()

    return _enterprise_safe_save_json(ENTERPRISE_CONTEXT_FILE, data)


def normalize_spoken_project_name(name):
    text = str(name or "").strip()
    lower = text.lower().strip()

    lower = lower.replace(".", " ")
    lower = lower.replace("_", " ")
    lower = lower.replace("-", " ")
    lower = " ".join(lower.split())

    aliases = {
        "cyber": "CyberShield AI",
        "cyber shield": "CyberShield AI",
        "cyber shield ai": "CyberShield AI",
        "cybershield": "CyberShield AI",
        "cybershield ai": "CyberShield AI",
        "cybers in the": "CyberShield AI",
        "cyber security app": "CyberShield AI",
        "security app": "CyberShield AI",

        "jarvis": "J.A.R.V.I.S",
        "jervis": "J.A.R.V.I.S",
        "j a r v i s": "J.A.R.V.I.S",
        "j a r v i s assistant": "J.A.R.V.I.S",
        "voice assistant": "J.A.R.V.I.S",

        "manager app": "ManagerApp",
        "managerapp": "ManagerApp",
        "manager application": "ManagerApp",

        "recipe app": "AIRecipeFinder",
        "recipe finder": "AIRecipeFinder",
        "ai recipe": "AIRecipeFinder",
    }

    return aliases.get(lower, text)


def enterprise_project_aliases(name, path=""):
    base = str(name or "")
    path = str(path or "")

    values = set()

    for value in [
        base,
        path,
        os.path.basename(path),
        base.replace("_", " "),
        base.replace("-", " "),
        base.replace(".", " "),
        normalize_spoken_project_name(base),
    ]:
        if not value:
            continue

        values.add(normalize_name(value))
        values.add(normalize_name(value.replace("ai", " ai ")))
        values.add(normalize_name(value.replace("app", " app ")))

    spoken = normalize_spoken_project_name(base)

    if spoken:
        values.add(normalize_name(spoken))

    # Strong manual aliases for common projects.
    lowered = normalize_name(base + " " + path)

    if "cybershield" in lowered or "cybershieldai" in lowered:
        for alias in ["cyber", "cybershield", "cybershieldai", "cybersinthe", "securityapp"]:
            values.add(normalize_name(alias))

    if "jarvis" in lowered or "javis" in lowered:
        for alias in ["jarvis", "jervis", "jarvisassistant", "voiceassistant", "jarvisagent"]:
            values.add(normalize_name(alias))

    if "managerapp" in lowered or "manager" in lowered:
        for alias in ["managerapp", "manager", "managerapplication"]:
            values.add(normalize_name(alias))

    return {value for value in values if value}


def enterprise_project_match_score(project, query):
    query = normalize_spoken_project_name(query)
    query_norm = normalize_name(query)

    if not query_norm:
        return 0

    name = project.get("name", "")
    path = project.get("path", "")
    aliases = set(project.get("aliases", []))
    aliases.update(enterprise_project_aliases(name, path))

    best = 0

    for alias in aliases:
        if not alias:
            continue

        if query_norm == alias:
            score = 1.0
        elif query_norm in alias or alias in query_norm:
            score = 0.92
        else:
            score = difflib.SequenceMatcher(None, query_norm, alias).ratio()

        if os.path.exists(path):
            score += 0.05

        if score > best:
            best = score

    # Tech/path bonus for commands like "flask project", "angular project".
    lower_query = str(query).lower()
    stack = " ".join(project.get("tech_stack", [])).lower()

    if stack and any(word in stack for word in lower_query.split()):
        best = max(best, 0.65)

    return min(best, 1.0)


def find_deep_project(project_name):
    data = load_deep_projects()

    if not data:
        return None

    query = normalize_spoken_project_name(project_name)

    scored = []

    for index, item in enumerate(data):
        score = enterprise_project_match_score(item, query)

        if score >= 0.50:
            # Prefer newer entries.
            recency_bonus = min(index / max(len(data), 1), 1) * 0.03
            scored.append((score + recency_bonus, item))

    if not scored:
        return None

    scored.sort(
        key=lambda row: row[0],
        reverse=True
    )

    best = scored[0][1]

    _enterprise_context_set(
        last_project=best.get("name"),
        last_project_path=best.get("path"),
    )

    return best


def remember_deep_project(project_name, project_path):
    project_name = normalize_spoken_project_name(project_name)

    if not os.path.exists(project_path):
        return f"Project path not found: {project_path}"

    files = collect_project_files(project_path)

    if not files:
        return "No readable project files found."

    tech_stack = detect_tech_stack(files)

    summary = summarize_project(
        project_name,
        project_path,
        files,
        tech_stack
    )

    data = load_deep_projects()

    data, removed_count = remove_old_project_entries(
        data,
        project_name,
        project_path
    )

    aliases = sorted(enterprise_project_aliases(project_name, project_path))

    data.append({
        "timestamp": _enterprise_now(),
        "last_accessed": _enterprise_now(),
        "name": project_name,
        "path": os.path.abspath(project_path),
        "aliases": aliases,
        "tech_stack": tech_stack,
        "files_count": len(files),
        "files": [
            {
                "relative_path": item["relative_path"],
                "extension": item["extension"],
                "content": item["content"]
            }
            for item in files
        ],
        "summary": summary,
        "profile_version": "enterprise-v1"
    })

    save_deep_projects(data)

    _enterprise_context_set(
        last_project=project_name,
        last_project_path=os.path.abspath(project_path),
        last_action="remember_deep_project"
    )

    return (
        f"Deep project remembered: {project_name}\n"
        f"Old entries replaced: {removed_count}\n"
        f"Files indexed: {len(files)}\n"
        f"Tech stack: {', '.join(tech_stack)}"
    )


def mark_project_accessed(project_name):
    project = find_deep_project(project_name)

    if not project:
        return f"Project not found: {project_name}"

    data = load_deep_projects()
    target_name = normalize_name(project.get("name", ""))
    target_path = normalize_name(project.get("path", ""))

    for item in data:
        if (
            normalize_name(item.get("name", "")) == target_name
            or normalize_name(item.get("path", "")) == target_path
        ):
            item["last_accessed"] = _enterprise_now()

    save_deep_projects(data)

    _enterprise_context_set(
        last_project=project.get("name"),
        last_project_path=project.get("path")
    )

    return f"Project marked as active: {project.get('name')}"


def last_deep_project():
    last_name = _enterprise_context_get("last_project")

    if last_name:
        item = find_deep_project(last_name)

        if item:
            return (
                f"Last deep project:\n"
                f"{item.get('name')}\n"
                f"Path: {item.get('path')}\n"
                f"Files indexed: {item.get('files_count')}\n"
                f"Tech stack: {', '.join(item.get('tech_stack', []))}"
            )

    data = load_deep_projects()

    if not data:
        return "No deep projects remembered."

    item = data[-1]

    return (
        f"Last deep project:\n"
        f"{item.get('name')}\n"
        f"Path: {item.get('path')}\n"
        f"Files indexed: {item.get('files_count')}\n"
        f"Tech stack: {', '.join(item.get('tech_stack', []))}"
    )


def get_latest_deep_project():
    last_name = _enterprise_context_get("last_project")

    if last_name:
        project = find_deep_project(last_name)

        if project:
            return project

    data = load_deep_projects()

    if not data:
        return None

    return data[-1]


def continue_last_deep_project():
    item = get_latest_deep_project()

    if not item:
        return "No deep project found."

    _enterprise_context_set(
        last_project=item.get("name"),
        last_project_path=item.get("path")
    )

    return (
        f"Continue project: {item.get('name')}\n"
        f"Path: {item.get('path')}\n\n"
        f"{item.get('summary', '')[:6000]}\n\n"
        f"Suggested next commands:\n"
        f"- review project {item.get('name')}\n"
        f"- generate pdf report for project {item.get('name')}\n"
        f"- full security audit {item.get('name')}"
    )


def list_deep_projects():
    data = load_deep_projects()

    if not data:
        return "No deep projects remembered."

    latest = {}

    for item in data:
        key = normalize_name(item.get("name", ""))

        if key:
            latest[key] = item

    items = sorted(
        latest.values(),
        key=lambda item: (
            item.get("last_accessed", item.get("timestamp", "")),
            item.get("timestamp", "")
        ),
        reverse=True
    )

    output = [
        "Remembered deep projects:",
        ""
    ]

    for item in items:
        exists = "OK" if os.path.exists(item.get("path", "")) else "MISSING"
        output.append(
            f"- {item.get('name')} | {item.get('files_count')} files | "
            f"{', '.join(item.get('tech_stack', [])) or 'Unknown stack'} | {exists}"
        )

    return "\n".join(output)


def search_projects_by_technology(technology):
    data = load_deep_projects()

    if not data:
        return "No deep projects remembered."

    query = str(technology or "").lower().strip()
    results = []

    for project in _latest_unique_deep_projects():
        stack = [item.lower() for item in project.get("tech_stack", [])]
        text = _all_project_text(project, max_chars_per_project=30000)

        if query in " ".join(stack) or query in text:
            results.append(project)

    if not results:
        return f"No projects found using: {technology}"

    output = [
        f"Projects using {technology}:",
        ""
    ]

    for project in results:
        output.append(
            f"- {project.get('name')} | {project.get('path')} | "
            f"{', '.join(project.get('tech_stack', []))}"
        )

    return "\n".join(output)


def find_projects_using(technology):
    return search_projects_by_technology(technology)


def which_project_uses(technology):
    return search_projects_by_technology(technology)


def find_projects_with_keyword(keyword, limit=30):
    data = load_deep_projects()

    if not data:
        return "No deep projects remembered."

    keyword = str(keyword or "").lower().strip()

    if not keyword:
        return "Missing keyword."

    matches = []

    for project in _latest_unique_deep_projects():
        files = _files_containing_keywords(project, [keyword], limit=10)

        if files:
            matches.append((project, files))

    if not matches:
        return f"No remembered projects contain: {keyword}"

    output = [
        f"Projects containing '{keyword}':",
        ""
    ]

    for project, files in matches[:limit]:
        output.append(f"- {project.get('name')}:")
        for path in files[:8]:
            output.append(f"  - {path}")

    return "\n".join(output)


def find_authentication_implementations():
    return find_projects_with_keyword("auth")


def find_jwt_implementations():
    return find_projects_with_keyword("jwt")


def find_docker_projects():
    return search_projects_by_technology("docker")


def find_ollama_projects():
    return find_projects_with_keyword("ollama")


def find_angular_projects():
    return search_projects_by_technology("angular")


def find_react_projects():
    return search_projects_by_technology("react")


def find_flask_projects():
    return search_projects_by_technology("flask")


def find_fastapi_projects():
    return search_projects_by_technology("fastapi")


def find_project_file_global(file_query, limit=30):
    data = load_deep_projects()

    if not data:
        return "No deep projects remembered."

    query = str(file_query or "").lower().strip()

    if not query:
        return "Missing file query."

    results = []

    for project in _latest_unique_deep_projects():
        for file in project.get("files", []):
            path = file.get("relative_path", "")
            lower_path = path.lower()

            if query in lower_path or query == os.path.basename(lower_path):
                results.append((project.get("name"), path))

    if not results:
        return f"No file found globally: {file_query}"

    output = [
        f"Global file matches for '{file_query}':",
        ""
    ]

    for project_name, path in results[:limit]:
        output.append(f"- {project_name} -> {path}")

    return "\n".join(output)


def find_function_global(symbol_name, limit=40):
    data = load_deep_projects()

    if not data:
        return "No deep projects remembered."

    symbol = str(symbol_name or "").strip()

    if not symbol:
        return "Missing function/class name."

    patterns = [
        rf"\bdef\s+{re.escape(symbol)}\b",
        rf"\bclass\s+{re.escape(symbol)}\b",
        rf"\bfunction\s+{re.escape(symbol)}\b",
        rf"\bconst\s+{re.escape(symbol)}\s*=",
        rf"\bexport\s+function\s+{re.escape(symbol)}\b",
        rf"\b{re.escape(symbol)}\s*[:=]",
    ]

    results = []

    for project in _latest_unique_deep_projects():
        for file in project.get("files", []):
            content = file.get("content", "")
            path = file.get("relative_path", "")

            for pattern in patterns:
                if re.search(pattern, content, flags=re.IGNORECASE):
                    results.append((project.get("name"), path))
                    break

    if not results:
        return f"No symbol found globally: {symbol_name}"

    output = [
        f"Global symbol matches for '{symbol_name}':",
        ""
    ]

    for project_name, path in results[:limit]:
        output.append(f"- {project_name} -> {path}")

    return "\n".join(output)


def show_project_profile(project_name):
    project = find_deep_project(project_name)

    if not project:
        return f"Project not found: {project_name}"

    _enterprise_context_set(
        last_project=project.get("name"),
        last_project_path=project.get("path")
    )

    files = project.get("files", [])

    extensions = {}

    for file in files:
        ext = file.get("extension", "")
        extensions[ext] = extensions.get(ext, 0) + 1

    important = []

    for file in files:
        path = file.get("relative_path", "").lower()

        if any(token in path for token in [
            "app.", "main.", "server.", "auth", "jwt", "login", "dashboard",
            "route", "api", "config", "settings", "package.json",
            "requirements", "docker", "readme"
        ]):
            important.append(file.get("relative_path", ""))

    return (
        f"PROJECT PROFILE\n\n"
        f"Name: {project.get('name')}\n"
        f"Path: {project.get('path')}\n"
        f"Last indexed: {project.get('timestamp')}\n"
        f"Files indexed: {project.get('files_count')}\n"
        f"Tech stack: {', '.join(project.get('tech_stack', []))}\n"
        f"Extensions: {extensions}\n\n"
        f"Important files:\n"
        + "\n".join(f"- {path}" for path in important[:40])
        + "\n\nSummary:\n"
        + str(project.get("summary", ""))[:4000]
    )


def show_latest_project_profile():
    project = get_latest_deep_project()

    if not project:
        return "No deep project remembered."

    return show_project_profile(project.get("name"))


def smart_project_search(query):
    query = str(query or "").strip()

    if not query:
        return "Missing search query."

    project = find_deep_project(query)

    if project:
        return show_project_profile(project.get("name"))

    tech_result = search_projects_by_technology(query)

    if "No projects found" not in tech_result:
        return tech_result

    keyword_result = find_projects_with_keyword(query)

    if "No remembered projects contain" not in keyword_result:
        return keyword_result

    file_result = find_project_file_global(query)

    if "No file found globally" not in file_result:
        return file_result

    return f"No deep memory result found for: {query}"


def refresh_deep_project(project_name):
    project = find_deep_project(project_name)

    if not project:
        return f"Project not found: {project_name}"

    path = project.get("path")

    if not path or not os.path.exists(path):
        return f"Project path no longer exists: {path}"

    return remember_deep_project(
        project.get("name", project_name),
        path
    )


def refresh_last_deep_project():
    project = get_latest_deep_project()

    if not project:
        return "No deep project remembered."

    return refresh_deep_project(project.get("name"))


def refresh_all_deep_projects():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    results = []

    for project in projects:
        name = project.get("name")
        path = project.get("path")

        if path and os.path.exists(path):
            results.append(remember_deep_project(name, path))
        else:
            results.append(f"Skipped missing project: {name} -> {path}")

    return "\n\n".join(results)


def deep_memory_health():
    projects = _latest_unique_deep_projects()

    if not projects:
        return "No deep projects remembered."

    existing = 0
    missing = 0
    total_files = 0
    tech_counter = {}

    for project in projects:
        if os.path.exists(project.get("path", "")):
            existing += 1
        else:
            missing += 1

        total_files += int(project.get("files_count", 0) or 0)

        for tech in project.get("tech_stack", []):
            tech_counter[tech] = tech_counter.get(tech, 0) + 1

    top_tech = sorted(
        tech_counter.items(),
        key=lambda item: item[1],
        reverse=True
    )[:10]

    return (
        "DEEP MEMORY HEALTH\n\n"
        f"Unique projects: {len(projects)}\n"
        f"Existing paths: {existing}\n"
        f"Missing paths: {missing}\n"
        f"Indexed files total: {total_files}\n"
        f"Most used tech: {', '.join(f'{tech}({count})' for tech, count in top_tech) if top_tech else 'None'}"
    )


def deep_memory_command(command):
    text = str(command or "").strip()
    lower = text.lower()

    if lower in {"deep memory health", "memory health", "project memory health"}:
        return deep_memory_health()

    if lower in {"latest project", "last project", "last deep project"}:
        return last_deep_project()

    if lower in {"continue latest project", "continue last project", "continue last deep project"}:
        return continue_last_deep_project()

    if lower in {"list deep projects", "show deep projects", "remembered projects"}:
        return list_deep_projects()

    match = re.match(r"^(?:find|search|show)\s+(?:project\s+)?(.+)$", text, flags=re.IGNORECASE)

    if match:
        return smart_project_search(match.group(1).strip())

    match = re.match(r"^(?:which|what)\s+projects?\s+(?:use|uses|using)\s+(.+)$", text, flags=re.IGNORECASE)

    if match:
        return search_projects_by_technology(match.group(1).strip())

    match = re.match(r"^find\s+(?:file\s+)?(.+?)\s+(?:globally|in all projects)$", text, flags=re.IGNORECASE)

    if match:
        return find_project_file_global(match.group(1).strip())

    match = re.match(r"^find\s+(?:function|class|symbol)\s+(.+?)\s+(?:globally|in all projects)$", text, flags=re.IGNORECASE)

    if match:
        return find_function_global(match.group(1).strip())

    match = re.match(r"^refresh\s+(?:deep\s+)?project\s+(.+)$", text, flags=re.IGNORECASE)

    if match:
        return refresh_deep_project(match.group(1).strip())

    if lower in {"refresh last project", "refresh latest project"}:
        return refresh_last_deep_project()

    if lower in {"refresh all deep projects", "refresh all projects memory"}:
        return refresh_all_deep_projects()

    return None


# Friendly aliases for jarvis_agent.py and voice commands
def project_memory_health():
    return deep_memory_health()


def latest_project():
    return last_deep_project()


def continue_latest_project():
    return continue_last_deep_project()


def search_project_memory_global(query):
    return smart_project_search(query)


def find_file_everywhere(file_query):
    return find_project_file_global(file_query)


def find_symbol_everywhere(symbol_name):
    return find_function_global(symbol_name)

