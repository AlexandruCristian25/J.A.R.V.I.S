import os
import json
from datetime import datetime

MEMORY_DIR = "memory"
MEMORY_FILE = os.path.join(
    MEMORY_DIR,
    "screenshots_db.json"
)


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


def remember_screenshot(
    image_path,
    ocr_text,
    summary
):

    data = load_memory()

    data.append({

        "timestamp":
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),

        "image":
        image_path,

        "ocr_text":
        ocr_text,

        "summary":
        summary
    })

    save_memory(data)

    return "Screenshot remembered."


def get_last_screenshot():

    data = load_memory()

    if not data:
        return "No screenshots remembered."

    last = data[-1]

    return (
        f"Timestamp: {last['timestamp']}\n\n"
        f"Summary:\n{last['summary']}"
    )


def search_screenshots(keyword):

    keyword = keyword.lower()

    data = load_memory()

    results = []

    for item in data:

        text = (
            item["ocr_text"]
            + " "
            + item["summary"]
        ).lower()

        if keyword in text:
            results.append(item)

    if not results:
        return "No matching screenshots found."

    output = []

    for item in results[-10:]:

        output.append(
            f"{item['timestamp']} -> "
            f"{item['summary']}"
        )

    return "\n".join(output)