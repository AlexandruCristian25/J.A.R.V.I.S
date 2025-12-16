"""
JARVIS: Vosk STT offline + fallback OpenAI GPT (dacă ai cheie API).
 - Wake word: "jarvis"
 - Offline comenzi de bază: open/search/read/time
 - Dacă nu înțelege comanda, iar OPENAI_API_KEY este setat, trimite la GPT pentru interpretare.
"""

import os, sys, queue, threading, subprocess, platform, time, json
from pathlib import Path
import pyttsx3, PyPDF2
import sounddevice as sd
from vosk import Model, KaldiRecognizer

# ===== CONFIG =====
MODEL_PATH = "models/vosk-model-small-en-us-0.15"  # schimbă dacă ai alt model
SAMPLE_RATE = 16000
WAKE_WORD = "jarvis"
ROOT_SEARCH_PATHS = [str(Path.home())]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # setează înainte: $env:OPENAI_API_KEY="cheia_ta"
# ==================

# TTS init
tts = pyttsx3.init()
tts.setProperty("rate", 150)
tts.setProperty("volume", 1.0)

def speak(text):
    print("JARVIS:", text)
    tts.say(text)
    tts.runAndWait()

# Load Vosk model
if not os.path.exists(MODEL_PATH):
    print(f"Model not found at {MODEL_PATH}.")
    sys.exit(1)
print("Loading Vosk model...")
model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)
audio_q = queue.Queue()

# Helpers
def open_with_default(path):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        speak(f"I couldn't find {path}")
        return
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        speak(f"Opened {os.path.basename(path)}")
    except Exception as e:
        speak(f"Failed to open {os.path.basename(path)}: {e}")

def search_files(query, max_results=5):
    results = []
    q = query.lower()
    for root in ROOT_SEARCH_PATHS:
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                if q in f.lower():
                    results.append(os.path.join(dirpath, f))
                    if len(results) >= max_results:
                        return results
    return results

def read_file(path, max_chars=1500):
    ext = Path(path).suffix.lower()
    try:
        if ext in [".txt", ".md", ".py", ".csv"]:
            text = open(path, encoding="utf-8", errors="ignore").read(max_chars)
            speak(text if text else "File is empty.")
        elif ext == ".pdf":
            reader = PyPDF2.PdfReader(open(path, "rb"))
            if reader.pages:
                text = reader.pages[0].extract_text() or ""
                speak(text[:max_chars] if text else "No text found in PDF.")
            else:
                speak("PDF has no pages.")
        else:
            speak("I only support text and PDF files.")
    except Exception as e:
        speak(f"Error reading file: {e}")

def handle_command(cmd):
    cmd = cmd.lower().strip()
    if not cmd:
        return

    if cmd.startswith("open "):
        files = search_files(cmd.replace("open ", "", 1), 3)
        if files: open_with_default(files[0])
        else: speak("Couldn't find that file.")
        return

    if cmd.startswith("search for "):
        files = search_files(cmd.replace("search for ", "", 1), 5)
        if files: open_with_default(files[0])
        else: speak("No results found.")
        return

    if cmd.startswith("read "):
        files = search_files(cmd.replace("read ", "", 1), 3)
        if files: read_file(files[0])
        else: speak("Couldn't find file to read.")
        return

    if "time" in cmd:
        speak(time.strftime("It is %H:%M on %A, %B %d, %Y"))
        return

    if cmd in ["hello", "hi"]:
        speak("Hello. How can I help you?")
        return

    if "shutdown" in cmd or "stop listening" in cmd:
        speak("Shutting down. Bye.")
        sys.exit(0)

    # dacă avem OpenAI pentru fallback
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "You are JARVIS, a helpful desktop assistant."},
                          {"role": "user", "content": cmd}]
            )
            answer = resp.choices[0].message.content.strip()
            speak(answer)
        except Exception as e:
            speak(f"OpenAI fallback error: {e}")
    else:
        speak("I didn't understand and no AI fallback is configured.")

# Audio
def audio_callback(indata, frames, time_info, status):
    if status: print("Audio:", status)
    audio_q.put(bytes(indata))

def recognition_loop():
    while True:
        chunk = audio_q.get()
        if chunk is None: break
        if recognizer.AcceptWaveform(chunk):
            text = json.loads(recognizer.Result()).get("text", "")
            if text:
                print("Heard:", text)
                if WAKE_WORD in text:
                    command = text.replace(WAKE_WORD, "").strip()
                    if not command:
                        speak("Yes?")
                        continue
                    handle_command(command)

def main():
    speak("JARVIS ready. Say 'Jarvis' before your command.")
    threading.Thread(target=recognition_loop, daemon=True).start()
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000, dtype='int16',
                           channels=1, callback=audio_callback):
        print("Listening... Press Ctrl+C to exit.")
        while True: time.sleep(0.1)

if __name__ == "__main__":
    main()
