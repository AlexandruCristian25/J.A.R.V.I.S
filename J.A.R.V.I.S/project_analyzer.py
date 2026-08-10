import os
from llm_local import ask_llm

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".css", ".scss", ".json",
    ".java", ".cpp", ".c", ".h", ".cs", ".php"
}

SKIP_DIRS = {
    "node_modules", "venv", ".venv", "jarvis-env",
    "__pycache__", ".git", "dist", "build", ".next",
    "site-packages", ".idea", ".vscode", ".cache"
}

IMPORTANT_FILES = {
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "vite.config.js",
    "next.config.js",
    "angular.json",
    "README.md",
    "readme.md",
}


def collect_project_files(
    project_path,
    max_files=35,
    max_chars_per_file=3500
):
    collected = []

    if not os.path.exists(project_path):
        return collected

    priority_files = []
    normal_files = []

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [
            d for d in dirs
            if d.lower() not in SKIP_DIRS
        ]

        for file in files:
            path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()

            if file in IMPORTANT_FILES:
                priority_files.append(path)
                continue

            if ext in CODE_EXTENSIONS:
                normal_files.append(path)

    ordered_files = priority_files + normal_files

    for path in ordered_files[:max_files]:
        try:
            with open(
                path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:
                content = f.read(max_chars_per_file)

            collected.append({
                "path": path,
                "content": content
            })

        except:
            pass

    return collected


def build_project_tree(project_path, max_items=120):
    tree_lines = []
    count = 0

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [
            d for d in dirs
            if d.lower() not in SKIP_DIRS
        ]

        level = root.replace(project_path, "").count(os.sep)
        indent = "  " * level

        folder_name = os.path.basename(root)
        tree_lines.append(f"{indent}{folder_name}/")
        count += 1

        for file in files:
            if count >= max_items:
                return "\n".join(tree_lines)

            ext = os.path.splitext(file)[1].lower()

            if ext in CODE_EXTENSIONS or file in IMPORTANT_FILES:
                tree_lines.append(f"{indent}  {file}")
                count += 1

    return "\n".join(tree_lines)


def analyze_project(project_name, project_path):
    files = collect_project_files(project_path)
    tree = build_project_tree(project_path)

    if not files:
        return (
            "No readable code files found in this project.\n"
            f"Path checked: {project_path}"
        )

    context = ""

    for item in files:
        context += f"\n\n===== FILE: {item['path']} =====\n"
        context += item["content"]

    prompt = f"""
You are JARVIS, a senior software engineer and cybersecurity code reviewer.

Analyze this project:

PROJECT NAME:
{project_name}

PROJECT PATH:
{project_path}

PROJECT TREE:
{tree}

Your response MUST be structured exactly like this:

# Project Summary
Briefly explain what this project appears to do.

# Detected Technologies
List the frameworks, languages, libraries, and tools you detected.

# Bugs / Logic Problems
List possible bugs or fragile logic. Be specific.

# Security Issues
List security risks, unsafe patterns, exposed secrets, weak validation, unsafe file handling, insecure API usage, etc.

# Performance Issues
List possible performance bottlenecks.

# Code Quality / Architecture
Explain structure, maintainability, naming, duplication, separation of concerns.

# Concrete Improvements
Give clear, practical improvements.

# Priority Fixes
List the top 5 fixes in order of importance.

# Code Quality Score
Give a score from 1 to 10 and explain briefly.

Rules:
- Be practical.
- Do not invent files that are not shown.
- If information is missing, say what is missing.
- Keep the answer concise but useful.

PROJECT FILES:
{context}
"""

    return ask_llm(prompt)