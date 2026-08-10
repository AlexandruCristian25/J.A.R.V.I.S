import json
import os
import queue
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import time
import subprocess
import wave
import numpy as np
import sys
import threading
import difflib
import webbrowser
import shutil

try:
    import winreg
except Exception:
    winreg = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

from jarvis_agent import handle_command


# ===============================
# AUTO MICROPHONE DETECTION
# ===============================
def get_best_microphone_id():
    devices = sd.query_devices()

    preferred_words = [
        "microphone",
        "mic",
        "realtek",
        "input"
    ]

    candidates = []

    for index, device in enumerate(devices):
        name = device["name"].lower()
        inputs = device["max_input_channels"]

        if inputs > 0:
            score = 0

            for word in preferred_words:
                if word in name:
                    score += 1

            candidates.append((score, index, device["name"]))

    if not candidates:
        raise RuntimeError("No microphone input device found.")

    candidates.sort(reverse=True)

    best = candidates[0]

    print(f"Auto-selected microphone: {best[2]} (ID {best[1]})")

    return best[1]


def find_vosk_model():
    models_dir = "models"

    preferred_models = [
        "vosk-model-en-us-0.22",
        "vosk-model-small-en-us-0.15",
        "vosk-model-small-en-us",
        "vosk-model-en-us"
    ]

    # 1. Try preferred direct paths first
    for model_name in preferred_models:
        candidate = os.path.join(models_dir, model_name)

        if os.path.isdir(candidate):
            if (
                os.path.isdir(os.path.join(candidate, "conf"))
                or os.path.isdir(os.path.join(candidate, "am"))
                or os.path.isdir(os.path.join(candidate, "graph"))
            ):
                print(f"Auto-selected Vosk model: {candidate}")
                return candidate

            # Handle nested extracted folder:
            # models/vosk-model.../vosk-model.../conf
            for child in os.listdir(candidate):
                nested = os.path.join(candidate, child)

                if os.path.isdir(nested) and (
                    os.path.isdir(os.path.join(nested, "conf"))
                    or os.path.isdir(os.path.join(nested, "am"))
                    or os.path.isdir(os.path.join(nested, "graph"))
                ):
                    print(f"Auto-selected nested Vosk model: {nested}")
                    return nested

    # 2. Scan every folder inside models/
    if os.path.isdir(models_dir):
        for root, dirs, files in os.walk(models_dir):
            root_lower = root.lower()

            if "vosk" not in root_lower:
                continue

            if (
                os.path.isdir(os.path.join(root, "conf"))
                or os.path.isdir(os.path.join(root, "am"))
                or os.path.isdir(os.path.join(root, "graph"))
            ):
                print(f"Auto-selected Vosk model: {root}")
                return root

    raise RuntimeError(
        "No valid Vosk model found. Put a Vosk English model inside the models folder, "
        "for example: models/vosk-model-small-en-us-0.15"
    )


MODEL_PATH = find_vosk_model()
MICROPHONE_ID = get_best_microphone_id()
ACTIVATION_SOUND = "activation.wav"
VOICE_FILE = "voice_level.txt"

# ===============================
# ENTERPRISE VAD SETTINGS
# ===============================
SAMPLE_RATE = 16000
BLOCK_SIZE = 4000

# VAD is RMS-based and works with the Vosk stream.
# It decides when speech starts and when the user stopped talking.
VAD_ENABLED = True
VAD_CALIBRATION_SECONDS = 0.45
VAD_START_RATIO = 1.85
VAD_MIN_START_LEVEL = 120
VAD_END_SILENCE_SECONDS = 0.72
VAD_MAX_COMMAND_SECONDS = 22
VAD_MIN_SPEECH_SECONDS = 0.18

# Wake detection stays short and strict.
WAKE_RECOGNITION_SECONDS = 2.8

# Debug output helps tune the mic.
VAD_DEBUG = False

VOICE_STATE_FILE = "voice_state.txt"

WAKE_WORDS = [
    "jarvis",
    "hey jarvis",
    "jervis",
    "hey jervis",
    "hey jar",
    "hey jha",
    "john nice",
    "hey john nice",
    "hey journeys",
    "hey jim this",
    "hey jack this"
]

SHUTDOWN_WORDS = [
    "jarvis shutdown",
    "shutdown jarvis",
    "jarvis stop",
    "stop jarvis",
    "stop listening"
]

q = queue.Queue()
hud_process = None

# ===============================
# VOICE SUMMARY MODE
# ===============================
VOICE_SUMMARY_MODE = True
MAX_SPOKEN_CHARS = 350
LONG_RESPONSE_CHARS = 900

tts_engine = None
tts_lock = threading.Lock()


def init_tts():
    global tts_engine

    if pyttsx3 is None:
        print("pyttsx3 not installed. Voice output disabled.")
        return None

    if tts_engine is None:
        try:
            tts_engine = pyttsx3.init()
            tts_engine.setProperty("rate", 150)
            tts_engine.setProperty("volume", 1.0)
        except Exception as e:
            print(f"TTS initialization failed: {e}")
            tts_engine = None

    return tts_engine


def speak(text):
    text = str(text).strip()

    if not text:
        return

    engine = init_tts()

    if engine is None:
        return

    def _run():
        with tts_lock:
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as e:
                print(f"TTS error: {e}")

    threading.Thread(target=_run, daemon=True).start()


def voice_summary(command, result):
    command_lower = command.lower()
    result_text = str(result).strip()

    if not result_text:
        return "Command completed."

    report_keywords = [
        "report",
        "analyzer",
        "review",
        "security",
        "architecture",
        "project",
        "duplicates",
        "dead code",
        "score",
        "ranking",
        "compare"
    ]

    is_report_like = (
        len(result_text) > LONG_RESPONSE_CHARS
        or any(word in command_lower for word in report_keywords)
    )

    if result_text.startswith("Project report exported successfully"):
        lines = result_text.splitlines()
        file_line = ""

        for line in lines:
            if line.lower().startswith("file:"):
                file_line = line.replace("File:", "").strip()
                break

        if file_line:
            return "Project report exported successfully. The full report was saved in the reports folder."

        return "Project report exported successfully."

    if "project not found" in result_text.lower():
        return "Project not found. Please refresh projects or remember the deep project first."

    if "file not found" in result_text.lower():
        return "File not found. Please check the project memory or file name."

    if is_report_like:
        summary_parts = []

        if "HIGH:" in result_text or "MEDIUM/HIGH" in result_text:
            summary_parts.append("I found important security issues.")

        if "weak/default secret" in result_text.lower():
            summary_parts.append("Weak or demo secrets were detected.")

        if "fake_users_db" in result_text:
            summary_parts.append("Demo users were detected and should be replaced before production.")

        if "scores:" in result_text.lower():
            for line in result_text.splitlines():
                lower = line.lower()

                if "overall:" in lower:
                    summary_parts.append(line.strip().replace(" - ", ""))
                    break

        if "winner by category" in result_text.lower():
            summary_parts.append("The project comparison is complete.")

        if "STRICT GROUNDED ANALYZER REPORT" in result_text:
            summary_parts.append("The strict grounded analyzer completed using real indexed files.")

        if not summary_parts:
            summary_parts.append("The report is complete.")

        summary_parts.append("Check the terminal for the full details.")

        return " ".join(summary_parts)

    short = result_text.replace("\n", ". ")

    if len(short) > MAX_SPOKEN_CHARS:
        short = short[:MAX_SPOKEN_CHARS].rsplit(" ", 1)[0]
        short += ". Check the terminal for the full details."

    return short



# ===============================
# ENTERPRISE VAD HELPERS
# ===============================
def write_text_file(path, value):
    try:
        with open(path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(str(value))
    except Exception:
        pass


def write_voice_level(level):
    level = max(0.0, min(1.0, float(level)))

    write_text_file(VOICE_FILE, str(level))


def write_voice_state(state):
    write_text_file(VOICE_STATE_FILE, str(state))


def audio_rms(data):
    try:
        audio = np.frombuffer(data, dtype=np.int16)

        if audio.size == 0:
            return 0.0

        return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))

    except Exception:
        return 0.0


def drain_audio_queue(max_items=60):
    drained = 0

    while drained < max_items:
        try:
            q.get_nowait()
            drained += 1
        except queue.Empty:
            break


def calibrate_vad_noise(seconds=VAD_CALIBRATION_SECONDS):
    """
    Measures room noise and returns an adaptive RMS threshold.
    """
    print("[VAD] Calibrating microphone noise...")
    write_voice_state("CALIBRATING")

    values = []
    start = time.time()

    while time.time() - start < seconds:
        try:
            data = q.get(timeout=0.25)
        except queue.Empty:
            continue

        level = audio_rms(data)
        values.append(level)
        write_voice_level(min(level / 3000.0, 1.0))

    if not values:
        base = VAD_MIN_START_LEVEL
    else:
        base = float(np.median(values))

    threshold = max(VAD_MIN_START_LEVEL, base * VAD_START_RATIO)

    print(f"[VAD] noise={base:.1f} threshold={threshold:.1f}")
    write_voice_state("READY")
    write_voice_level(0.0)

    return threshold


def new_vosk_recognizer(grammar=None):
    if grammar:
        return KaldiRecognizer(
            model,
            SAMPLE_RATE,
            json.dumps(grammar)
        )

    return KaldiRecognizer(
        model,
        SAMPLE_RATE
    )


def recognize_vosk_from_chunks(chunks, grammar=None):
    if not chunks:
        return ""

    local_rec = new_vosk_recognizer(grammar)

    final_parts = []

    for chunk in chunks:
        if local_rec.AcceptWaveform(chunk):
            try:
                part = json.loads(local_rec.Result()).get("text", "").strip()
                if part:
                    final_parts.append(part)
            except Exception:
                pass

    try:
        final = json.loads(local_rec.FinalResult()).get("text", "").strip()
        if final:
            final_parts.append(final)
    except Exception:
        pass

    return " ".join(final_parts).strip()


def collect_speech_with_vad(
    max_seconds=VAD_MAX_COMMAND_SECONDS,
    end_silence_seconds=VAD_END_SILENCE_SECONDS,
    min_speech_seconds=VAD_MIN_SPEECH_SECONDS,
    grammar=None,
    label="command"
):
    """
    Records audio chunks until:
    - speech starts above threshold
    - then user pauses for end_silence_seconds
    This prevents cutting long commands and avoids random short noise.
    """
    drain_audio_queue()
    threshold = calibrate_vad_noise()
    chunks = []

    speech_started = False
    speech_start_time = None
    last_voice_time = None
    start_time = time.time()

    write_voice_state(f"LISTENING_{label.upper()}")
    print(f"[VAD] Listening for {label}...")

    while time.time() - start_time < max_seconds:
        try:
            data = q.get(timeout=0.35)
        except queue.Empty:
            continue

        level = audio_rms(data)
        write_voice_level(min(level / max(threshold * 2, 1), 1.0))

        is_voice = level >= threshold

        if VAD_DEBUG:
            # Compact debug; not every sample.
            if int(time.time() * 2) % 3 == 0:
                print(f"[VAD] level={level:.0f} threshold={threshold:.0f} voice={is_voice}")

        if is_voice:
            if not speech_started:
                speech_started = True
                speech_start_time = time.time()
                print("[VAD] Speech started.")
                write_voice_state("SPEAKING")

            last_voice_time = time.time()
            chunks.append(data)

        elif speech_started:
            # Keep small silence after speech for recognizer context.
            chunks.append(data)

            if last_voice_time and time.time() - last_voice_time >= end_silence_seconds:
                break

    write_voice_level(0.0)
    write_voice_state("PROCESSING")

    if not speech_started:
        print("[VAD] No speech detected.")
        write_voice_state("NO_SPEECH")
        return ""

    speech_duration = time.time() - (speech_start_time or time.time())

    if speech_duration < min_speech_seconds:
        print("[VAD] Speech too short, ignored.")
        write_voice_state("TOO_SHORT")
        return ""

    text = recognize_vosk_from_chunks(chunks, grammar=grammar)
    text = normalize_vosk_mistakes(text)

    write_voice_state("READY")

    if text:
        print(f"[VAD] Recognized {label}: {text}")
    else:
        print(f"[VAD] Could not recognize {label}.")

    return text


def normalize_vosk_mistakes(text):
    text = str(text or "").lower().strip()

    if not text:
        return ""

    replacements = {
        "hey jha": "hey jarvis",
        "hey jar": "hey jarvis",
        "hey jervis": "hey jarvis",
        "jervis": "jarvis",
        "john nice": "jarvis",
        "hey john nice": "hey jarvis",
        "hey journeys": "hey jarvis",
        "hey jim this": "hey jarvis",
        "hey jack this": "hey jarvis",
        "open fire": "open firefox",
        "open mozilla": "open firefox",
        "open browser": "open chrome",
        "open vs": "open vscode",
        "open vs code": "open vscode",
        "open visual studio code": "open vscode",
        "cybers in the": "cybershield ai",
        "cyber shield": "cyber shield ai",
    }

    if text in replacements:
        return replacements[text]

    text = re.sub(r"\bhey\s+(jha|jar|jervis|john nice|journeys|jim this|jack this)\b", "hey jarvis", text)
    text = re.sub(r"\b(jervis|john nice|journeys)\b", "jarvis", text)
    text = re.sub(r"\bopen\s+fire\b", "open firefox", text)
    text = re.sub(r"\bopen\s+mozilla\b", "open firefox", text)
    text = re.sub(r"\bopen\s+vs\s+code\b", "open vscode", text)
    text = re.sub(r"\bcybers\s+in\s+the\b", "cybershield ai", text)

    return text.strip()


def is_wake_text(text):
    text = normalize_vosk_mistakes(text)

    if not text:
        return False

    if text in WAKE_WORDS:
        return True

    if text.startswith("hey jarvis"):
        return True

    if text.startswith("jarvis"):
        return True

    return any(wake in text for wake in WAKE_WORDS)


def strip_wake_from_command(text):
    text = normalize_vosk_mistakes(text)

    for wake in sorted(WAKE_WORDS, key=len, reverse=True):
        if text.startswith(wake + " "):
            return text[len(wake):].strip()

    if text == "jarvis" or text == "hey jarvis":
        return ""

    return text

# ===============================
# MICROPHONE CALLBACK
# ===============================
def audio_callback(indata, frames, time_info, status):
    q.put(bytes(indata))

print("Loading model...")
model = Model(MODEL_PATH)

# ===============================
# BETTER VOICE RECOGNITION GRAMMAR
# Helps the small Vosk model understand JARVIS commands better.
# ===============================
VOICE_GRAMMAR = [
    "jarvis",
    "hey jarvis",
    "hey jervis",
    "hey jar",
    "hey jha",
    "jervis",
    "john nice",
    "hey john nice",
    "hey journeys",
    "hey jim this",
    "hey jack this",

    "daily check",
    "daily project check",
    "smart daily check",

    "open calculator",
    "open computer",
    "open chrome",
    "open browser",
    "open notepad",
    "open visual studio code",
    "open vscode",
    "open visual studio",
    "open command prompt",
    "open powershell",
    "open explorer",
    "open file explorer",
    "open settings",
    "open task manager",
    "open control panel",
    "open paint",
    "open word",
    "open excel",
    "open powerpoint",
    "open edge",
    "open firefox",
    "open fire",
    "open mozilla",
    "open opera",
    "open discord",
    "open teams",
    "open telegram",
    "open whatsapp",
    "open spotify",
    "open steam",

    "open google",
    "open youtube",
    "open gmail",
    "open github",
    "open chat gpt",
    "open chatgpt",
    "open facebook",
    "open instagram",
    "open linkedin",
    "open stack overflow",
    "open wikipedia",
    "open stack overflow",
    "open reddit",
    "open w3schools",
    "open mdn",
    "open website wikipedia",
    "open website stack overflow",
    "go to wikipedia",
    "go to stack overflow",
    "open website google",
    "open website youtube",
    "open website github",

    "open downloads",
    "open documents",
    "open desktop",
    "open pictures",
    "open folder downloads",
    "open folder documents",
    "open folder desktop",
    "open folder pictures",

    "find file",
    "open file",
    "read file",
    "rank file",
    "open project",
    "open project cyber shield ai",
    "open project jarvis",
    "open code cyber shield ai",
    "open code jarvis",

    "show projects",
    "refresh projects",
    "refresh applications",

    "score project cyber shield ai",
    "score project cybershield ai",
    "score project jarvis",

    "strict security analyzer project cyber shield ai",
    "strict security analyzer project cybershield ai",

    "suggest fixes for project cyber shield ai",
    "suggest fixes for project cybershield ai",
    "suggest fixes jarvis",

    "export report cyber shield ai",
    "export report cybershield ai",
    "export report jarvis",

    "stop listening",
    "jarvis stop",
    "shutdown jarvis",


    "ok jarvis",
    "okay jarvis",
    "hi jarvis",
    "hello jarvis",
    "yo jarvis",
    "jarvis please",
    "hey service",
    "hey javascript",
    "hey travis",
    "travis",
    "service",
    "javascript",

    "open browser firefox",
    "open browser chrome",
    "open browser edge",
    "open firefox browser",
    "open fire fox",
    "open project cyber shield ai in vs code",
    "open project cybershield ai in vs code",
    "open project jarvis in vs code",
    "open project manager app in vs code",
    "open manager app in vs code",
    "open managerapp in vs code",
    "open project cyber shield ai in visual studio code",
    "open project jarvis in visual studio code",
    "open project manager app in intellij",
    "open project manager app in eclipse",
    "open project manager app in visual studio",
    "create pdf report for cyber shield ai",
    "generate pdf report for cyber shield ai",
    "give me a report about this project in pdf",
    "generate word report",
    "generate excel report",
    "generate powerpoint report",

    "[unk]"
]

rec = new_vosk_recognizer(VOICE_GRAMMAR)

stream = sd.RawInputStream(
    samplerate=SAMPLE_RATE,
    blocksize=BLOCK_SIZE,
    device=MICROPHONE_ID,
    dtype="int16",
    channels=1,
    callback=audio_callback
)
stream.start()

# ===============================
# HUD CONTROL
# ===============================
def start_hud():
    global hud_process
    if hud_process is None or hud_process.poll() is not None:
        hud_process = subprocess.Popen(
            [sys.executable, "hud.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

def stop_hud():
    global hud_process
    if hud_process and hud_process.poll() is None:
        hud_process.terminate()
        hud_process = None

# ===============================
# PLAY WAV + REAL VOICE LEVEL
# ===============================
def play_activation():
    wf = wave.open(ACTIVATION_SOUND, 'rb')

    samplerate = wf.getframerate()
    channels = wf.getnchannels()

    def callback(outdata, frames, time_info, status):
        data = wf.readframes(frames)
        if len(data) == 0:
            raise sd.CallbackStop()

        audio = np.frombuffer(data, dtype=np.int16)

        level = np.linalg.norm(audio) / 30000
        level = min(level, 1.0)

        with open(VOICE_FILE, "w") as f:
            f.write(str(level))

        outdata[:] = audio.reshape(-1, channels)

    with sd.OutputStream(
        samplerate=samplerate,
        channels=channels,
        dtype="int16",
        callback=callback
    ):
        sd.sleep(int(wf.getnframes() / samplerate * 1000))

    with open(VOICE_FILE, "w") as f:
        f.write("0.0")

# ===============================
# VOICE COMMAND NORMALIZATION
# Fixes common Vosk recognition mistakes.
# ===============================
KNOWN_COMMANDS = [
    "daily check",
    "daily project check",
    "smart daily check",

    "open calculator",
    "open chrome",
    "open browser",
    "open notepad",
    "open visual studio code",
    "open vscode",
    "open powershell",
    "open command prompt",
    "open file explorer",
    "open settings",
    "open task manager",
    "open control panel",
    "open paint",

    "open website google",
    "open website youtube",
    "open website gmail",
    "open website github",
    "open website chatgpt",
    "open website facebook",
    "open website instagram",
    "open website linkedin",
    "open website stackoverflow",

    "open file downloads",
    "open file documents",
    "open file desktop",
    "open file pictures",

    "show projects",
    "refresh projects",
    "refresh applications",

    "score project CyberShield AI",
    "score project J.A.R.V.I.S",

    "strict security analyzer project CyberShield AI",
    "suggest fixes for project CyberShield AI",
    "suggest fixes J.A.R.V.I.S",

    "export report CyberShield AI",
    "export report J.A.R.V.I.S",
]


WEBSITE_ALIASES = {
    "google": "google.com",
    "youtube": "youtube.com",
    "you tube": "youtube.com",
    "gmail": "gmail.com",
    "github": "github.com",
    "git hub": "github.com",
    "chat gpt": "chat.openai.com",
    "chatgpt": "chat.openai.com",
    "open ai": "openai.com",
    "openai": "openai.com",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "linkedin": "linkedin.com",
    "linked in": "linkedin.com",
    "stackoverflow": "stackoverflow.com",
    "stack overflow": "stackoverflow.com",
    "wikipedia": "wikipedia.org",
    "wiki": "wikipedia.org",
    "reddit": "reddit.com",
    "netflix": "netflix.com",
    "tiktok": "tiktok.com",
    "tik tok": "tiktok.com",
    "twitter": "x.com",
    "x": "x.com",
    "medium": "medium.com",
    "quora": "quora.com",
    "amazon": "amazon.com",
    "emag": "emag.ro",
    "olx": "olx.ro",
    "w3schools": "w3schools.com",
    "mdn": "developer.mozilla.org",
    "mozilla": "developer.mozilla.org",
    "coursera": "coursera.org",
    "udemy": "udemy.com",

}


FOLDER_ALIASES = {
    "downloads": "downloads",
    "download": "downloads",
    "documents": "documents",
    "document": "documents",
    "desktop": "desktop",
    "pictures": "pictures",
    "images": "pictures",
    "music": "music",
    "videos": "videos",
}


APP_ALIASES = {
    "computer": "calculator",
    "calculate": "calculator",
    "calculation": "calculator",
    "cal creator": "calculator",
    "browser": "chrome",
    "visual studio": "visual studio code",
    "code": "vscode",
    "vs code": "vscode",
    "explorer": "file explorer",
}


PROJECT_ALIASES = {
    "cyber shield ai": "CyberShield AI",
    "cybershield ai": "CyberShield AI",
    "cyber shield": "CyberShield AI",
    "jarvis": "J.A.R.V.I.S",
    "jervis": "J.A.R.V.I.S",
    "jarvis project": "J.A.R.V.I.S",
}


DIRECT_COMMAND_PREFIXES = [
    "open ",
    "open website ",
    "open site ",
    "go to ",
    "visit ",
    "search ",
    "find file ",
    "open file ",
    "read file ",
    "rank file ",
    "open folder ",
    "open project ",
    "open code ",
    "edit project ",
    "daily ",
    "smart daily",
    "score project",
    "strict security",
    "suggest fixes",
    "export report",
    "show projects",
    "refresh projects",
    "refresh applications"
]


def _strip_wake_words(text):
    text = normalize_vosk_mistakes(text)

    for wake in WAKE_WORDS:
        wake_lower = wake.lower()

        if text.startswith(wake_lower + " "):
            text = text[len(wake_lower):].strip()

        text = text.replace(wake_lower + " ", "").strip()

    return text


def _normalize_projects(text):
    for wrong, right in PROJECT_ALIASES.items():
        if wrong in text:
            text = text.replace(wrong, right)

    return text


def _clean_website_target(target):
    target = str(target).lower().strip()

    filler_words = [
        "please",
        "the website",
        "website",
        "site",
        "page",
    ]

    for word in filler_words:
        target = target.replace(word, "").strip()

    target = target.replace(" dot ", ".")
    target = target.replace(" point ", ".")
    target = target.replace(" slash ", "/")
    target = target.replace(" ", "")

    return target


def _normalize_websites(text):
    lower = text.lower().strip()

    website_prefixes = [
        "open website ",
        "open site ",
        "go to website ",
        "go to site ",
        "go to ",
        "visit website ",
        "visit site ",
        "visit ",
        "open web page ",
        "open page ",
    ]

    for prefix in website_prefixes:
        if lower.startswith(prefix):
            target = lower[len(prefix):].strip()
            target = WEBSITE_ALIASES.get(target, target)
            target = _clean_website_target(target)

            if not target:
                return text

            if "." not in target:
                target = target + ".com"

            return "open website " + target

    # Universal shortcut:
    # "open wikipedia" -> "open website wikipedia.com"
    # but only if it is not a known local app/folder/project command.
    if lower.startswith("open "):
        target = lower[len("open "):].strip()

        if target in APP_ALIASES:
            return text

        if target in FOLDER_ALIASES:
            return text

        if target in PROJECT_ALIASES:
            return text

        if target in WEBSITE_ALIASES:
            return "open website " + WEBSITE_ALIASES[target]

        # If user says a clear domain, open it as website.
        if "." in target:
            return "open website " + _clean_website_target(target)

        # Common web-like words should be treated as websites.
        web_like_words = [
            "wikipedia",
            "stackoverflow",
            "stack overflow",
            "github",
            "git hub",
            "youtube",
            "you tube",
            "google",
            "gmail",
            "facebook",
            "instagram",
            "linkedin",
            "reddit",
            "twitter",
            "x",
            "netflix",
            "tiktok",
            "tik tok",
            "openai",
            "chatgpt",
            "chat gpt",
            "medium",
            "quora",
            "amazon",
            "emag",
            "olx",
            "w3schools",
            "mdn",
            "mozilla",
            "coursera",
            "udemy",
            "stackoverflow"
        ]

        if target in web_like_words:
            cleaned = WEBSITE_ALIASES.get(target, target)
            cleaned = _clean_website_target(cleaned)

            if "." not in cleaned:
                cleaned = cleaned + ".com"

            return "open website " + cleaned

    return text

def _normalize_apps_and_folders(text):
    lower = text.lower().strip()

    if lower.startswith("open folder "):
        target = lower[len("open folder "):].strip()
        target = FOLDER_ALIASES.get(target, target)
        return "open file " + target

    if lower.startswith("open "):
        target = lower[len("open "):].strip()

        if target in FOLDER_ALIASES:
            return "open file " + FOLDER_ALIASES[target]

        if target in APP_ALIASES:
            return "open " + APP_ALIASES[target]

    return text


def normalize_voice_text(text):
    text = normalize_vosk_mistakes(text)
    text = str(text).lower().strip()

    if not text:
        return ""

    text = _strip_wake_words(text)
    text = _normalize_projects(text)
    text = _normalize_websites(text)
    text = _normalize_apps_and_folders(text)

    # Common command forms.
    if text in {"daily project", "project check", "daily"}:
        text = "daily check"

    if text.startswith("search google"):
        return "open website google.com"

    # Do not fuzzy-match universal open commands.
    # Otherwise "open project CyberShield AI" can become "score project CyberShield AI".
    universal_open_prefixes = (
        "open ",
        "open website ",
        "open site ",
        "go to ",
        "visit ",
        "open folder ",
        "open file ",
        "open app ",
        "open application ",
    )

    if text.lower().startswith(universal_open_prefixes):
        return text.strip()

    # Fuzzy match only for known non-open commands.
    possible = difflib.get_close_matches(
        text.lower(),
        [cmd.lower() for cmd in KNOWN_COMMANDS if not cmd.lower().startswith("open ")],
        n=1,
        cutoff=0.78
    )

    if possible:
        matched = possible[0]

        for cmd in KNOWN_COMMANDS:
            if cmd.lower() == matched:
                return cmd

    return text.strip()

def looks_like_direct_command(text):
    lower = text.lower().strip()

    return any(
        lower.startswith(prefix)
        for prefix in DIRECT_COMMAND_PREFIXES
    )

# ===============================
# LISTEN COMMAND AFTER WAKE WORD
# ===============================
def listen_for_command(timeout_seconds=10):
    print("Listening for command with VAD...")

    return collect_speech_with_vad(
        max_seconds=max(timeout_seconds, VAD_MAX_COMMAND_SECONDS),
        end_silence_seconds=VAD_END_SILENCE_SECONDS,
        min_speech_seconds=VAD_MIN_SPEECH_SECONDS,
        grammar=VOICE_GRAMMAR,
        label="command"
    )

# ===============================
# UNIVERSAL OPEN ENGINE
# Opens apps, websites, folders, files and projects.
# Uses Windows shell first, then falls back to search.
# ===============================
COMMON_APPS = {
    "calculator": {
        "commands": ["calc.exe"],
        "paths": []
    },
    "calc": {
        "commands": ["calc.exe"],
        "paths": []
    },
    "notepad": {
        "commands": ["notepad.exe"],
        "paths": []
    },
    "paint": {
        "commands": ["mspaint.exe"],
        "paths": []
    },
    "powershell": {
        "commands": ["powershell.exe"],
        "paths": []
    },
    "command prompt": {
        "commands": ["cmd.exe"],
        "paths": []
    },
    "cmd": {
        "commands": ["cmd.exe"],
        "paths": []
    },
    "task manager": {
        "commands": ["taskmgr.exe"],
        "paths": []
    },
    "control panel": {
        "commands": ["control.exe"],
        "paths": []
    },
    "settings": {
        "commands": ["ms-settings:"],
        "paths": []
    },
    "file explorer": {
        "commands": ["explorer.exe"],
        "paths": []
    },
    "explorer": {
        "commands": ["explorer.exe"],
        "paths": []
    },
    "chrome": {
        "commands": ["chrome.exe", "chrome"],
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    },
    "google chrome": {
        "commands": ["chrome.exe", "chrome"],
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    },
    "edge": {
        "commands": ["msedge.exe", "msedge"],
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
    },
    "firefox": {
        "commands": ["firefox.exe", "firefox"],
        "paths": [
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Mozilla Firefox\firefox.exe"),
        ]
    },
    "vscode": {
        "commands": ["code", "code.cmd"],
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
        ]
    },
    "visual studio code": {
        "commands": ["code", "code.cmd"],
        "paths": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            r"C:\Program Files\Microsoft VS Code\Code.exe",
        ]
    },
    "word": {
        "commands": ["winword.exe"],
        "paths": []
    },
    "excel": {
        "commands": ["excel.exe"],
        "paths": []
    },
    "powerpoint": {
        "commands": ["powerpnt.exe"],
        "paths": []
    },
    "teams": {
        "commands": ["ms-teams:", "teams.exe"],
        "paths": []
    },
    "spotify": {
        "commands": ["spotify.exe", "spotify"],
        "paths": [
            os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
        ]
    },
    "steam": {
        "commands": ["steam.exe", "steam"],
        "paths": [
            r"C:\Program Files (x86)\Steam\steam.exe",
            r"C:\Program Files\Steam\steam.exe",
        ]
    },
}


def _get_app_path_from_registry(app_exe):
    if winreg is None:
        return None

    registry_locations = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app_exe}"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{app_exe}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{app_exe}"),
    ]

    for root, key_path in registry_locations:
        try:
            with winreg.OpenKey(root, key_path) as key:
                value, _ = winreg.QueryValueEx(key, None)

                if value and os.path.exists(value):
                    return value
        except Exception:
            continue

    return None


def _start_process_target(target):
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False
        )
        return True
    except Exception:
        return False


def _launch_known_app(app_name):
    app_name = str(app_name).lower().strip()
    app_data = COMMON_APPS.get(app_name)

    if not app_data:
        return False

    # URI apps, for example ms-settings: or ms-teams:
    for command in app_data.get("commands", []):
        if command.endswith(":"):
            return _open_with_windows_shell(command)

    # 1. Try explicit common paths.
    for path in app_data.get("paths", []):
        expanded = os.path.expandvars(path)

        if expanded and os.path.exists(expanded):
            try:
                subprocess.Popen(
                    [expanded],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True
            except Exception:
                pass

    # 2. Try Windows App Paths registry.
    for command in app_data.get("commands", []):
        if command.endswith(".exe"):
            reg_path = _get_app_path_from_registry(command)

            if reg_path:
                try:
                    subprocess.Popen(
                        [reg_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return True
                except Exception:
                    pass

    # 3. Try PATH lookup.
    for command in app_data.get("commands", []):
        resolved = shutil.which(command)

        if resolved:
            try:
                subprocess.Popen(
                    [resolved],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return True
            except Exception:
                pass

    # 4. Final Windows shell fallback.
    for command in app_data.get("commands", []):
        if _start_process_target(command):
            return True

    return False


def _user_folder(name):
    home = os.path.expanduser("~")
    mapping = {
        "desktop": os.path.join(home, "Desktop"),
        "downloads": os.path.join(home, "Downloads"),
        "documents": os.path.join(home, "Documents"),
        "pictures": os.path.join(home, "Pictures"),
        "music": os.path.join(home, "Music"),
        "videos": os.path.join(home, "Videos"),
    }

    return mapping.get(name.lower().strip())


def _open_with_windows_shell(target):
    try:
        os.startfile(target)
        return True
    except Exception:
        pass

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False
        )
        return True
    except Exception:
        return False


def _looks_like_website(target):
    target = target.lower().strip()

    if target.startswith("http://") or target.startswith("https://"):
        return True

    if "." in target and " " not in target:
        return True

    return False


def _open_website(target):
    target = _clean_website_target(target)

    if not target:
        return "Website target was empty."

    if "." not in target:
        target = target + ".com"

    if not target.startswith("http://") and not target.startswith("https://"):
        target = "https://" + target

    webbrowser.open(target)
    return f"Opening website: {target}"


def _search_file_or_folder(name, max_results=1):
    name = name.lower().strip()

    if not name or "[unk]" in name:
        return None

    search_roots = [
        os.getcwd(),
        os.path.expanduser("~"),
        "D:\\",
        "E:\\",
    ]

    skip_dirs = {
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
    }

    for root_dir in search_roots:
        if not os.path.exists(root_dir):
            continue

        try:
            for root, dirs, files in os.walk(root_dir):
                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in skip_dirs
                ]

                base = os.path.basename(root).lower()

                if name == base or name in base:
                    return root

                for file_name in files:
                    lower_file = file_name.lower()

                    if name == lower_file or name in lower_file:
                        return os.path.join(root, file_name)

        except Exception:
            continue

    return None


def _normalize_open_target(target):
    target = str(target).lower().strip()
    target = target.replace("[unk]", "").strip()

    for wrong, right in APP_ALIASES.items():
        if target == wrong:
            return right

    for wrong, right in WEBSITE_ALIASES.items():
        if target == wrong:
            return right

    for wrong, right in FOLDER_ALIASES.items():
        if target == wrong:
            return right

    for wrong, right in PROJECT_ALIASES.items():
        if target == wrong:
            return right

    return target


def handle_universal_open_command(command):
    lower = command.lower().strip()

    if "[unk]" in lower:
        return "I did not understand the target clearly. Please repeat the command."

    prefixes = [
        "open website ",
        "open site ",
        "go to ",
        "visit ",
        "open folder ",
        "open file ",
        "open app ",
        "open application ",
        "open "
    ]

    used_prefix = None

    for prefix in prefixes:
        if lower.startswith(prefix):
            used_prefix = prefix
            target = command[len(prefix):].strip()
            break
    else:
        return None

    if not target:
        return "Open command detected, but no target was provided."

    target_normalized = _normalize_open_target(target)

    # Projects should stay routed to jarvis_agent because deep project memory knows their paths.
    if used_prefix in {"open project ", "open code "}:
        return None

    # Websites
    if used_prefix in {"open website ", "open site ", "go to ", "visit "}:
        return _open_website(target_normalized)

    if _looks_like_website(target_normalized):
        return _open_website(target_normalized)

    # Known user folders
    folder_path = _user_folder(target_normalized)

    if folder_path and os.path.exists(folder_path):
        _open_with_windows_shell(folder_path)
        return f"Opening folder: {folder_path}"

    # Existing absolute/relative path
    if os.path.exists(target_normalized):
        _open_with_windows_shell(target_normalized)
        return f"Opening: {target_normalized}"

    # Known apps with real executable/path resolution.
    if target_normalized in COMMON_APPS:
        if _launch_known_app(target_normalized):
            return f"Opening application: {target_normalized}"

        return f"Application found in command map, but Windows could not open it: {target_normalized}"

    # Let Windows try unknown app names.
    # This helps with apps installed in Start Menu / App Execution Aliases.
    if used_prefix in {"open ", "open app ", "open application "}:
        if _start_process_target(target_normalized):
            return f"Trying to open with Windows: {target_normalized}"

    # Search files/folders by name.
    found = _search_file_or_folder(target_normalized)

    if found:
        _open_with_windows_shell(found)
        return f"Opening found item: {found}"

    return f"Could not find or open: {target}"


def is_noise_command(command):
    lower = str(command).lower().strip()

    noise_values = {
        "",
        "hey",
        "hi",
        "hello",
        "journeys",
        "john nice",
        "hey journeys",
        "hey john nice",
        "[unk]",
        "open [unk]",
        "grandma",
        "musical",
        "try another",
        "what is retarded",
        "can you hear me",
    }

    if lower in noise_values:
        return True

    if lower.endswith("[unk]") and len(lower.split()) <= 3:
        return True

    return False

# ===============================
# EXECUTE JARVIS COMMAND
# ===============================
def execute_jarvis_command(command):
    original_command = command
    command = normalize_voice_text(command)

    if is_noise_command(command):
        print("Ignored noise command:", original_command)
        return

    if not command:
        print("No command detected.")
        speak("No command detected.")
        return

    print("Raw command:", original_command)
    print("Normalized command:", command)

    universal_result = handle_universal_open_command(command)

    if universal_result is not None:
        result = universal_result
    else:
        result = handle_command(command)

    if result == "exit":
        speak("Shutting down. Goodbye.")
        stop_hud()
        stream.stop()
        stream.close()
        sys.exit(0)

    print("\nJARVIS:\n")
    print(result)

    if VOICE_SUMMARY_MODE:
        spoken_answer = voice_summary(command, result)
    else:
        spoken_answer = str(result)

    speak(spoken_answer)



# ==========================================================
# J.A.R.V.I.S ENTERPRISE WAKE WORD + VAD REFINEMENT
# Inserted before startup so the main loop uses these overrides.
#
# Improvements:
# - more sensitive VAD for human voice
# - adaptive threshold with noise floor memory
# - faster wake detection
# - fuzzy wake-word matching
# - better command correction
# - direct support for "open project X in IDE"
# - Firefox/browser correction
# - voice statistics
# ==========================================================

WAKE_ENTERPRISE_VERSION = "J.A.R.V.I.S Enterprise Wake Word Refinement"
WAKE_STATS_FILE = "wake_word_stats.json"
WAKE_THRESHOLD_FILE = "wake_noise_profile.json"

WAKE_FUZZY_CUTOFF = 0.68
WAKE_DIRECT_COMMAND_MIN_WORDS = 2
WAKE_INSTANT_END_SILENCE = 0.55
COMMAND_END_SILENCE_FAST = 0.68
COMMAND_MIN_SPEECH_FAST = 0.16
COMMAND_MAX_SECONDS_FAST = 18

EXTRA_WAKE_WORDS = [
    "jarvis",
    "hey jarvis",
    "ok jarvis",
    "okay jarvis",
    "hi jarvis",
    "hello jarvis",
    "yo jarvis",
    "jervis",
    "hey jervis",
    "travis",
    "hey travis",
    "service",
    "hey service",
    "javascript",
    "hey javascript",
    "john nice",
    "hey john nice",
    "hey jha",
    "hey jar",
    "jar",
]

WAKE_WORDS = sorted(set(WAKE_WORDS + EXTRA_WAKE_WORDS), key=len, reverse=True)

EXTRA_DIRECT_COMMAND_PREFIXES = [
    "create ",
    "generate ",
    "make ",
    "export ",
    "give me ",
    "review ",
    "analyze ",
    "explain ",
    "debug ",
    "commander mode",
    "architect mode",
    "open manager",
    "open cyber",
    "open jarvis",
    "open browser",
]

DIRECT_COMMAND_PREFIXES = sorted(set(DIRECT_COMMAND_PREFIXES + EXTRA_DIRECT_COMMAND_PREFIXES), key=len, reverse=True)

IDE_WORDS = [
    "vs code",
    "vscode",
    "visual studio code",
    "visual studio",
    "visual studio community",
    "intellij",
    "intellij idea",
    "eclipse",
    "pycharm",
    "android studio",
    "webstorm",
    "rider",
    "clion",
    "cursor",
    "windsurf",
]


def _wake_safe_load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as file:
            return json.load(file)
    except Exception:
        return default if default is not None else {}


def _wake_safe_save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def update_wake_stats(key):
    stats = _wake_safe_load_json(WAKE_STATS_FILE, {})
    if not isinstance(stats, dict):
        stats = {}

    stats[key] = int(stats.get(key, 0) or 0) + 1
    stats["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _wake_safe_save_json(WAKE_STATS_FILE, stats)


def wake_stats_report():
    stats = _wake_safe_load_json(WAKE_STATS_FILE, {})
    if not stats:
        return "No wake statistics yet."

    lines = ["WAKE WORD STATS", ""]
    for key, value in stats.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _wake_clean_text(text):
    text = str(text or "").lower().strip()
    text = text.replace("-", " ")
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _wake_best_similarity(text, candidates):
    text = _wake_clean_text(text)
    best_candidate = ""
    best_score = 0.0

    for candidate in candidates:
        candidate = _wake_clean_text(candidate)

        if not candidate:
            continue

        if text == candidate:
            return candidate, 1.0

        if text.startswith(candidate + " ") or candidate in text:
            score = 0.92
        else:
            score = difflib.SequenceMatcher(None, text, candidate).ratio()

        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_candidate, best_score


def normalize_vosk_mistakes(text):
    text = _wake_clean_text(text)

    if not text:
        return ""

    replacements = {
        "hey jha": "hey jarvis",
        "hey jar": "hey jarvis",
        "hey jervis": "hey jarvis",
        "jervis": "jarvis",
        "travis": "jarvis",
        "service": "jarvis",
        "javascript": "jarvis",
        "hey service": "hey jarvis",
        "hey javascript": "hey jarvis",
        "john nice": "jarvis",
        "hey john nice": "hey jarvis",
        "hey journeys": "hey jarvis",
        "hey jim this": "hey jarvis",
        "hey jack this": "hey jarvis",

        "open fire": "open firefox",
        "open fire fox": "open firefox",
        "open browser fire": "open browser firefox",
        "open browser fire fox": "open browser firefox",
        "open mozilla": "open firefox",
        "open browser": "open chrome",

        "open vs": "open vscode",
        "open vs code": "open vscode",
        "open visual studio code": "open vscode",
        "visual studio called": "visual studio code",

        "cybers in the": "cybershield ai",
        "cyber shield": "cyber shield ai",
        "cyber shield ai ai": "cyber shield ai",
        "manager up": "manager app",
        "manager at": "manager app",
        "manager application": "managerapp",

        "give me report about this project in pdf": "give me a report about this project in pdf",
        "give me a report about this project and pdf": "give me a report about this project in pdf",
        "create report pdf": "create pdf report",
        "generate report pdf": "generate pdf report",
    }

    if text in replacements:
        return replacements[text]

    for wrong, right in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text)

    text = re.sub(r"\bhey\s+(jha|jar|jervis|john nice|journeys|jim this|jack this|service|javascript|travis)\b", "hey jarvis", text)
    text = re.sub(r"\b(jervis|john nice|journeys|service|javascript|travis)\b", "jarvis", text)
    text = re.sub(r"\bopen\s+fire\s+fox\b", "open firefox", text)
    text = re.sub(r"\bopen\s+fire\b", "open firefox", text)
    text = re.sub(r"\bopen\s+mozilla\b", "open firefox", text)
    text = re.sub(r"\bopen\s+browser\s+firefox\b", "open firefox", text)
    text = re.sub(r"\bopen\s+browser\s+fire\b", "open firefox", text)
    text = re.sub(r"\bopen\s+vs\s+code\b", "open vscode", text)
    text = re.sub(r"\bcybers\s+in\s+the\b", "cybershield ai", text)

    return text.strip()


def calibrate_vad_noise(seconds=VAD_CALIBRATION_SECONDS):
    """
    Faster adaptive calibration.
    Uses median + percentile to avoid one loud sample making the threshold too high.
    Saves the last stable threshold for future cycles.
    """
    print("[VAD] Fast calibrating microphone noise...")
    write_voice_state("CALIBRATING")

    values = []
    start = time.time()

    while time.time() - start < seconds:
        try:
            data = q.get(timeout=0.12)
        except queue.Empty:
            continue

        level = audio_rms(data)
        if level > 0:
            values.append(level)
        write_voice_level(min(level / 2200.0, 1.0))

    old_profile = _wake_safe_load_json(WAKE_THRESHOLD_FILE, {})

    if values:
        median = float(np.median(values))
        p75 = float(np.percentile(values, 75))
        base = max(median, p75 * 0.80)
    else:
        base = float(old_profile.get("noise", 35.0) or 35.0)

    dynamic_threshold = max(85.0, min(900.0, base * 1.75))
    previous = float(old_profile.get("threshold", dynamic_threshold) or dynamic_threshold)

    # Smooth threshold to avoid sudden bad calibration.
    threshold = (previous * 0.35) + (dynamic_threshold * 0.65)
    threshold = max(85.0, min(950.0, threshold))

    _wake_safe_save_json(WAKE_THRESHOLD_FILE, {
        "noise": round(base, 2),
        "threshold": round(threshold, 2),
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    })

    print(f"[VAD] noise={base:.1f} threshold={threshold:.1f}")
    write_voice_state("READY")
    write_voice_level(0.0)

    return threshold


def collect_speech_with_vad(
    max_seconds=VAD_MAX_COMMAND_SECONDS,
    end_silence_seconds=VAD_END_SILENCE_SECONDS,
    min_speech_seconds=VAD_MIN_SPEECH_SECONDS,
    grammar=None,
    label="command"
):
    """
    More sensitive and faster VAD.
    Captures a short pre-roll so the first word is not cut.
    """
    drain_audio_queue(max_items=20)

    if label == "wake":
        max_seconds = min(max_seconds, WAKE_RECOGNITION_SECONDS)
        end_silence_seconds = min(end_silence_seconds, WAKE_INSTANT_END_SILENCE)
        min_speech_seconds = 0.12
    else:
        max_seconds = min(max_seconds, COMMAND_MAX_SECONDS_FAST)
        end_silence_seconds = min(end_silence_seconds, COMMAND_END_SILENCE_FAST)
        min_speech_seconds = min(min_speech_seconds, COMMAND_MIN_SPEECH_FAST)

    threshold = calibrate_vad_noise()
    chunks = []
    pre_roll = []

    speech_started = False
    speech_start_time = None
    last_voice_time = None
    start_time = time.time()

    write_voice_state(f"LISTENING_{label.upper()}")
    print(f"[VAD] Listening for {label}...")

    while time.time() - start_time < max_seconds:
        try:
            data = q.get(timeout=0.18)
        except queue.Empty:
            continue

        level = audio_rms(data)
        write_voice_level(min(level / max(threshold * 2.0, 1), 1.0))

        # Slightly lower start threshold for wake, because wake is short.
        start_threshold = threshold * (0.82 if label == "wake" else 1.0)
        continue_threshold = threshold * 0.62

        is_voice = level >= (continue_threshold if speech_started else start_threshold)

        if VAD_DEBUG:
            print(f"[VAD] level={level:.0f} threshold={threshold:.0f} voice={is_voice}")

        if not speech_started:
            pre_roll.append(data)
            if len(pre_roll) > 5:
                pre_roll.pop(0)

        if is_voice:
            if not speech_started:
                speech_started = True
                speech_start_time = time.time()
                chunks.extend(pre_roll)
                print("[VAD] Speech started.")
                write_voice_state("SPEAKING")

            last_voice_time = time.time()
            chunks.append(data)

        elif speech_started:
            chunks.append(data)

            if last_voice_time and time.time() - last_voice_time >= end_silence_seconds:
                break

    write_voice_level(0.0)
    write_voice_state("PROCESSING")

    if not speech_started:
        write_voice_state("NO_SPEECH")
        return ""

    speech_duration = time.time() - (speech_start_time or time.time())

    if speech_duration < min_speech_seconds:
        write_voice_state("TOO_SHORT")
        return ""

    # Try command grammar first, then unrestricted model if grammar fails.
    text = recognize_vosk_from_chunks(chunks, grammar=grammar)
    text = normalize_vosk_mistakes(text)

    if not text or text == "[unk]":
        fallback = recognize_vosk_from_chunks(chunks, grammar=None)
        fallback = normalize_vosk_mistakes(fallback)
        if fallback:
            text = fallback

    write_voice_state("READY")

    if text:
        update_wake_stats(f"{label}_recognized")
        print(f"[VAD] Recognized {label}: {text}")
    else:
        update_wake_stats(f"{label}_unrecognized")
        print(f"[VAD] Could not recognize {label}.")

    return text


def is_wake_text(text):
    text = normalize_vosk_mistakes(text)

    if not text:
        return False

    if text in WAKE_WORDS:
        update_wake_stats("wake_exact")
        return True

    if text.startswith(("hey jarvis", "ok jarvis", "okay jarvis", "hi jarvis", "hello jarvis", "jarvis")):
        update_wake_stats("wake_prefix")
        return True

    candidate, score = _wake_best_similarity(text, WAKE_WORDS)

    if score >= WAKE_FUZZY_CUTOFF:
        print(f"[WAKE] fuzzy match: '{text}' -> '{candidate}' ({score:.2f})")
        update_wake_stats("wake_fuzzy")
        return True

    # If text contains a direct command, allow hands-free mode without explicit wake.
    normalized = normalize_voice_text(text)
    if looks_like_direct_command(normalized):
        return False

    return False


def strip_wake_from_command(text):
    text = normalize_vosk_mistakes(text)

    for wake in sorted(WAKE_WORDS, key=len, reverse=True):
        wake = wake.lower()
        if text.startswith(wake + " "):
            return text[len(wake):].strip()

    # Fuzzy wake at beginning, for variants like "service open firefox"
    words = text.split()
    if words:
        first_two = " ".join(words[:2])
        first_one = words[0]

        candidate, score = _wake_best_similarity(first_two, WAKE_WORDS)
        if score >= WAKE_FUZZY_CUTOFF and len(words) > 2:
            return " ".join(words[2:]).strip()

        candidate, score = _wake_best_similarity(first_one, WAKE_WORDS)
        if score >= WAKE_FUZZY_CUTOFF and len(words) > 1:
            return " ".join(words[1:]).strip()

    if text in {"jarvis", "hey jarvis", "ok jarvis", "okay jarvis", "hi jarvis", "hello jarvis"}:
        return ""

    return text


def _normalize_project_ide_voice(text):
    """
    Normalizes project+IDE commands before sending to jarvis_agent.
    """
    lower = normalize_vosk_mistakes(text)
    lower = _wake_clean_text(lower)

    project_aliases = {
        "cyber": "CyberShield AI",
        "cyber shield": "CyberShield AI",
        "cyber shield ai": "CyberShield AI",
        "cybershield": "CyberShield AI",
        "cybershield ai": "CyberShield AI",
        "jarvis": "J.A.R.V.I.S",
        "jervis": "J.A.R.V.I.S",
        "manager app": "ManagerApp",
        "managerapp": "ManagerApp",
    }

    ide_aliases = {
        "vs code": "VS Code",
        "vscode": "VS Code",
        "visual studio code": "VS Code",
        "visual studio": "Visual Studio Community",
        "visual studio community": "Visual Studio Community",
        "intellij": "IntelliJ",
        "intelli j": "IntelliJ",
        "intellij idea": "IntelliJ",
        "eclipse": "Eclipse",
        "pycharm": "PyCharm",
        "android studio": "Android Studio",
        "webstorm": "WebStorm",
        "rider": "Rider",
        "cursor": "Cursor",
        "windsurf": "Windsurf",
    }

    ide_pattern = "|".join(re.escape(k) for k in sorted(ide_aliases, key=len, reverse=True))
    patterns = [
        rf"^(?:open|launch|start|edit)\s+(?:project\s+)?(.+?)\s+(?:in|with|using)\s+({ide_pattern})$",
        rf"^(?:open|launch|start|edit)\s+(.+?)\s+project\s+(?:in|with|using)\s+({ide_pattern})$",
    ]

    for pattern in patterns:
        match = re.match(pattern, lower, flags=re.IGNORECASE)
        if match:
            project = match.group(1).strip()
            ide = match.group(2).strip()
            project = project_aliases.get(project, project)
            ide = ide_aliases.get(ide, ide)
            return f"open project {project} in {ide}"

    return text


def normalize_voice_text(text):
    text = normalize_vosk_mistakes(text)
    text = str(text).lower().strip()

    if not text:
        return ""

    text = _strip_wake_words(text)
    text = normalize_vosk_mistakes(text)
    text = _normalize_project_ide_voice(text)
    text = _normalize_projects(text)
    text = _normalize_websites(text)
    text = _normalize_apps_and_folders(text)

    if text in {"daily project", "project check", "daily"}:
        text = "daily check"

    if text.startswith("search google"):
        return "open website google.com"

    # Natural fast report command.
    if "report" in text and "pdf" in text and ("this project" in text or "current project" in text):
        return "create pdf report for project CyberShield AI"

    if text.startswith(("create ", "generate ", "make ", "export ", "give me ")):
        return text.strip()

    universal_open_prefixes = (
        "open ",
        "open website ",
        "open site ",
        "go to ",
        "visit ",
        "open folder ",
        "open file ",
        "open app ",
        "open application ",
    )

    if text.lower().startswith(universal_open_prefixes):
        return text.strip()

    possible = difflib.get_close_matches(
        text.lower(),
        [cmd.lower() for cmd in KNOWN_COMMANDS if not cmd.lower().startswith("open ")],
        n=1,
        cutoff=0.74
    )

    if possible:
        matched = possible[0]

        for cmd in KNOWN_COMMANDS:
            if cmd.lower() == matched:
                return cmd

    return text.strip()


def looks_like_direct_command(text):
    lower = normalize_vosk_mistakes(text).lower().strip()

    if not lower or lower in {"hey", "hi", "hello", "[unk]"}:
        return False

    if any(lower.startswith(prefix) for prefix in DIRECT_COMMAND_PREFIXES):
        words = lower.split()
        return len(words) >= WAKE_DIRECT_COMMAND_MIN_WORDS

    # Direct project+IDE commands can run without wake.
    if re.match(r"^(?:open|launch|start|edit)\s+.+?\s+(?:in|with|using)\s+(" + "|".join(re.escape(i) for i in IDE_WORDS) + r")$", lower):
        return True

    return False


def listen_for_command(timeout_seconds=10):
    print("Listening for command with fast VAD...")

    return collect_speech_with_vad(
        max_seconds=min(max(timeout_seconds, 8), COMMAND_MAX_SECONDS_FAST),
        end_silence_seconds=COMMAND_END_SILENCE_FAST,
        min_speech_seconds=COMMAND_MIN_SPEECH_FAST,
        grammar=VOICE_GRAMMAR,
        label="command"
    )


def is_noise_command(command):
    lower = str(command).lower().strip()

    noise_values = {
        "",
        "hey",
        "hi",
        "hello",
        "journeys",
        "john nice",
        "hey journeys",
        "hey john nice",
        "[unk]",
        "open [unk]",
        "grandma",
        "musical",
        "try another",
        "what is retarded",
        "can you hear me",
        "thank you",
        "thanks",
        "okay",
        "ok",
    }

    if lower in noise_values:
        return True

    if lower.endswith("[unk]") and len(lower.split()) <= 3:
        return True

    # Do not treat real open/report commands as noise.
    if looks_like_direct_command(lower):
        return False

    return False


def execute_jarvis_command(command):
    original_command = command
    command = normalize_voice_text(command)

    if is_noise_command(command):
        print("Ignored noise command:", original_command)
        update_wake_stats("noise_ignored")
        return

    if not command:
        print("No command detected.")
        speak("No command detected.")
        return

    print("Raw command:", original_command)
    print("Normalized command:", command)
    update_wake_stats("commands_executed")

    universal_result = handle_universal_open_command(command)

    if universal_result is not None:
        result = universal_result
    else:
        result = handle_command(command)

    if result == "exit":
        speak("Shutting down. Goodbye.")
        stop_hud()
        stream.stop()
        stream.close()
        sys.exit(0)

    print("\nJARVIS:\n")
    print(result)

    if VOICE_SUMMARY_MODE:
        spoken_answer = voice_summary(command, result)
    else:
        spoken_answer = str(result)

    speak(spoken_answer)


def wake_word_self_test():
    tests = [
        "hey jha",
        "hey service",
        "travis",
        "javascript open firefox",
        "hey jarvis open fire",
        "open browser fire fox",
        "open project cyber shield ai in vs code",
        "open manager app in intellij",
        "give me a report about this project in pdf",
    ]

    output = [
        "WAKE WORD SELF TEST",
        f"Version: {WAKE_ENTERPRISE_VERSION}",
        "",
    ]

    for raw in tests:
        normalized = normalize_vosk_mistakes(raw)
        wake = is_wake_text(raw)
        command = strip_wake_from_command(raw)
        final = normalize_voice_text(raw)
        output.append(f"RAW: {raw}")
        output.append(f"NORMALIZED: {normalized}")
        output.append(f"IS_WAKE: {wake}")
        output.append(f"STRIPPED: {command}")
        output.append(f"FINAL: {final}")
        output.append("")

    return "\n".join(output)



# ===============================
# STARTUP
# ===============================
print("JARVIS online (stand-by)")
start_hud()
speak("JARVIS online and standing by.")

last_activation = 0
MIN_DELAY = 0.75

# ===============================
# MAIN LOOP - ENTERPRISE VAD
# ===============================
try:
    # Calibrate once at startup so the first command is more stable.
    try:
        calibrate_vad_noise()
    except Exception:
        pass

    while True:
        text = collect_speech_with_vad(
            max_seconds=WAKE_RECOGNITION_SECONDS,
            end_silence_seconds=WAKE_INSTANT_END_SILENCE,
            min_speech_seconds=0.12,
            grammar=VOICE_GRAMMAR,
            label="wake"
        )

        if not text:
            continue

        print("Heard:", text)

        # SHUTDOWN
        if any(cmd in text for cmd in SHUTDOWN_WORDS):
            print("JARVIS shutting down...")
            speak("Shutting down. Goodbye.")
            stop_hud()
            stream.stop()
            stream.close()
            sys.exit(0)

        # ANTI-SPAM
        if time.time() - last_activation < MIN_DELAY:
            continue

        normalized_text = normalize_voice_text(text)

        if is_noise_command(normalized_text):
            continue

        # DIRECT COMMAND MODE
        # Clear commands can run without wake word.
        if looks_like_direct_command(normalized_text):
            last_activation = time.time()
            print("DIRECT COMMAND DETECTED")
            execute_jarvis_command(normalized_text)
            continue

        # ACTIVATION
        if is_wake_text(text):
            last_activation = time.time()
            print("JARVIS ACTIVATED")
            play_activation()
            speak("Yes Sir, how may I help you today?")

            command = strip_wake_from_command(text)

            # If user says only "Jarvis", listen with VAD for the real command.
            if not command:
                command = listen_for_command(timeout_seconds=VAD_MAX_COMMAND_SECONDS)

            if not command:
                speak("I did not hear a command. Returning to standby.")
                continue

            execute_jarvis_command(command)

except KeyboardInterrupt:
    print("\nManual shutdown")
    stop_hud()
    stream.stop()
    stream.close()
