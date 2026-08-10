import os
import shutil
import difflib
from datetime import datetime

from llm_local import ask_llm
from deep_project_memory import load_deep_projects


VERSION = "2.1_FILE_FROM_PROJECT_AND_DIRECT_PATH"
MAX_DIRECT_READ_CHARS = 12000

# ==========================
# HUD / ASSISTANT CONTEXT
# ==========================
HUD_PROJECT_FILE = "hud_project.txt"
HUD_CURRENT_FILE = "hud_current_file.txt"
HUD_ACTION_FILE = "hud_action.txt"
HUD_AI_STATUS_FILE = "hud_ai_status.txt"
HUD_RESULT_FILE = "hud_result.txt"


def write_context_file(path, value):
    try:
        with open(path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(str(value))
    except Exception:
        pass


def update_assistant_context(
    project=None,
    file_path=None,
    action=None,
    ai_status=None,
    result=None
):
    if project is not None:
        write_context_file(HUD_PROJECT_FILE, project)

    if file_path is not None:
        write_context_file(HUD_CURRENT_FILE, file_path)

    if action is not None:
        write_context_file(HUD_ACTION_FILE, action)

    if ai_status is not None:
        write_context_file(HUD_AI_STATUS_FILE, ai_status)

    if result is not None:
        text = str(result).replace("\n", " ").strip()
        write_context_file(HUD_RESULT_FILE, text[:220])




# ==========================
# NORMALIZE
# ==========================
def normalize(text):
    return "".join(
        ch for ch in str(text).lower()
        if ch.isalnum()
    )


def normalize_for_path_match(text):
    return (
        str(text)
        .replace("\\", "/")
        .replace("//", "/")
        .lower()
        .strip()
    )


# ==========================
# DIRECT PATH HELPERS
# ==========================
def normalize_path(path):
    path = path.strip().strip('"').strip("'")
    path = os.path.expandvars(path)
    path = os.path.expanduser(path)
    return path


def is_direct_path(text):
    text = normalize_path(text)

    if os.path.isabs(text):
        return True

    if ":" in text[:4]:
        return True

    if text.startswith("\\\\"):
        return True

    return False


def read_direct_file(path):
    path = normalize_path(path)

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
            content = f.read(MAX_DIRECT_READ_CHARS)

        return content, None

    except Exception as e:
        return None, f"Could not read file: {e}"


def open_direct_file(path):
    path = normalize_path(path)

    if not os.path.exists(path):
        return f"File not found on disk: {path}"

    if not os.path.isfile(path):
        return f"Path is not a file: {path}"

    try:
        os.startfile(path)
        return f"Opening file:\n{path}"

    except Exception as e:
        return f"Could not open file: {e}"


# ==========================
# PROJECT / QUERY PARSING
# ==========================
def parse_file_from_project_query(file_query):
    """
    Supports:
    auth.py from CyberShield AI
    routes/auth.py from CyberShield AI
    routes\\auth.py from CyberShield AI
    G:\\Projects\\App\\auth.py
    """

    text = file_query.strip()

    lower = text.lower()

    if " from " in lower:
        index = lower.rfind(" from ")

        file_part = text[:index].strip()
        project_part = text[index + len(" from "):].strip()

        return file_part, project_part

    return text, None


def find_project_in_deep_memory(project_query):
    data = load_deep_projects()

    if not data:
        return None

    query = normalize(project_query)

    for project in reversed(data):
        name = project.get("name", "")
        path = project.get("path", "")

        candidates = [
            normalize(name),
            normalize(name.replace("_", " ")),
            normalize(name.replace("-", " ")),
            normalize(path)
        ]

        for candidate in candidates:
            if query == candidate:
                return project

        for candidate in candidates:
            if query in candidate or candidate in query:
                return project

    best_project = None
    best_score = 0

    for project in reversed(data):
        name = project.get("name", "")
        path = project.get("path", "")

        candidates = [
            normalize(name),
            normalize(name.replace("_", " ")),
            normalize(name.replace("-", " ")),
            normalize(path)
        ]

        for candidate in candidates:
            score = difflib.SequenceMatcher(
                None,
                query,
                candidate
            ).ratio()

            if score > best_score:
                best_score = score
                best_project = project

    if best_project and best_score >= 0.55:
        return best_project

    return None


# ==========================
# FIND FILE
# ==========================
def file_matches_query(relative_path, file_query):
    relative_norm = normalize_for_path_match(relative_path)
    query_norm_path = normalize_for_path_match(file_query)

    file_name = os.path.basename(relative_norm)
    query_file_name = os.path.basename(query_norm_path)

    query_norm = normalize(file_query)
    rel_norm = normalize(relative_path)
    name_norm = normalize(os.path.basename(relative_path))

    if query_norm_path == relative_norm:
        return 1.0

    if query_norm_path == file_name:
        return 1.0

    if query_file_name == file_name and "/" not in query_norm_path:
        return 1.0

    if query_norm_path in relative_norm:
        return 0.90

    if query_norm == rel_norm:
        return 1.0

    if query_norm == name_norm:
        return 1.0

    if query_norm in rel_norm:
        return 0.85

    if query_norm in name_norm:
        return 0.80

    return 0


def find_file_in_specific_project(project, file_query):
    matches = []

    for file in project.get("files", []):
        relative_path = file.get("relative_path", "")

        score = file_matches_query(relative_path, file_query)

        if score > 0:
            matches.append((project, file, score))

    if len(matches) == 1:
        return matches[0], None

    if len(matches) > 1:
        # Prefer exact full relative path match if available
        exact = [
            item for item in matches
            if normalize_for_path_match(item[1].get("relative_path", ""))
            == normalize_for_path_match(file_query)
        ]

        if len(exact) == 1:
            return exact[0], None

        # Prefer highest score if unique
        matches.sort(key=lambda x: x[2], reverse=True)

        if len(matches) >= 2 and matches[0][2] > matches[1][2]:
            return matches[0], None

        preview = []

        for project, file, score in matches[:15]:
            preview.append(
                f"{project['name']} -> {file['relative_path']}"
            )

        return None, (
            "Multiple files matched. Use a more specific path:\n"
            + "\n".join(preview)
        )

    best = None
    best_score = 0

    query = normalize(file_query)

    for file in project.get("files", []):
        relative_path = file.get("relative_path", "")
        file_name = os.path.basename(relative_path)

        for candidate in [
            normalize(file_name),
            normalize(relative_path),
            normalize_for_path_match(relative_path)
        ]:
            score = difflib.SequenceMatcher(
                None,
                query,
                normalize(candidate)
            ).ratio()

            if score > best_score:
                best_score = score
                best = (project, file, score)

    if best and best_score >= 0.65:
        return best, None

    return None, f"File not found in project: {file_query}"


def find_file_in_deep_memory(file_query):
    file_part, project_part = parse_file_from_project_query(file_query)

    # 1. Direct disk path
    if is_direct_path(file_part):
        return {
            "type": "direct",
            "path": normalize_path(file_part)
        }, None

    # 2. Specific project: <file> from <project>
    if project_part:
        project = find_project_in_deep_memory(project_part)

        if not project:
            return None, f"Project not found in deep memory: {project_part}"

        return find_file_in_specific_project(
            project,
            file_part
        )

    # 3. Search all deep projects
    data = load_deep_projects()

    if not data:
        return None, "No deep projects remembered."

    matches = []

    for project in reversed(data):
        for file in project.get("files", []):
            relative_path = file.get("relative_path", "")

            score = file_matches_query(relative_path, file_part)

            if score > 0:
                matches.append((project, file, score))

    if len(matches) == 1:
        return matches[0], None

    if len(matches) > 1:
        exact = [
            item for item in matches
            if normalize_for_path_match(item[1].get("relative_path", ""))
            == normalize_for_path_match(file_part)
        ]

        if len(exact) == 1:
            return exact[0], None

        matches.sort(key=lambda x: x[2], reverse=True)

        if len(matches) >= 2 and matches[0][2] > matches[1][2]:
            return matches[0], None

        preview = []

        for project, file, score in matches[:15]:
            preview.append(
                f"{project['name']} -> {file['relative_path']}"
            )

        return None, (
            "Multiple files matched. Use one of these formats:\n"
            "read file <file> from <project>\n"
            "read file <full path>\n\n"
            + "\n".join(preview)
        )

    return None, f"File not found in deep memory: {file_query}"


def get_real_file_path(project, file):
    return os.path.join(
        project.get("path", ""),
        file.get("relative_path", "")
    )


# ==========================
# CONTENT RESOLUTION
# ==========================
def resolve_file_content(file_query):
    found, error = find_file_in_deep_memory(file_query)

    if error:
        return None, None, None, error

    if isinstance(found, dict) and found.get("type") == "direct":
        path = found["path"]
        content, read_error = read_direct_file(path)

        if read_error:
            return None, None, None, read_error

        update_assistant_context(
            project="Direct file",
            file_path=path,
            action="Resolved direct file",
            result=path
        )

        return {
            "name": "Direct file",
            "path": os.path.dirname(path)
        }, {
            "relative_path": path,
            "content": content
        }, path, None

    project, file, score = found
    real_path = get_real_file_path(project, file)

    content = file.get("content", "")

    if os.path.exists(real_path) and os.path.isfile(real_path):
        fresh_content, read_error = read_direct_file(real_path)

        if not read_error and fresh_content is not None:
            content = fresh_content

    if not content.strip():
        return None, None, None, "File content is empty."

    update_assistant_context(
        project=project.get("name", "Unknown project"),
        file_path=file.get("relative_path", real_path),
        action="Resolved project file",
        result=real_path
    )

    return project, {
        "relative_path": file.get("relative_path", ""),
        "content": content
    }, real_path, None


# ==========================
# OPEN / READ
# ==========================
def open_memory_file(file_query):
    found, error = find_file_in_deep_memory(file_query)

    if error:
        return error

    if isinstance(found, dict) and found.get("type") == "direct":
        update_assistant_context(
            project="Direct file",
            file_path=found["path"],
            action="Opening direct file",
            result=found["path"]
        )
        return open_direct_file(found["path"])

    project, file, score = found
    real_path = get_real_file_path(project, file)

    if not os.path.exists(real_path):
        return (
            "File exists in memory but not on disk:\n"
            f"{real_path}\n\n"
            "Tip: re-run remember deep project <project> if the project moved."
        )

    try:
        os.startfile(real_path)
        update_assistant_context(
            project=project.get("name", "Unknown project"),
            file_path=file.get("relative_path", real_path),
            action="Opening file",
            result=real_path
        )
        return (
            f"Opening file:\n"
            f"{project['name']} -> {file['relative_path']}"
        )

    except Exception as e:
        return f"Could not open file: {e}"


def read_memory_file(file_query):
    project, file, real_path, error = resolve_file_content(file_query)

    if error:
        return error

    return (
        f"Project: {project['name']}\n"
        f"File: {file['relative_path']}\n"
        f"Path: {real_path}\n\n"
        f"{file['content']}"
    )


# ==========================
# AI REVIEW HELPERS
# ==========================
def build_code_prompt(role, file_query, task):
    project, file, real_path, error = resolve_file_content(file_query)

    if error:
        return None, error

    prompt = f"""
You are JARVIS, {role}.

Use ONLY the code below. Do not invent code that is not visible.

Project:
{project['name']}

File:
{file['relative_path']}

Path:
{real_path}

Code:
{file['content']}

Task:
{task}
"""

    return prompt, None


def analyze_memory_file(file_query):
    prompt, error = build_code_prompt(
        "a senior software engineer and cybersecurity reviewer",
        file_query,
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

Be practical and specific.
"""
    )

    if error:
        return error

    update_assistant_context(
        action="AI file analysis",
        ai_status="THINKING",
        result=f"Running analyze_memory_file on {file_query}"
    )

    result = ask_llm(prompt)

    update_assistant_context(
        action="AI file analysis completed",
        ai_status="READY",
        result=result
    )

    return result


def review_memory_file(file_query):
    prompt, error = build_code_prompt(
        "a strict code reviewer",
        file_query,
        """
Return:
1. Main problems
2. Bugs
3. Security risks
4. Bad practices
5. Refactoring suggestions
6. Priority fixes

Be concise and useful.
"""
    )

    if error:
        return error

    update_assistant_context(
        action="AI file analysis",
        ai_status="THINKING",
        result=f"Running review_memory_file on {file_query}"
    )

    result = ask_llm(prompt)

    update_assistant_context(
        action="AI file analysis completed",
        ai_status="READY",
        result=result
    )

    return result


def improve_memory_file(file_query):
    prompt, error = build_code_prompt(
        "a senior developer",
        file_query,
        """
Improve this real project file without changing its core behavior.

Return:
1. Main weaknesses
2. Better approach
3. Improved code if possible
4. Explanation of changes
5. Any risks

Do not invent unrelated files.
"""
    )

    if error:
        return error

    update_assistant_context(
        action="AI file analysis",
        ai_status="THINKING",
        result=f"Running improve_memory_file on {file_query}"
    )

    result = ask_llm(prompt)

    update_assistant_context(
        action="AI file analysis completed",
        ai_status="READY",
        result=result
    )

    return result


def optimize_memory_file(file_query):
    prompt, error = build_code_prompt(
        "a performance-focused software engineer",
        file_query,
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

    update_assistant_context(
        action="AI file analysis",
        ai_status="THINKING",
        result=f"Running optimize_memory_file on {file_query}"
    )

    result = ask_llm(prompt)

    update_assistant_context(
        action="AI file analysis completed",
        ai_status="READY",
        result=result
    )

    return result


def security_review_memory_file(file_query):
    prompt, error = build_code_prompt(
        "a cybersecurity code reviewer",
        file_query,
        """
Perform a security review.

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

    update_assistant_context(
        action="AI file analysis",
        ai_status="THINKING",
        result=f"Running security_review_memory_file on {file_query}"
    )

    result = ask_llm(prompt)

    update_assistant_context(
        action="AI file analysis completed",
        ai_status="READY",
        result=result
    )

    return result


# ==========================
# SAFE CODE EDIT + BACKUP
# ==========================
BACKUP_ROOT = "file_backups"


def ensure_backup_dir():
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    return BACKUP_ROOT


def create_file_backup(file_query):
    """
    Creates a timestamped backup for a resolved file.
    Does not modify the original file.
    """

    project, file, real_path, error = resolve_file_content(file_query)

    if error:
        return error

    if not real_path or not os.path.exists(real_path):
        return f"Cannot create backup. File not found on disk: {real_path}"

    if not os.path.isfile(real_path):
        return f"Cannot create backup. Path is not a file: {real_path}"

    ensure_backup_dir()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_project = normalize(project.get("name", "project")) or "project"
    safe_file = normalize(os.path.basename(real_path)) or "file"

    backup_name = f"{safe_project}_{safe_file}_{timestamp}.bak"
    backup_path = os.path.join(BACKUP_ROOT, backup_name)

    try:
        shutil.copy2(real_path, backup_path)

        update_assistant_context(
            project=project.get("name", "Unknown project"),
            file_path=real_path,
            action="Backup created",
            result=backup_path
        )

        return (
            "Backup created successfully.\n"
            f"Original: {real_path}\n"
            f"Backup: {os.path.abspath(backup_path)}"
        )

    except Exception as e:
        return f"Could not create backup: {e}"


def get_resolved_file_path(file_query):
    project, file, real_path, error = resolve_file_content(file_query)

    if error:
        return None, error

    if not real_path or not os.path.exists(real_path):
        return None, f"File not found on disk: {real_path}"

    if not os.path.isfile(real_path):
        return None, f"Path is not a file: {real_path}"

    return real_path, None


def safe_write_file(file_query, new_content):
    """
    Writes content safely:
    1. Resolves the file.
    2. Creates backup.
    3. Writes new content.
    """

    real_path, error = get_resolved_file_path(file_query)

    if error:
        return error

    backup_result = create_file_backup(file_query)

    if not backup_result.startswith("Backup created successfully."):
        return backup_result

    try:
        with open(real_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(str(new_content))

        return (
            "Safe write completed.\n"
            f"{backup_result}\n"
            f"Updated file: {real_path}"
        )

    except Exception as e:
        return f"Backup was created, but file write failed: {e}"


def build_safe_improvement_plan(file_query):
    """
    Generates a safe improvement plan.
    Does NOT modify code.
    """

    prompt, error = build_code_prompt(
        "a strict senior developer and code safety reviewer",
        file_query,
        """
Analyze this file and return ONLY a safe edit plan.

Return:
1. What should be changed
2. Why it should be changed
3. Exact functions/sections affected
4. Risks
5. Backup recommendation
6. A patch-style proposal, but do NOT claim it was applied

Important:
- Do not invent other files.
- Do not say you changed anything.
- Do not output unrelated code.
"""
    )

    if error:
        return error

    return ask_llm(prompt)


def suggest_safe_patch_for_file(file_query):
    """
    Suggests a patch but does not apply it.
    """

    return build_safe_improvement_plan(file_query)


def apply_safe_full_replacement(file_query, new_content):
    """
    Applies a full file replacement after backup.
    This should only be called after user confirmation.
    """

    if not str(new_content).strip():
        return "Refused: new content is empty."

    return safe_write_file(file_query, new_content)


def restore_latest_backup(file_query):
    """
    Restores the latest backup matching the resolved file/project.
    """

    project, file, real_path, error = resolve_file_content(file_query)

    if error:
        return error

    if not os.path.isdir(BACKUP_ROOT):
        return "No backups folder found."

    safe_project = normalize(project.get("name", "project")) or "project"
    safe_file = normalize(os.path.basename(real_path)) or "file"

    prefix = f"{safe_project}_{safe_file}_"

    candidates = [
        os.path.join(BACKUP_ROOT, name)
        for name in os.listdir(BACKUP_ROOT)
        if name.startswith(prefix) and name.endswith(".bak")
    ]

    if not candidates:
        return f"No backup found for: {real_path}"

    candidates.sort(reverse=True)
    latest_backup = candidates[0]

    try:
        shutil.copy2(latest_backup, real_path)

        update_assistant_context(
            project=project.get("name", "Unknown project"),
            file_path=real_path,
            action="Backup restored",
            result=latest_backup
        )

        return (
            "Latest backup restored.\n"
            f"Backup: {os.path.abspath(latest_backup)}\n"
            f"Restored file: {real_path}"
        )

    except Exception as e:
        return f"Could not restore backup: {e}"


def list_file_backups():
    if not os.path.isdir(BACKUP_ROOT):
        return "No backups folder found."

    backups = [
        name for name in os.listdir(BACKUP_ROOT)
        if name.endswith(".bak")
    ]

    if not backups:
        return "No backups found."

    backups.sort(reverse=True)

    output = [
        f"Backups found: {len(backups)}"
    ]

    for name in backups[:50]:
        output.append(
            f" - {name}"
        )

    if len(backups) > 50:
        output.append(
            f"... and {len(backups) - 50} more"
        )

    return "\n".join(output)


# ==========================
# CONTEXT DISPLAY HELPERS
# ==========================
def get_current_file_context():
    project = ""
    file_path = ""
    action = ""
    ai_status = ""

    for path, var_name in [
        (HUD_PROJECT_FILE, "project"),
        (HUD_CURRENT_FILE, "file_path"),
        (HUD_ACTION_FILE, "action"),
        (HUD_AI_STATUS_FILE, "ai_status"),
    ]:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                value = f.read().strip()
        except Exception:
            value = ""

        if var_name == "project":
            project = value
        elif var_name == "file_path":
            file_path = value
        elif var_name == "action":
            action = value
        elif var_name == "ai_status":
            ai_status = value

    return (
        f"Project: {project or 'Not set'}\n"
        f"File: {file_path or 'Not set'}\n"
        f"Action: {action or 'Not set'}\n"
        f"AI: {ai_status or 'Not set'}"
    )
