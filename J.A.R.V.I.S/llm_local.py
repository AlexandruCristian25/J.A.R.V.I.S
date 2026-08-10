import os
import shutil
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434

OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_VERSION_URL = f"{OLLAMA_BASE_URL}/api/version"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

DEFAULT_MODEL = "llama3.2:3b"
MODELS = [DEFAULT_MODEL]

REQUEST_TIMEOUT = 90
HEALTH_TIMEOUT = 3
SERVER_START_TIMEOUT = 18
REPAIR_WAIT_SECONDS = 1.0

DEFAULT_LLM_LIBRARY = "cpu"

KNOWN_OLLAMA_PATHS = [
    r"C:\Users\Student\AppData\Local\Programs\Ollama\ollama.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
    "ollama",
]

SYSTEM_PROMPT = """
You are JARVIS, a local AI assistant.

Rules:
- Reply directly.
- Be concise.
- Do not expose chain of thought.
- Do not explain internal reasoning.
- Give practical answers.
- When reviewing code, be specific and practical.
- When something is not visible in the provided code/context, say that it is not visible.
"""


def write_hud_file(path: str, value: str) -> None:
    try:
        with open(path, "w", encoding="utf-8", errors="ignore") as file:
            file.write(str(value))
    except Exception:
        pass


def update_llm_hud(status: str, result: str = "") -> None:
    write_hud_file("hud_ollama_status.txt", status)
    write_hud_file("hud_ai_status.txt", status)

    if result:
        write_hud_file("hud_result.txt", str(result).replace("\n", " ")[:220])


def find_ollama_exe() -> Optional[str]:
    for candidate in KNOWN_OLLAMA_PATHS:
        expanded = os.path.expandvars(candidate)

        if expanded.lower() == "ollama":
            found = shutil.which("ollama")

            if found:
                return found

            continue

        if os.path.exists(expanded):
            return expanded

    return shutil.which("ollama")


def port_is_open(host: str = OLLAMA_HOST, port: int = OLLAMA_PORT, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def get_pid_using_port(port: int = OLLAMA_PORT) -> Optional[int]:
    try:
        completed = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=10,
        )

        for line in completed.stdout.splitlines():
            lower = line.lower()

            if f":{port}" not in lower:
                continue

            if "listening" not in lower:
                continue

            parts = line.split()

            if parts and parts[-1].isdigit():
                return int(parts[-1])

    except Exception:
        return None

    return None


def kill_pid(pid: int) -> bool:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def kill_known_ollama_processes() -> None:
    for process_name in ["ollama.exe", "llama-server.exe"]:
        try:
            subprocess.run(
                ["taskkill", "/IM", process_name, "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass


def stop_ollama_server() -> bool:
    update_llm_hud("REPAIR", "Stopping broken Ollama server...")

    pid = get_pid_using_port(OLLAMA_PORT)

    if pid:
        kill_pid(pid)
        time.sleep(REPAIR_WAIT_SECONDS)

    kill_known_ollama_processes()
    time.sleep(REPAIR_WAIT_SECONDS)

    pid = get_pid_using_port(OLLAMA_PORT)

    if pid:
        kill_pid(pid)
        time.sleep(REPAIR_WAIT_SECONDS)

    return not port_is_open()


def ollama_alive() -> bool:
    try:
        response = requests.get(OLLAMA_VERSION_URL, timeout=HEALTH_TIMEOUT)
        return response.status_code == 200
    except Exception:
        return False


def start_ollama_server_cpu() -> bool:
    ollama_exe = find_ollama_exe()

    if not ollama_exe:
        update_llm_hud("ERROR", "ollama.exe not found.")
        return False

    update_llm_hud("REPAIR", "Starting Ollama with CPU runner...")

    env = os.environ.copy()
    env["OLLAMA_HOST"] = f"{OLLAMA_HOST}:{OLLAMA_PORT}"
    env["OLLAMA_LLM_LIBRARY"] = DEFAULT_LLM_LIBRARY

    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=creationflags,
        )
    except Exception as error:
        update_llm_hud("ERROR", f"Could not start Ollama: {error}")
        return False

    start = time.time()

    while time.time() - start < SERVER_START_TIMEOUT:
        if ollama_alive():
            update_llm_hud("READY", "Ollama CPU server started.")
            return True

        time.sleep(0.7)

    update_llm_hud("ERROR", "Ollama did not start in time.")
    return False


def ollama_version() -> str:
    try:
        response = requests.get(OLLAMA_VERSION_URL, timeout=HEALTH_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return str(data.get("version", "unknown"))
    except Exception as error:
        return f"unavailable ({error})"


def get_installed_models() -> List[str]:
    try:
        response = requests.get(OLLAMA_TAGS_URL, timeout=8)
        response.raise_for_status()

        data = response.json()
        models = data.get("models", [])

        names = []

        for item in models:
            name = item.get("name") or item.get("model")

            if name:
                names.append(str(name))

        return sorted(set(names))

    except Exception:
        return []


def resolve_model_name(preferred_model: Optional[str] = None) -> Optional[str]:
    installed = get_installed_models()

    if not installed:
        return None

    preferred = preferred_model or DEFAULT_MODEL

    if preferred in installed:
        return preferred

    preferred_base = preferred.split(":")[0].lower()

    for model in installed:
        if model.split(":")[0].lower() == preferred_base:
            return model

    for model in MODELS:
        if model in installed:
            return model

    return installed[0]


def ollama_status_report() -> str:
    installed = get_installed_models()
    model = resolve_model_name()
    pid = get_pid_using_port(OLLAMA_PORT)

    lines = [
        "OLLAMA STATUS",
        f"Alive: {ollama_alive()}",
        f"Version: {ollama_version()}",
        "Installed models: " + (", ".join(installed) if installed else "None"),
        f"Selected model: {model or 'None'}",
        f"Base URL: {OLLAMA_BASE_URL}",
        f"Port PID: {pid or 'None'}",
        f"Ollama EXE: {find_ollama_exe() or 'Not found'}",
        f"Repair library: {DEFAULT_LLM_LIBRARY}",
    ]

    return "\n".join(lines)


def ask_model_chat(model_name: str, prompt: str) -> str:
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": str(prompt)},
        ],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 1200,
        },
    }

    response = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    data = response.json()

    return data.get("message", {}).get("content", "").strip()


def ask_model_generate(model_name: str, prompt: str) -> str:
    full_prompt = SYSTEM_PROMPT.strip() + "\n\nUser request:\n" + str(prompt)

    payload: Dict[str, Any] = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 1200,
        },
    }

    response = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    data = response.json()

    return str(data.get("response", "")).strip()


def ask_model_cli(model_name: str, prompt: str) -> str:
    ollama_exe = find_ollama_exe()

    if not ollama_exe:
        raise RuntimeError("ollama.exe not found")

    full_prompt = SYSTEM_PROMPT.strip() + "\n\nUser request:\n" + str(prompt)

    env = os.environ.copy()
    env["OLLAMA_LLM_LIBRARY"] = DEFAULT_LLM_LIBRARY

    completed = subprocess.run(
        [ollama_exe, "run", model_name, full_prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=240,
        env=env,
    )

    if completed.returncode != 0:
        error = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(error or "ollama CLI failed")

    return completed.stdout.strip()


def ask_model(model_name: str, prompt: str) -> str:
    errors = []

    try:
        result = ask_model_chat(model_name, prompt)

        if result:
            return result

        errors.append("chat: empty response")
    except Exception as error:
        errors.append(f"chat: {error}")

    try:
        result = ask_model_generate(model_name, prompt)

        if result:
            return result

        errors.append("generate: empty response")
    except Exception as error:
        errors.append(f"generate: {error}")

    try:
        result = ask_model_cli(model_name, prompt)

        if result:
            return result

        errors.append("cli: empty response")
    except Exception as error:
        errors.append(f"cli: {error}")

    raise RuntimeError(f"Model {model_name} failed. " + " | ".join(errors))


def test_model_generation(model_name: Optional[str] = None) -> Tuple[bool, str]:
    selected = model_name or resolve_model_name()

    if not selected:
        return False, "No model selected."

    try:
        result = ask_model_generate(selected, "Reply with OK using one word.")

        if result and "ok" in result.lower():
            return True, f"Model test OK through generate: {selected}"

        if result:
            return True, f"Model responded through generate: {result[:80]}"

        return False, "Model returned empty response."
    except Exception as error:
        return False, str(error)


def ensure_ollama_ready(auto_repair: bool = True) -> Tuple[bool, str]:
    update_llm_hud("CHECKING", "Checking Ollama health...")

    if not ollama_alive():
        if not auto_repair:
            return False, "Ollama is offline."

        stop_ollama_server()

        if not start_ollama_server_cpu():
            return False, "Ollama could not be started automatically."

    installed = get_installed_models()

    if not installed:
        return False, (
            "Ollama is running, but no model is installed.\n"
            f"Run: ollama pull {DEFAULT_MODEL}"
        )

    selected = resolve_model_name()

    if not selected:
        return False, "No usable Ollama model could be selected."

    ok, message = test_model_generation(selected)

    if ok:
        update_llm_hud("READY", message)
        return True, message

    if not auto_repair:
        update_llm_hud("ERROR", message)
        return False, message

    update_llm_hud("REPAIR", "Ollama model test failed. Restarting CPU server...")

    stop_ollama_server()

    if not start_ollama_server_cpu():
        return False, "Ollama repair failed: could not restart server."

    time.sleep(1.5)

    ok, second_message = test_model_generation(selected)

    if ok:
        update_llm_hud("READY", "Ollama repaired successfully.")
        return True, "Ollama repaired successfully. " + second_message

    update_llm_hud("ERROR", second_message)

    return False, (
        "Ollama repair was attempted, but model still fails.\n"
        f"Last error: {second_message}"
    )


def ask_llm(prompt: str, model_name: Optional[str] = None) -> str:
    ready, ready_message = ensure_ollama_ready(auto_repair=True)

    if not ready:
        return ready_message

    installed = get_installed_models()
    selected_model = resolve_model_name(model_name)

    if not selected_model:
        update_llm_hud("NO MODEL", "Could not select model.")
        return "Could not select an Ollama model."

    update_llm_hud("THINKING", f"Using {selected_model}")

    try:
        answer = ask_model(selected_model, prompt)
        update_llm_hud("READY", "Ollama response completed.")
        return answer
    except Exception as error:
        update_llm_hud("REPAIR", "LLM request failed. Repairing Ollama...")

        repaired, repair_message = ensure_ollama_ready(auto_repair=True)

        if repaired:
            try:
                answer = ask_model(selected_model, prompt)
                update_llm_hud("READY", "Ollama response completed after repair.")
                return answer
            except Exception as second_error:
                error = second_error

        update_llm_hud("ERROR", str(error))

        return (
            "All configured models failed.\n"
            f"Ollama version: {ollama_version()}\n"
            f"Installed models: {', '.join(installed)}\n"
            f"Selected model: {selected_model}\n"
            f"Repair result: {repair_message if 'repair_message' in locals() else 'N/A'}\n"
            f"Last error: {error}"
        )


def warmup_models() -> str:
    lines = [
        ollama_status_report(),
        "",
        "AUTO-REPAIR TEST:",
    ]

    ready, message = ensure_ollama_ready(auto_repair=True)
    lines.append(f"ensure_ollama_ready -> {ready}: {message}")

    lines.extend(["", "MODEL TESTS:"])

    if not ready:
        return "\n".join(lines)

    selected = resolve_model_name()

    if not selected:
        lines.append("No usable model found.")
        return "\n".join(lines)

    try:
        reply = ask_model_chat(selected, "Reply with OK using one word.")
        lines.append(f"{selected} / chat -> OK ({reply[:80]})")
    except Exception as error:
        lines.append(f"{selected} / chat -> FAILED ({error})")

    try:
        reply = ask_model_generate(selected, "Reply with OK using one word.")
        lines.append(f"{selected} / generate -> OK ({reply[:80]})")
    except Exception as error:
        lines.append(f"{selected} / generate -> FAILED ({error})")

    try:
        reply = ask_llm("Reply with OK using one word.", model_name=selected)
        lines.append(f"{selected} / full ask_llm -> OK ({reply[:80]})")
    except Exception as error:
        lines.append(f"{selected} / full ask_llm -> FAILED ({error})")

    return "\n".join(lines)


# ==========================================================
# J.A.R.V.I.S MARK XLVII ENTERPRISE LLM CORE
# Appended safely before __main__.
# ==========================================================

import hashlib
from datetime import datetime

MARK47_LLM_VERSION = "J.A.R.V.I.S Mark XLVII Enterprise LLM Core"

LLM_LOG_DIR = "logs"
LLM_LOG_FILE = os.path.join(LLM_LOG_DIR, "llm.log")
LLM_CACHE_FILE = "llm_response_cache.json"
LLM_STATS_FILE = "llm_stats.json"
LLM_CIRCUIT_FILE = "llm_circuit_breaker.json"

LLM_CACHE_ENABLED = True
LLM_CACHE_MAX_ITEMS = 150
LLM_CACHE_MAX_PROMPT_CHARS = 25000
LLM_CACHE_TTL_SECONDS = 60 * 60 * 24

LLM_MAX_CONTEXT_CHARS = 28000
LLM_RETRY_ATTEMPTS = 2
LLM_RETRY_BASE_DELAY = 0.45
LLM_CIRCUIT_FAILURE_LIMIT = 3
LLM_CIRCUIT_COOLDOWN_SECONDS = 20

LLM_PROFILE = os.environ.get("JARVIS_LLM_PROFILE", "fast").lower().strip()

LLM_PROFILES = {
    "fast": {"temperature": 0.2, "num_predict": 450, "timeout_factor": 0.55, "prefer": ["1.5b", "3b"]},
    "balanced": {"temperature": 0.3, "num_predict": 850, "timeout_factor": 0.85, "prefer": ["3b", "7b", "8b"]},
    "quality": {"temperature": 0.25, "num_predict": 1500, "timeout_factor": 1.25, "prefer": ["8b", "7b", "14b", "3b"]},
    "code": {"temperature": 0.15, "num_predict": 1200, "timeout_factor": 1.05, "prefer": ["coder", "code", "qwen", "deepseek", "llama"]},
}


def _m47_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _m47_safe_load(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            return json.load(file)
    except Exception:
        return default if default is not None else {}


def _m47_safe_save(path: str, data) -> bool:
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def llm_log(message: str, level: str = "INFO") -> None:
    try:
        os.makedirs(LLM_LOG_DIR, exist_ok=True)
        with open(LLM_LOG_FILE, "a", encoding="utf-8", errors="ignore") as file:
            file.write(f"[{_m47_now()}] [{level}] {message}\n")
    except Exception:
        pass


def _m47_hash_prompt(prompt: str, model: str, profile: str) -> str:
    raw = f"{model}|{profile}|{str(prompt)}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _m47_cache_get(prompt: str, model: str, profile: str) -> Optional[str]:
    if not LLM_CACHE_ENABLED or len(str(prompt)) > LLM_CACHE_MAX_PROMPT_CHARS:
        return None

    data = _m47_safe_load(LLM_CACHE_FILE, {})
    if not isinstance(data, dict):
        return None

    item = data.get(_m47_hash_prompt(prompt, model, profile))
    if not item:
        return None

    created = int(item.get("created", 0) or 0)
    if time.time() - created > LLM_CACHE_TTL_SECONDS:
        return None

    answer = item.get("answer", "")
    if answer:
        llm_log(f"Cache hit model={model} profile={profile}")
        return answer
    return None


def _m47_cache_set(prompt: str, model: str, profile: str, answer: str) -> None:
    if not LLM_CACHE_ENABLED or len(str(prompt)) > LLM_CACHE_MAX_PROMPT_CHARS:
        return
    if not answer or "All configured models failed" in str(answer):
        return

    data = _m47_safe_load(LLM_CACHE_FILE, {})
    if not isinstance(data, dict):
        data = {}

    data[_m47_hash_prompt(prompt, model, profile)] = {
        "created": int(time.time()),
        "model": model,
        "profile": profile,
        "prompt_preview": str(prompt)[:300],
        "answer": str(answer),
    }

    if len(data) > LLM_CACHE_MAX_ITEMS:
        items = sorted(data.items(), key=lambda pair: int(pair[1].get("created", 0) or 0), reverse=True)
        data = dict(items[:LLM_CACHE_MAX_ITEMS])

    _m47_safe_save(LLM_CACHE_FILE, data)


def _m47_stats_update(success: bool, model: str = "", profile: str = "", elapsed: float = 0.0, error: str = "") -> None:
    data = _m47_safe_load(LLM_STATS_FILE, {})
    if not isinstance(data, dict):
        data = {}

    data["total_requests"] = int(data.get("total_requests", 0) or 0) + 1
    data["last_request"] = _m47_now()
    data["last_model"] = model
    data["last_profile"] = profile
    data["last_elapsed_seconds"] = round(float(elapsed or 0.0), 3)

    if success:
        data["successful_requests"] = int(data.get("successful_requests", 0) or 0) + 1
    else:
        data["failed_requests"] = int(data.get("failed_requests", 0) or 0) + 1
        data["last_error"] = str(error)[-1200:]

    model_stats = data.get("models", {})
    if not isinstance(model_stats, dict):
        model_stats = {}

    item = model_stats.get(model, {})
    item["requests"] = int(item.get("requests", 0) or 0) + 1
    item["success"] = int(item.get("success", 0) or 0) + (1 if success else 0)
    item["failed"] = int(item.get("failed", 0) or 0) + (0 if success else 1)
    item["last_elapsed_seconds"] = round(float(elapsed or 0.0), 3)
    model_stats[model] = item
    data["models"] = model_stats
    _m47_safe_save(LLM_STATS_FILE, data)


def _m47_circuit_state():
    data = _m47_safe_load(LLM_CIRCUIT_FILE, {})
    return data if isinstance(data, dict) else {}


def _m47_circuit_is_open() -> Tuple[bool, str]:
    data = _m47_circuit_state()
    failures = int(data.get("failures", 0) or 0)
    opened_at = int(data.get("opened_at", 0) or 0)

    if failures < LLM_CIRCUIT_FAILURE_LIMIT:
        return False, "closed"

    elapsed = int(time.time()) - opened_at
    if elapsed >= LLM_CIRCUIT_COOLDOWN_SECONDS:
        return False, "cooldown expired"

    return True, f"circuit open, cooldown {LLM_CIRCUIT_COOLDOWN_SECONDS - elapsed}s"


def _m47_circuit_success() -> None:
    _m47_safe_save(LLM_CIRCUIT_FILE, {"failures": 0, "opened_at": 0, "last_success": int(time.time()), "status": "closed"})


def _m47_circuit_failure(error: str) -> None:
    data = _m47_circuit_state()
    failures = int(data.get("failures", 0) or 0) + 1
    payload = {
        "failures": failures,
        "last_error": str(error)[-1200:],
        "last_failure": int(time.time()),
        "status": "closed",
        "opened_at": int(data.get("opened_at", 0) or 0),
    }
    if failures >= LLM_CIRCUIT_FAILURE_LIMIT:
        payload["opened_at"] = int(time.time())
        payload["status"] = "open"
    _m47_safe_save(LLM_CIRCUIT_FILE, payload)


def optimize_prompt_context(prompt: str, max_chars: int = LLM_MAX_CONTEXT_CHARS) -> str:
    text = str(prompt or "")
    if len(text) <= max_chars:
        return text

    head_size = int(max_chars * 0.45)
    tail_size = int(max_chars * 0.45)
    note = "\n\n[Context optimized by J.A.R.V.I.S Mark XLVII: middle content removed to keep the local model stable.]\n\n"
    return text[:head_size] + note + text[-tail_size:]


def adaptive_timeout(prompt: str, profile: Optional[str] = None) -> int:
    profile = (profile or LLM_PROFILE or "balanced").lower()
    settings = LLM_PROFILES.get(profile, LLM_PROFILES["balanced"])
    length = len(str(prompt or ""))

    if length > 50000:
        base = 300
    elif length > 25000:
        base = 240
    elif length > 10000:
        base = 210
    elif length < 2000:
        base = 120
    else:
        base = REQUEST_TIMEOUT

    return max(60, min(420, int(base * float(settings.get("timeout_factor", 1.0)))))


def detect_prompt_type(prompt: str) -> str:
    lower = str(prompt or "").lower()
    if any(token in lower for token in ["traceback", "error:", "exception", "def ", "class ", "function ", "review code", "improve code", "safe patch", "```"]):
        return "code"
    if any(token in lower for token in ["architecture", "roadmap", "security audit", "vulnerability"]):
        return "quality"
    if len(lower) < 500:
        return "fast"
    return LLM_PROFILE or "balanced"


def get_profile_settings(profile: Optional[str] = None) -> Dict[str, Any]:
    resolved = (profile or LLM_PROFILE or "balanced").lower().strip()
    return LLM_PROFILES.get(resolved, LLM_PROFILES["balanced"])


def choose_model_for_prompt(prompt: str, preferred_model: Optional[str] = None, profile: Optional[str] = None) -> Optional[str]:
    installed = get_installed_models()
    if not installed:
        return None

    if preferred_model:
        resolved = resolve_model_name(preferred_model)
        if resolved:
            return resolved

    profile = (profile or detect_prompt_type(prompt)).lower().strip()
    preferences = get_profile_settings(profile).get("prefer", [])
    installed_lower = [(model, model.lower()) for model in installed]

    for pref in preferences:
        pref = str(pref).lower()
        for model, lower in installed_lower:
            if pref in lower:
                return model

    return resolve_model_name() or installed[0]


def _m47_options(profile: Optional[str] = None) -> Dict[str, Any]:
    settings = get_profile_settings(profile)
    return {"temperature": settings.get("temperature", 0.3), "num_predict": settings.get("num_predict", 1200)}


def ask_model_chat_enterprise(model_name: str, prompt: str, profile: Optional[str] = None) -> str:
    prompt = optimize_prompt_context(prompt)
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT.strip()}, {"role": "user", "content": str(prompt)}],
        "stream": False,
        "options": _m47_options(profile),
    }
    response = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=adaptive_timeout(prompt, profile))
    response.raise_for_status()
    data = response.json()
    return data.get("message", {}).get("content", "").strip()


def ask_model_generate_enterprise(model_name: str, prompt: str, profile: Optional[str] = None) -> str:
    prompt = optimize_prompt_context(prompt)
    full_prompt = SYSTEM_PROMPT.strip() + "\n\nUser request:\n" + str(prompt)
    payload: Dict[str, Any] = {"model": model_name, "prompt": full_prompt, "stream": False, "options": _m47_options(profile)}
    response = requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=adaptive_timeout(prompt, profile))
    response.raise_for_status()
    data = response.json()
    return str(data.get("response", "")).strip()


def ask_model_stream_generate(model_name: str, prompt: str, profile: Optional[str] = None):
    prompt = optimize_prompt_context(prompt)
    full_prompt = SYSTEM_PROMPT.strip() + "\n\nUser request:\n" + str(prompt)
    payload: Dict[str, Any] = {"model": model_name, "prompt": full_prompt, "stream": True, "options": _m47_options(profile)}

    with requests.post(OLLAMA_GENERATE_URL, json=payload, timeout=adaptive_timeout(prompt, profile), stream=True) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line.decode("utf-8", errors="ignore"))
                chunk = data.get("response", "")
                if chunk:
                    yield chunk
                if data.get("done"):
                    break
            except Exception:
                continue


def ask_model_enterprise(model_name: str, prompt: str, profile: Optional[str] = None) -> str:
    errors = []
    methods = [
        ("generate", ask_model_generate_enterprise),
        ("chat", ask_model_chat_enterprise),
        ("cli", lambda m, p, profile=None: ask_model_cli(m, optimize_prompt_context(p))),
    ]

    for method_name, method in methods:
        try:
            result = method(model_name, prompt, profile=profile)
            if result:
                llm_log(f"{method_name} success model={model_name}")
                return result
            errors.append(f"{method_name}: empty response")
        except Exception as error:
            errors.append(f"{method_name}: {error}")
            llm_log(f"{method_name} failed model={model_name}: {error}", level="WARN")

    raise RuntimeError(f"Model {model_name} failed. " + " | ".join(errors))


def _m47_retry_call(fn, attempts: int = LLM_RETRY_ATTEMPTS):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as error:
            last_error = error
            delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            llm_log(f"Retry {attempt}/{attempts} failed: {error}. Sleeping {delay:.1f}s", level="WARN")
            time.sleep(delay)
    raise last_error


def ask_llm_enterprise(prompt: str, model_name: Optional[str] = None, profile: Optional[str] = None, use_cache: bool = True) -> str:
    start_time = time.time()
    prompt = optimize_prompt_context(prompt)
    profile = (profile or detect_prompt_type(prompt)).lower().strip()

    is_open, reason = _m47_circuit_is_open()
    if is_open:
        message = f"Ollama circuit breaker is temporarily open.\nReason: {reason}\nWait a few seconds, then try again or run: repair"
        update_llm_hud("CIRCUIT OPEN", message)
        llm_log(message, level="ERROR")
        return message

    ready, ready_message = ensure_ollama_ready(auto_repair=True)
    if not ready:
        _m47_circuit_failure(ready_message)
        _m47_stats_update(False, profile=profile, elapsed=time.time() - start_time, error=ready_message)
        return ready_message

    selected_model = choose_model_for_prompt(prompt, preferred_model=model_name, profile=profile)
    if not selected_model:
        message = "Could not select an Ollama model."
        _m47_circuit_failure(message)
        _m47_stats_update(False, profile=profile, elapsed=time.time() - start_time, error=message)
        return message

    cached = _m47_cache_get(prompt, selected_model, profile) if use_cache else None
    if cached:
        _m47_stats_update(True, model=selected_model, profile=profile, elapsed=time.time() - start_time)
        update_llm_hud("READY", "Returned cached LLM response.")
        return cached

    update_llm_hud("THINKING", f"Using {selected_model} / {profile}")
    llm_log(f"Request started model={selected_model}, profile={profile}, chars={len(prompt)}")

    try:
        answer = _m47_retry_call(lambda: ask_model_enterprise(selected_model, prompt, profile=profile))
        _m47_cache_set(prompt, selected_model, profile, answer)
        _m47_circuit_success()
        _m47_stats_update(True, model=selected_model, profile=profile, elapsed=time.time() - start_time)
        update_llm_hud("READY", "Ollama response completed.")
        return answer
    except Exception as error:
        _m47_circuit_failure(str(error))
        update_llm_hud("REPAIR", "LLM request failed. Repairing Ollama...")
        llm_log(f"Request failed before repair: {error}", level="ERROR")
        repaired, repair_message = ensure_ollama_ready(auto_repair=True)

        if repaired:
            try:
                answer = ask_model_enterprise(selected_model, prompt, profile=profile)
                _m47_cache_set(prompt, selected_model, profile, answer)
                _m47_circuit_success()
                _m47_stats_update(True, model=selected_model, profile=profile, elapsed=time.time() - start_time)
                update_llm_hud("READY", "Ollama response completed after repair.")
                return answer
            except Exception as second_error:
                error = second_error

        _m47_stats_update(False, model=selected_model, profile=profile, elapsed=time.time() - start_time, error=str(error))
        update_llm_hud("ERROR", str(error))
        installed = get_installed_models()
        return (
            "All configured models failed.\n"
            f"Ollama version: {ollama_version()}\n"
            f"Installed models: {', '.join(installed)}\n"
            f"Selected model: {selected_model}\n"
            f"Profile: {profile}\n"
            f"Repair result: {repair_message if 'repair_message' in locals() else 'N/A'}\n"
            f"Last error: {error}"
        )


def llm_stats_report() -> str:
    stats = _m47_safe_load(LLM_STATS_FILE, {})
    circuit = _m47_circuit_state()
    cache = _m47_safe_load(LLM_CACHE_FILE, {})
    if not isinstance(stats, dict):
        stats = {}
    if not isinstance(cache, dict):
        cache = {}

    lines = [
        "J.A.R.V.I.S MARK XLVII LLM STATS",
        "",
        f"Version: {MARK47_LLM_VERSION}",
        f"Total requests: {stats.get('total_requests', 0)}",
        f"Successful requests: {stats.get('successful_requests', 0)}",
        f"Failed requests: {stats.get('failed_requests', 0)}",
        f"Last request: {stats.get('last_request', 'N/A')}",
        f"Last model: {stats.get('last_model', 'N/A')}",
        f"Last profile: {stats.get('last_profile', 'N/A')}",
        f"Last elapsed: {stats.get('last_elapsed_seconds', 'N/A')}s",
        f"Cache items: {len(cache)}",
        f"Circuit status: {circuit.get('status', 'closed')}",
        f"Circuit failures: {circuit.get('failures', 0)}",
        "",
        ollama_status_report(),
    ]

    models = stats.get("models", {})
    if isinstance(models, dict) and models:
        lines.append("")
        lines.append("Per-model stats:")
        for model, item in models.items():
            lines.append(f"- {model}: requests={item.get('requests', 0)}, success={item.get('success', 0)}, failed={item.get('failed', 0)}, last={item.get('last_elapsed_seconds', 'N/A')}s")

    return "\n".join(lines)


def llm_health_monitor_once() -> str:
    ready, message = ensure_ollama_ready(auto_repair=True)
    update_llm_hud("READY" if ready else "ERROR", message)
    llm_log(f"Health monitor once -> {ready}: {message}")
    return "LLM HEALTH MONITOR\n" + f"Ready: {ready}\nMessage: {message}\n\n" + ollama_status_report()


def clear_llm_cache() -> str:
    _m47_safe_save(LLM_CACHE_FILE, {})
    return "LLM cache cleared."


def reset_llm_circuit_breaker() -> str:
    _m47_circuit_success()
    return "LLM circuit breaker reset."


def set_llm_profile(profile: str) -> str:
    global LLM_PROFILE
    profile = str(profile or "").lower().strip()
    if profile not in LLM_PROFILES:
        return "Unknown profile. Use: fast, balanced, quality, code."
    LLM_PROFILE = profile
    os.environ["JARVIS_LLM_PROFILE"] = profile
    return f"LLM profile set to: {profile}"


def llm_enterprise_status() -> str:
    return llm_stats_report() + "\n\nAvailable profiles: " + ", ".join(LLM_PROFILES.keys())


def cloud_llm_placeholder(prompt: str) -> str:
    return "Cloud LLM connector is not configured.\nThis local J.A.R.V.I.S build currently uses Ollama only."


_OLD_ASK_LLM_BASIC = ask_llm
_OLD_WARMUP_MODELS_BASIC = warmup_models


def ask_llm(prompt: str, model_name: Optional[str] = None, profile: Optional[str] = None) -> str:
    return ask_llm_enterprise(prompt, model_name=model_name, profile=profile, use_cache=True)


def warmup_models() -> str:
    lines = [
        MARK47_LLM_VERSION,
        "",
        ollama_status_report(),
        "",
        "ENTERPRISE HEALTH:",
        llm_health_monitor_once(),
        "",
        "MODEL ROUTER TEST:",
    ]

    selected = choose_model_for_prompt("Reply with OK using one word.", profile="fast")
    lines.append(f"Fast profile selected model: {selected}")

    if selected:
        try:
            reply = ask_llm_enterprise("Reply with OK using one word.", model_name=selected, profile="fast", use_cache=False)
            lines.append(f"{selected} / enterprise ask_llm -> OK ({reply[:100]})")
        except Exception as error:
            lines.append(f"{selected} / enterprise ask_llm -> FAILED ({error})")

    lines.append("")
    lines.append("STATS:")
    lines.append(llm_stats_report())
    return "\n".join(lines)


def handle_llm_console_command(question: str) -> Optional[str]:
    lower = str(question or "").lower().strip()

    if lower in {"status", "ollama status", "llm status", "enterprise status"}:
        return llm_enterprise_status()
    if lower in {"stats", "llm stats", "statistics"}:
        return llm_stats_report()
    if lower in {"health", "llm health", "monitor", "health monitor"}:
        return llm_health_monitor_once()
    if lower in {"repair", "auto repair", "fix ollama"}:
        ready, message = ensure_ollama_ready(auto_repair=True)
        return f"Ready: {ready}\n{message}"
    if lower in {"clear cache", "clear llm cache"}:
        return clear_llm_cache()
    if lower in {"reset circuit", "reset circuit breaker", "reset llm circuit"}:
        return reset_llm_circuit_breaker()

    match = re.match(r"^profile\s+(fast|balanced|quality|code)$", lower)
    if match:
        return set_llm_profile(match.group(1))

    if lower == "test models":
        return warmup_models()

    if lower in {"speed test", "llm speed test", "test speed"}:
        return llm_speed_self_test()

    return None



# ==========================================================
# J.A.R.V.I.S SPEED REFINEMENT LAYER
# Added at the end so it overrides the previous enterprise LLM functions.
#
# Goals:
# - much faster normal answers
# - no repeated heavy model tests before every prompt
# - faster report/short command routing
# - smarter timeout and context trimming
# - optional quick mode / quality mode
# ==========================================================

SPEED_REFINEMENT_VERSION = "J.A.R.V.I.S LLM Speed Refinement"
FAST_READY_CACHE_FILE = "llm_ready_cache.json"
FAST_READY_CACHE_SECONDS = 90
FAST_COMMAND_MAX_CHARS = 4500
FAST_REPORT_MAX_CHARS = 1800


def _speed_now_int():
    return int(time.time())


def _speed_safe_load(path, default=None):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            return json.load(file)
    except Exception:
        return default if default is not None else {}


def _speed_safe_save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _speed_is_report_prompt(prompt: str) -> bool:
    lower = str(prompt or "").lower()
    return (
        "report" in lower
        or "pdf" in lower
        or "docx" in lower
        or "word" in lower
        or "xlsx" in lower
        or "excel" in lower
        or "ppt" in lower
        or "powerpoint" in lower
    )


def _speed_is_short_command(prompt: str) -> bool:
    lower = str(prompt or "").lower().strip()
    return len(lower) <= FAST_COMMAND_MAX_CHARS and not any(
        token in lower for token in [
            "full source code",
            "analyze entire",
            "complete audit",
            "very detailed",
            "deep analysis",
            "architecture review",
            "security audit",
        ]
    )


def optimize_prompt_context(prompt: str, max_chars: int = LLM_MAX_CONTEXT_CHARS) -> str:
    text = str(prompt or "")

    if _speed_is_report_prompt(text):
        max_chars = min(max_chars, FAST_REPORT_MAX_CHARS)
    elif _speed_is_short_command(text):
        max_chars = min(max_chars, FAST_COMMAND_MAX_CHARS)

    if len(text) <= max_chars:
        return text

    head_size = int(max_chars * 0.55)
    tail_size = int(max_chars * 0.35)

    note = (
        "\n\n[Fast context optimization: middle content skipped for speed. "
        "Use quality mode for deeper analysis.]\n\n"
    )

    return text[:head_size] + note + text[-tail_size:]


def adaptive_timeout(prompt: str, profile: Optional[str] = None) -> int:
    profile = (profile or LLM_PROFILE or "fast").lower()
    settings = LLM_PROFILES.get(profile, LLM_PROFILES["fast"])
    length = len(str(prompt or ""))

    if _speed_is_report_prompt(prompt):
        base = 55
    elif length < 1000:
        base = 45
    elif length < 5000:
        base = 65
    elif length < 15000:
        base = 90
    else:
        base = 130

    return max(30, min(180, int(base * float(settings.get("timeout_factor", 1.0)))))


def detect_prompt_type(prompt: str) -> str:
    lower = str(prompt or "").lower()

    if _speed_is_report_prompt(lower):
        return "fast"

    if any(token in lower for token in ["traceback", "error:", "exception", "def ", "class ", "function ", "review code", "improve code", "safe patch", "```"]):
        return "code"

    if any(token in lower for token in ["architecture", "roadmap", "security audit", "vulnerability", "deep analysis"]):
        return "quality"

    return LLM_PROFILE or "fast"


def ensure_ollama_ready_fast(auto_repair: bool = True, force_test: bool = False) -> Tuple[bool, str]:
    """
    Faster readiness check:
    - checks /api/version and installed models
    - does not generate test text every time
    - only runs model generation test when forced or cache expired
    """
    cache = _speed_safe_load(FAST_READY_CACHE_FILE, {})

    if (
        isinstance(cache, dict)
        and not force_test
        and cache.get("ready") is True
        and _speed_now_int() - int(cache.get("time", 0) or 0) < FAST_READY_CACHE_SECONDS
        and ollama_alive()
    ):
        return True, "Ollama ready from fast cache."

    update_llm_hud("CHECKING", "Fast Ollama health check...")

    if not ollama_alive():
        if not auto_repair:
            return False, "Ollama is offline."

        stop_ollama_server()

        if not start_ollama_server_cpu():
            return False, "Ollama could not be started automatically."

    installed = get_installed_models()

    if not installed:
        return False, f"Ollama is running, but no model is installed. Run: ollama pull {DEFAULT_MODEL}"

    selected = resolve_model_name()

    if not selected:
        return False, "No usable Ollama model could be selected."

    if force_test:
        ok, message = test_model_generation(selected)
        if not ok:
            if auto_repair:
                stop_ollama_server()
                if start_ollama_server_cpu():
                    ok, message = test_model_generation(selected)

            if not ok:
                return False, message

    _speed_safe_save(FAST_READY_CACHE_FILE, {
        "ready": True,
        "time": _speed_now_int(),
        "model": selected,
        "version": ollama_version(),
    })

    update_llm_hud("READY", f"Ollama ready: {selected}")
    return True, f"Ollama ready: {selected}"


def ask_model_generate_enterprise(model_name: str, prompt: str, profile: Optional[str] = None) -> str:
    prompt = optimize_prompt_context(prompt)
    full_prompt = SYSTEM_PROMPT.strip() + "\n\nUser request:\n" + str(prompt)

    payload: Dict[str, Any] = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "options": _m47_options(profile),
    }

    response = requests.post(
        OLLAMA_GENERATE_URL,
        json=payload,
        timeout=adaptive_timeout(prompt, profile)
    )
    response.raise_for_status()
    data = response.json()
    return str(data.get("response", "")).strip()


def ask_model_chat_enterprise(model_name: str, prompt: str, profile: Optional[str] = None) -> str:
    prompt = optimize_prompt_context(prompt)
    payload: Dict[str, Any] = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": str(prompt)},
        ],
        "stream": False,
        "options": _m47_options(profile),
    }

    response = requests.post(
        OLLAMA_CHAT_URL,
        json=payload,
        timeout=adaptive_timeout(prompt, profile)
    )
    response.raise_for_status()
    data = response.json()
    return data.get("message", {}).get("content", "").strip()


def ask_model_enterprise(model_name: str, prompt: str, profile: Optional[str] = None) -> str:
    errors = []

    # Generate first is usually more stable and faster on local Ollama.
    methods = [
        ("generate", ask_model_generate_enterprise),
        ("chat", ask_model_chat_enterprise),
    ]

    # CLI fallback is slow, so use it only for quality/code profile.
    if (profile or "").lower() in {"quality", "code"}:
        methods.append(("cli", lambda m, p, profile=None: ask_model_cli(m, optimize_prompt_context(p))))

    for method_name, method in methods:
        try:
            result = method(model_name, prompt, profile=profile)

            if result:
                llm_log(f"{method_name} success model={model_name}")
                return result

            errors.append(f"{method_name}: empty response")
        except Exception as error:
            errors.append(f"{method_name}: {error}")
            llm_log(f"{method_name} failed model={model_name}: {error}", level="WARN")

    raise RuntimeError(f"Model {model_name} failed. " + " | ".join(errors))


def _m47_retry_call(fn, attempts: int = LLM_RETRY_ATTEMPTS):
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as error:
            last_error = error

            if attempt >= attempts:
                break

            delay = LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            llm_log(f"Retry {attempt}/{attempts} failed: {error}. Sleeping {delay:.1f}s", level="WARN")
            time.sleep(delay)

    raise last_error


def ask_llm_enterprise(prompt: str, model_name: Optional[str] = None, profile: Optional[str] = None, use_cache: bool = True) -> str:
    start_time = time.time()
    prompt = optimize_prompt_context(prompt)
    profile = (profile or detect_prompt_type(prompt)).lower().strip()

    is_open, reason = _m47_circuit_is_open()
    if is_open:
        message = f"Ollama circuit breaker is temporarily open. Reason: {reason}"
        update_llm_hud("CIRCUIT OPEN", message)
        llm_log(message, level="ERROR")
        return message

    # Force a model test only for health/test commands, not every normal prompt.
    force_test = False
    ready, ready_message = ensure_ollama_ready_fast(auto_repair=True, force_test=force_test)

    if not ready:
        _m47_circuit_failure(ready_message)
        _m47_stats_update(False, profile=profile, elapsed=time.time() - start_time, error=ready_message)
        return ready_message

    selected_model = choose_model_for_prompt(prompt, preferred_model=model_name, profile=profile)

    if not selected_model:
        message = "Could not select an Ollama model."
        _m47_circuit_failure(message)
        _m47_stats_update(False, profile=profile, elapsed=time.time() - start_time, error=message)
        return message

    cached = _m47_cache_get(prompt, selected_model, profile) if use_cache else None

    if cached:
        _m47_stats_update(True, model=selected_model, profile=profile, elapsed=time.time() - start_time)
        update_llm_hud("READY", "Returned cached LLM response.")
        return cached

    update_llm_hud("THINKING", f"Using {selected_model} / {profile}")
    llm_log(f"Fast request started model={selected_model}, profile={profile}, chars={len(prompt)}")

    try:
        answer = _m47_retry_call(
            lambda: ask_model_enterprise(selected_model, prompt, profile=profile),
            attempts=LLM_RETRY_ATTEMPTS
        )

        _m47_cache_set(prompt, selected_model, profile, answer)
        _m47_circuit_success()
        _m47_stats_update(True, model=selected_model, profile=profile, elapsed=time.time() - start_time)
        update_llm_hud("READY", "Ollama response completed.")
        return answer

    except Exception as error:
        _m47_circuit_failure(str(error))
        update_llm_hud("REPAIR", "LLM failed. Fast repair...")

        repaired, repair_message = ensure_ollama_ready_fast(auto_repair=True, force_test=True)

        if repaired:
            try:
                answer = ask_model_enterprise(selected_model, prompt, profile=profile)
                _m47_cache_set(prompt, selected_model, profile, answer)
                _m47_circuit_success()
                _m47_stats_update(True, model=selected_model, profile=profile, elapsed=time.time() - start_time)
                update_llm_hud("READY", "Ollama response completed after repair.")
                return answer
            except Exception as second_error:
                error = second_error

        _m47_stats_update(False, model=selected_model, profile=profile, elapsed=time.time() - start_time, error=str(error))
        update_llm_hud("ERROR", str(error))

        return (
            "All configured models failed.\n"
            f"Ollama version: {ollama_version()}\n"
            f"Installed models: {', '.join(get_installed_models())}\n"
            f"Selected model: {selected_model}\n"
            f"Profile: {profile}\n"
            f"Repair result: {repair_message if 'repair_message' in locals() else 'N/A'}\n"
            f"Last error: {error}"
        )


def ask_llm(prompt: str, model_name: Optional[str] = None, profile: Optional[str] = None) -> str:
    return ask_llm_enterprise(
        prompt,
        model_name=model_name,
        profile=profile,
        use_cache=True
    )


def warmup_models() -> str:
    lines = [
        SPEED_REFINEMENT_VERSION,
        MARK47_LLM_VERSION,
        "",
        ollama_status_report(),
        "",
        "FAST HEALTH:",
    ]

    ready, message = ensure_ollama_ready_fast(auto_repair=True, force_test=True)
    lines.append(f"ensure_ollama_ready_fast -> {ready}: {message}")

    selected = choose_model_for_prompt("Reply OK.", profile="fast")
    lines.append(f"Fast selected model: {selected}")

    if selected:
        try:
            reply = ask_llm_enterprise("Reply with OK using one word.", model_name=selected, profile="fast", use_cache=False)
            lines.append(f"{selected} / fast ask_llm -> OK ({reply[:100]})")
        except Exception as error:
            lines.append(f"{selected} / fast ask_llm -> FAILED ({error})")

    lines.append("")
    lines.append(llm_stats_report())

    return "\n".join(lines)


def set_llm_profile(profile: str) -> str:
    global LLM_PROFILE

    profile = str(profile or "").lower().strip()

    if profile not in LLM_PROFILES:
        return "Unknown profile. Use: fast, balanced, quality, code."

    LLM_PROFILE = profile
    os.environ["JARVIS_LLM_PROFILE"] = profile

    return f"LLM profile set to: {profile}"


def handle_llm_console_command(question: str) -> Optional[str]:
    lower = str(question or "").lower().strip()

    if lower in {"status", "ollama status", "llm status", "enterprise status"}:
        return llm_enterprise_status()

    if lower in {"stats", "llm stats", "statistics"}:
        return llm_stats_report()

    if lower in {"health", "llm health", "monitor", "health monitor"}:
        return llm_health_monitor_once()

    if lower in {"repair", "auto repair", "fix ollama"}:
        ready, message = ensure_ollama_ready_fast(auto_repair=True, force_test=True)
        return f"Ready: {ready}\n{message}"

    if lower in {"clear cache", "clear llm cache"}:
        return clear_llm_cache()

    if lower in {"reset circuit", "reset circuit breaker", "reset llm circuit"}:
        return reset_llm_circuit_breaker()

    if lower in {"fast mode", "quick mode"}:
        return set_llm_profile("fast")

    if lower in {"quality mode", "deep mode"}:
        return set_llm_profile("quality")

    if lower in {"code mode", "developer mode"}:
        return set_llm_profile("code")

    match = re.match(r"^profile\s+(fast|balanced|quality|code)$", lower)
    if match:
        return set_llm_profile(match.group(1))

    if lower == "test models":
        return warmup_models()

    return None


def llm_speed_self_test() -> str:
    start = time.time()
    ready, message = ensure_ollama_ready_fast(auto_repair=True, force_test=False)
    elapsed_ready = round(time.time() - start, 2)

    start_answer = time.time()
    answer = ask_llm("Reply with OK using one word.", profile="fast")
    elapsed_answer = round(time.time() - start_answer, 2)

    return (
        "LLM SPEED SELF TEST\n"
        f"Ready: {ready}\n"
        f"Ready message: {message}\n"
        f"Ready check time: {elapsed_ready}s\n"
        f"Answer: {answer[:100]}\n"
        f"Answer time: {elapsed_answer}s\n"
        f"Profile: {LLM_PROFILE}\n"
        f"Context limit: {LLM_MAX_CONTEXT_CHARS}\n"
    )



if __name__ == "__main__":
    print(
        "JARVIS Local LLM Ready\n"
        "Type: exit\n"
        "Type: test models\n"
        "Type: status\n"
        "Type: repair\n"
    )

    print("Checking Ollama...\n")
    print(ollama_status_report())
    print()

    while True:
        question = input("You: ").strip()

        if question.lower() == "exit":
            break

        console_result = handle_llm_console_command(question)

        if console_result is not None:
            print("\nJARVIS:")
            print(console_result)
            print()
            continue

        start = time.time()
        answer = ask_llm(question)
        elapsed = round(time.time() - start, 2)

        print("\nJARVIS:")
        print(answer)
        print(f"\n[{elapsed}s]\n")
