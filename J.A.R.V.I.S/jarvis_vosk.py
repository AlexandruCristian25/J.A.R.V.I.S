"""
jarvis_vosk.py
Varianta offline (Vosk STT + pyttsx3 TTS).
Funcții:
 - wake word: "jarvis"
 - ascultă comenzi în engleză
 - caută fișiere, deschide fișiere, citește text din .txt/.pdf
 - folosește Vosk model local (config: MODEL_PATH)
 - rulabil cross-platform (Windows/macOS/Linux)
"""

import os
import sys
import queue
import threading
import subprocess
import platform
import time
from pathlib import Path

# STT (Vosk) and audio
try:
    from vosk import Model, KaldiRecognizer
    import sounddevice as sd
except Exception as e:
    print("Missing vosk or sounddevice. Install with: pip install vosk sounddevice")
    raise

# TTS
try:
    import pyttsx3
except Exception as e:
    print("Missing pyttsx3. Install with: pip install pyttsx3")
    raise

# PDF reading
try:
    import PyPDF2
except Exception as e:
    print("Missing PyPDF2. Install with: pip install PyPDF2")
    raise

# -------------------- CONFIG --------------------
MODEL_PATH = "models/vosk-model-small-en-us-0.15"  # schimba dacă ai alt model
SAMPLE_RATE = 16000  # ideal pentru majoritatea modelelor Vosk small
WAKE_WORD = "jarvis"
ROOT_SEARCH_PATHS = [str(Path.home())]  # poți adăuga și "C:\\Users\\You\\Documents"
TTS_RATE = 150
TTS_VOLUME = 1.0
# ------------------------------------------------

if not os.path.exists(MODEL_PATH):
    print(f"Model not found at {MODEL_PATH}. Please download and extract a Vosk model there.")
    sys.exit(1)

# Init model
print("Loading Vosk model (this may take a few seconds)...")
model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)

# audio queue to avoid blocking
audio_q = queue.Queue()

# init TTS
tts = pyttsx3.init()
tts.setProperty("rate", TTS_RATE)
tts.setProperty("volume", TTS_VOLUME)

def speak(text):
    """Speak text (non-blocking wrapper)."""
    print("JARVIS:", text)
    # run in thread to avoid blocking main loop
    def _say():
        tts.say(text)
        tts.runAndWait()
    th = threading.Thread(target=_say, daemon=True)
    th.start()

# Helper: open file with default application
def open_with_default(path):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        speak(f"I couldn't find {path}")
        return
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        speak(f"Opened {os.path.basename(path)}")
    except Exception as e:
        speak(f"Failed to open {os.path.basename(path)}: {str(e)}")

# Search files by substring (case-insensitive)
def search_files(query, max_results=10):
    results = []
    q = query.lower()
    for root in ROOT_SEARCH_PATHS:
        for dirpath, dirnames, filenames in os.walk(root):
            for f in filenames:
                if q in f.lower():
                    results.append(os.path.join(dirpath, f))
                    if len(results) >= max_results:
                        return results
    return results

# Read simple text or first page of PDF
def read_file(path, max_chars=1500):
    if not os.path.exists(path):
        speak("File not found.")
        return
    ext = Path(path).suffix.lower()
    try:
        if ext in ['.txt', '.md', '.py', '.csv']:
            with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                text = fh.read(max_chars)
                speak(text if text else "File is empty.")
        elif ext in ['.pdf']:
            with open(path, 'rb') as fh:
                reader = PyPDF2.PdfReader(fh)
                if len(reader.pages) > 0:
                    text = reader.pages[0].extract_text() or ""
                    speak(text[:max_chars] if text else "I couldn't extract text from that PDF.")
                else:
                    speak("PDF has no pages.")
        else:
            speak("I can only read plain text and PDFs for now.")
    except Exception as e:
        speak(f"Error reading file: {str(e)}")

# Basic command handler
def handle_command(text):
    text = text.lower().strip()
    print("Command:", text)
    if not text:
        return

    # open <name>
    if text.startswith("open "):
        target = text.replace("open ", "", 1).strip()
        files = search_files(target, max_results=3)
        if files:
            open_with_default(files[0])
        else:
            # try open application by name (best-effort)
            try:
                if platform.system() == "Windows":
                    subprocess.Popen(["start", "", target], shell=True)
                elif platform.system() == "Darwin":
                    subprocess.Popen(["open", "-a", target])
                else:
                    subprocess.Popen([target])
                speak(f"Attempting to open {target}")
            except Exception:
                speak(f"I couldn't find or open {target}")
        return

    # search for <name>
    if text.startswith("search for "):
        target = text.replace("search for ", "", 1).strip()
        results = search_files(target, max_results=5)
        if results:
            speak(f"I found {len(results)} items. Opening first match.")
            open_with_default(results[0])
        else:
            speak("I couldn't find anything with that name.")
        return

    # read <name>
    if text.startswith("read ") or "read file" in text:
        # attempt to extract filename phrase
        target = text.replace("read ", "", 1).replace("read file ", "", 1).strip()
        files = search_files(target, max_results=3)
        if files:
            read_file(files[0])
        else:
            speak("I couldn't find that file to read.")
        return

    # time
    if "time" in text:
        speak(time.strftime("It is %H:%M on %A, %B %d, %Y"))
        return

    # greetings
    if "hello" in text or "hi" in text:
        speak("Hello. How can I help you today?")
        return

    if "stop listening" in text or "shutdown" in text or "goodbye" in text:
        speak("Shutting down. Goodbye.")
        os._exit(0)

    # fallback
    speak("I didn't understand. Try: 'Jarvis open resume pdf', 'Jarvis read notes', 'Jarvis search for budget spreadsheet', or 'Jarvis what time is it'.")

# Audio callback: push recorded data to queue
def audio_callback(indata, frames, time_info, status):
    if status:
        print("Audio status:", status)
    audio_q.put(bytes(indata))

def recognition_loop():
    """Consume audio chunks from queue and feed Vosk recognizer."""
    buffer = b""
    while True:
        try:
            chunk = audio_q.get()
            if chunk is None:
                break
            if recognizer.AcceptWaveform(chunk):
                result = recognizer.Result()
                # result is JSON string; extract text
                import json
                j = json.loads(result)
                text = j.get("text", "")
                if text:
                    print("Heard (final):", text)
                    # check for wakeword
                    if WAKE_WORD in text:
                        # remove wake word and treat rest as command if present
                        command = text.replace(WAKE_WORD, "").strip()
                        if not command:
                            speak("Yes?")
                            # wait for next phrase (we will gather next partials)
                            # collect next recognized utterance (blocking-ish)
                            # simpler: continue and let next Vosk result be processed
                            continue
                        handle_command(command)
                else:
                    # no final text
                    pass
            else:
                # partial result - could inspect if desired:
                # partial = recognizer.PartialResult()
                # print("Partial:", partial)
                pass
        except Exception as e:
            print("Recognition loop error:", e)
            break

def main():
    # Start recognition thread
    th = threading.Thread(target=recognition_loop, daemon=True)
    th.start()
    speak("J. A. R. V. I. S. is ready and listening. Say 'Jarvis' before commands.")
    # open input audio stream
    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize = 8000, dtype='int16',
                               channels=1, callback=audio_callback):
            print("Listening (press Ctrl+C to stop)...")
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("Exiting...")
    except Exception as e:
        print("Audio input error:", e)
        speak("Audio input error. Check microphone and permissions.")
    finally:
        audio_q.put(None)  # stop recognition loop

if __name__ == "__main__":
    main()
