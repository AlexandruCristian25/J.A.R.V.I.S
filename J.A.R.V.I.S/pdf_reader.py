import os
import string
import difflib
import PyPDF2
from llm_local import ask_llm


def normalize_name(name):
    return "".join(ch for ch in name.lower() if ch.isalnum())


def get_available_drives():
    drives = []

    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append(drive)

    return drives


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
}


def find_pdf(name, max_results=30):
    query = normalize_name(name)
    matches = []

    for drive in get_available_drives():
        for root, dirs, files in os.walk(drive, topdown=True):
            dirs[:] = [
                d for d in dirs
                if d.lower() not in SKIP_DIRS
            ]

            for file in files:
                if not file.lower().endswith(".pdf"):
                    continue

                file_name = os.path.splitext(file)[0]
                normalized_file = normalize_name(file_name)

                if query in normalized_file or normalized_file in query:
                    return os.path.join(root, file)

                score = difflib.SequenceMatcher(
                    None,
                    query,
                    normalized_file
                ).ratio()

                if score >= 0.55:
                    matches.append((score, os.path.join(root, file)))

                if len(matches) >= max_results:
                    break

    if matches:
        matches.sort(reverse=True, key=lambda x: x[0])
        return matches[0][1]

    return None


def extract_pdf_text(path, max_pages=5, max_chars=8000):
    if not os.path.exists(path):
        return ""

    text = ""

    try:
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)

            pages = min(len(reader.pages), max_pages)

            for i in range(pages):
                page_text = reader.pages[i].extract_text() or ""
                text += f"\n\n--- PAGE {i + 1} ---\n"
                text += page_text

                if len(text) >= max_chars:
                    break

    except Exception as e:
        return f"PDF read error: {e}"

    return text[:max_chars]


def read_pdf(name):
    pdf_path = find_pdf(name)

    if not pdf_path:
        return f"PDF not found: {name}"

    text = extract_pdf_text(pdf_path)

    if not text.strip():
        return f"No readable text found in PDF: {pdf_path}"

    return f"PDF: {pdf_path}\n\n{text[:3000]}"


def analyze_pdf(name):
    pdf_path = find_pdf(name)

    if not pdf_path:
        return f"PDF not found: {name}"

    text = extract_pdf_text(pdf_path)

    if not text.strip():
        return f"No readable text found in PDF: {pdf_path}"

    prompt = f"""
You are JARVIS, a document analysis assistant.

Analyze this PDF document.

PDF PATH:
{pdf_path}

PDF TEXT:
{text}

Return:
1. Summary
2. Key points
3. Important risks or issues
4. Action items
5. Final recommendation

Be concise and practical.
"""

    return ask_llm(prompt)


def open_pdf(name):
    pdf_path = find_pdf(name)

    if not pdf_path:
        return f"PDF not found: {name}"

    os.startfile(pdf_path)
    return f"Opening PDF: {pdf_path}"