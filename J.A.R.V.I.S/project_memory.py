import os
import json
from datetime import datetime

MEMORY_DIR = "memory"
PROJECT_MEMORY_FILE = os.path.join(
    MEMORY_DIR,
    "project_memory.json"
)


# ==========================
# LOAD / SAVE
# ==========================
def load_project_memory():
    if not os.path.exists(PROJECT_MEMORY_FILE):
        return []

    try:
        with open(PROJECT_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_project_memory(data):
    os.makedirs(MEMORY_DIR, exist_ok=True)

    with open(PROJECT_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ==========================
# STORE PROJECT MEMORY
# ==========================
def remember_project(name, description, tags=None, metadata=None):
    if tags is None:
        tags = []

    if metadata is None:
        metadata = {}

    data = load_project_memory()

    data.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "name": name,
        "description": description,
        "tags": tags,
        "metadata": metadata
    })

    save_project_memory(data)

    return f"Project remembered: {name}"


def remember_project_event(project_name, title, content, event_type="project_event", tags=None):
    if tags is None:
        tags = []

    all_tags = ["project", event_type] + tags

    return remember_project(
        project_name,
        f"{title}\n\n{content}",
        tags=all_tags,
        metadata={
            "event_type": event_type,
            "title": title
        }
    )


def remember_project_file(project_name, file_path, action, summary=""):
    return remember_project_event(
        project_name,
        f"{action}: {file_path}",
        summary,
        event_type="file",
        tags=["file", action, file_path],
    )


def remember_project_audit(project_name, audit_title, audit_result):
    return remember_project_event(
        project_name,
        audit_title,
        audit_result,
        event_type="audit",
        tags=["audit", "security", "review"],
    )


# ==========================
# GET PROJECT MEMORY
# ==========================
def get_project_memory(name):
    data = load_project_memory()

    results = []

    for item in data:
        if name.lower() in item.get("name", "").lower():
            results.append(item)

    if not results:
        return "Project not found in memory."

    output = []

    for item in results[-5:]:
        output.append(
            f"Project: {item.get('name', 'Unknown')}\n"
            f"Timestamp: {item.get('timestamp', 'Unknown')}\n\n"
            f"{item.get('description', '')}"
        )

    return "\n\n---\n\n".join(output)


def search_project_memory(keyword):
    data = load_project_memory()

    keyword = keyword.lower()
    results = []

    for item in data:
        text = (
            item.get("name", "") + " " +
            item.get("description", "") + " " +
            " ".join(item.get("tags", [])) + " " +
            json.dumps(item.get("metadata", {}), ensure_ascii=False)
        ).lower()

        if keyword in text:
            results.append(item)

    if not results:
        return "No project memory found."

    output = []

    for item in results[-10:]:
        output.append(
            f"{item.get('timestamp', 'Unknown')} -> "
            f"{item.get('name', 'Unknown')} | "
            f"{item.get('metadata', {}).get('title', item.get('description', '')[:80])}"
        )

    return "\n".join(output)


def show_remembered_projects():
    data = load_project_memory()

    if not data:
        return "No remembered projects."

    seen = set()
    output = []

    for item in reversed(data):
        name = item.get("name", "Unknown")

        if name.lower() not in seen:
            seen.add(name.lower())

            output.append(
                f"{item.get('timestamp', 'Unknown')} -> {name}"
            )

    return "\n".join(output)


def project_memory_stats():
    data = load_project_memory()

    if not data:
        return "Project memories: 0"

    projects = set()

    for item in data:
        name = item.get("name", "").strip()

        if name:
            projects.add(name.lower())

    return (
        f"Project memories: {len(data)}\n"
        f"Unique projects: {len(projects)}"
    )


# ==========================
# STEP 9 - CONVERSATIONAL PROJECT MEMORY
# ==========================
def _latest_project_item(filter_func=None):
    data = load_project_memory()

    for item in reversed(data):
        if filter_func is None or filter_func(item):
            return item

    return None


def _has_tag(item, tag):
    tags = [
        str(x).lower()
        for x in item.get("tags", [])
    ]

    return tag.lower() in tags


def last_project_name():
    item = _latest_project_item()

    if not item:
        return None

    return item.get("name")


def last_project():
    item = _latest_project_item()

    if not item:
        return "No project memory found."

    return (
        f"Last project:\n"
        f"{item.get('name', 'Unknown')}\n\n"
        f"Timestamp: {item.get('timestamp', 'Unknown')}\n"
        f"Summary:\n{item.get('description', '')[:2500]}"
    )


def last_project_file():
    item = _latest_project_item(
        lambda x: _has_tag(x, "file")
        or x.get("metadata", {}).get("event_type") == "file"
    )

    if not item:
        return "No project file memory found."

    return (
        f"Last project file:\n"
        f"Project: {item.get('name', 'Unknown')}\n"
        f"Timestamp: {item.get('timestamp', 'Unknown')}\n\n"
        f"{item.get('description', '')[:2500]}"
    )


def last_project_audit():
    item = _latest_project_item(
        lambda x: _has_tag(x, "audit")
        or x.get("metadata", {}).get("event_type") == "audit"
    )

    if not item:
        return "No project audit memory found."

    return (
        f"Last project audit:\n"
        f"Project: {item.get('name', 'Unknown')}\n"
        f"Timestamp: {item.get('timestamp', 'Unknown')}\n\n"
        f"{item.get('description', '')[:5000]}"
    )


def last_project_security_report():
    item = _latest_project_item(
        lambda x: _has_tag(x, "security")
    )

    if not item:
        return "No project security report found."

    return (
        f"Last project security report:\n"
        f"Project: {item.get('name', 'Unknown')}\n"
        f"Timestamp: {item.get('timestamp', 'Unknown')}\n\n"
        f"{item.get('description', '')[:5000]}"
    )


def continue_last_project_task():
    item = _latest_project_item()

    if not item:
        return "No project task found."

    project_name = item.get("name", "Unknown")
    event_type = item.get("metadata", {}).get("event_type", "project")

    return (
        f"Continue last project task:\n"
        f"Project: {project_name}\n"
        f"Type: {event_type}\n"
        f"Timestamp: {item.get('timestamp', 'Unknown')}\n\n"
        f"Context:\n{item.get('description', '')[:6000]}\n\n"
        f"Suggested next command:\n"
        f"review everything {project_name}\n"
        f"or\n"
        f"autonomous improve {project_name}"
    )


def project_conversation_summary(project_name=None, limit=8):
    data = load_project_memory()

    if project_name:
        data = [
            item for item in data
            if project_name.lower() in item.get("name", "").lower()
        ]

    if not data:
        return "No project conversation memory found."

    output = [
        "Project conversation summary:"
    ]

    for item in data[-limit:]:
        output.append(
            f"- {item.get('timestamp', 'Unknown')} | "
            f"{item.get('name', 'Unknown')} | "
            f"{item.get('metadata', {}).get('event_type', 'project')} | "
            f"{item.get('metadata', {}).get('title', item.get('description', '')[:80])}"
        )

    return "\n".join(output)


def what_was_i_working_on():
    return last_project()


def what_file_did_we_review_last():
    return last_project_file()


def continue_last_audit():
    return last_project_audit()


def show_last_security_report():
    return last_project_security_report()
