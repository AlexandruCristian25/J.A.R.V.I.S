import os
import json

from datetime import datetime

MEMORY_DIR = "memory"

MEMORY_FILE = os.path.join(
    MEMORY_DIR,
    "memory_db.json"
)


# ==========================
# LOAD / SAVE
# ==========================
def load_memory():

    if not os.path.exists(MEMORY_FILE):
        return []

    try:
        with open(
            MEMORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return []


def save_memory(data):

    os.makedirs(
        MEMORY_DIR,
        exist_ok=True
    )

    with open(
        MEMORY_FILE,
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
# STORE MEMORY
# ==========================
def remember(
    memory_type,
    title,
    content,
    tags=None
):

    if tags is None:
        tags = []

    data = load_memory()

    data.append({

        "timestamp":
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "type":
        memory_type,

        "title":
        title,

        "content":
        content,

        "tags":
        tags
    })

    save_memory(data)

    return "Memory stored."


# ==========================
# RECENT
# ==========================
def recent_memories(limit=10):

    data = load_memory()

    if not data:
        return "No memories stored."

    output = []

    for item in data[-limit:]:

        output.append(
            f"[{item['type']}] "
            f"{item['timestamp']} - "
            f"{item['title']}"
        )

    return "\n".join(output)


# ==========================
# SEARCH
# ==========================
def search_memory(keyword):

    keyword = keyword.lower()

    data = load_memory()

    results = []

    for item in data:

        text = (
            item["title"]
            + " "
            + item["content"]
            + " "
            + " ".join(item["tags"])
        ).lower()

        if keyword in text:
            results.append(item)

    if not results:
        return "No memory found."

    output = []

    for item in results[-20:]:

        output.append(
            f"[{item['type']}] "
            f"{item['timestamp']} - "
            f"{item['title']}"
        )

    return "\n".join(output)


# ==========================
# STATS
# ==========================
def memory_stats():

    data = load_memory()

    return (
        f"Total memories: "
        f"{len(data)}"
    )


# ==========================
# INTERNAL
# ==========================
def _find_last_by_tag(tag):

    data = load_memory()

    for item in reversed(data):

        tags = [
            str(x).lower()
            for x in item.get("tags", [])
        ]

        if tag.lower() in tags:
            return item

    return None


# ==========================
# LAST PROJECT
# ==========================
def last_project():

    data = load_memory()

    for item in reversed(data):

        tags = [
            str(x).lower()
            for x in item.get("tags", [])
        ]

        if "project" in tags:

            return (
                f"Last project:\n"
                f"{item['title']}\n\n"
                f"{item['timestamp']}"
            )

    return "No project memory found."


# ==========================
# LAST FILE
# ==========================
def last_file():

    data = load_memory()

    for item in reversed(data):

        tags = [
            str(x).lower()
            for x in item.get("tags", [])
        ]

        if "file" in tags:

            return (
                f"Last file:\n"
                f"{item['title']}\n\n"
                f"{item['timestamp']}"
            )

    return "No file memory found."


# ==========================
# LAST AUDIT
# ==========================
def last_audit():

    item = _find_last_by_tag(
        "audit"
    )

    if not item:
        return "No audit found."

    return (
        f"{item['title']}\n\n"
        f"{item['content'][:4000]}"
    )


# ==========================
# SECURITY REPORT
# ==========================
def last_security_report():

    item = _find_last_by_tag(
        "security"
    )

    if not item:
        return "No security report found."

    return (
        f"{item['title']}\n\n"
        f"{item['content'][:4000]}"
    )


# ==========================
# LAST TASK
# ==========================
def last_task():

    data = load_memory()

    if not data:
        return "No tasks found."

    item = data[-1]

    return (
        f"Last task:\n"
        f"{item['title']}\n\n"
        f"{item['timestamp']}"
    )


# ==========================
# CONTINUE TASK
# ==========================
def continue_last_task():

    data = load_memory()

    if not data:
        return "No task found."

    item = data[-1]

    return (
        f"Continue:\n\n"
        f"{item['title']}\n\n"
        f"{item['content'][:6000]}"
    )


# ==========================
# SUMMARY
# ==========================
def memory_summary(limit=20):

    data = load_memory()

    if not data:
        return "No memory stored."

    output = []

    for item in data[-limit:]:

        output.append(
            f"[{item['type']}] "
            f"{item['title']}"
        )

    return "\n".join(output)