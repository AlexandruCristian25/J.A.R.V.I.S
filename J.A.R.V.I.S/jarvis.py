# jarvis.py
import speech_recognition as sr
import pyttsx3
import os
import subprocess
import platform
import time
from pathlib import Path
import PyPDF2

# CONFIG
WAKE_WORD = "jarvis"
VOICE_LANGUAGE = "en"  # limbă de recunoaștere (speech_recognition folosește engleză implicit la Google)
ROOT_SEARCH_PATHS = [str(Path.home())]  # unde caută fișiere (poți adăuga "C:\\Users\\You\\Documents")

# Init TTS
tts = pyttsx3.init()
# Optionally set voice properties
tts.setProperty("rate", 160)  # viteză
tts.setProperty("volume", 1.0)

def speak(text):
    print("JARVIS (speaks):", text)
    tts.say(text)
    tts.runAndWait()

# STT init
recognizer = sr.Recognizer()
mic = sr.Microphone()

def listen(timeout=None, phrase_time_limit=None):
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.6)
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            # Use Google Web Speech API (default) - requires internet.
            text = recognizer.recognize_google(audio, language="en-US")
            return text.lower()
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            # network error or API unavailable
            print("STT request error:", e)
            return ""

# Helper: open file with default app
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
        else:  # linux
            subprocess.Popen(["xdg-open", path])
        speak(f"Opened {os.path.basename(path)}")
    except Exception as e:
        speak(f"Failed to open {os.path.basename(path)}: {e}")

# Helper: search for files by name pattern
def search_files(query, max_results=5):
    results = []
    q_lower = query.lower()
    for root in ROOT_SEARCH_PATHS:
        for dirpath, dirnames, filenames in os.walk(root):
            for f in filenames:
                if q_lower in f.lower():
                    results.append(os.path.join(dirpath, f))
                    if len(results) >= max_results:
                        return results
    return results

# Helper: read text file or PDF (first N chars/pages)
def read_file(path, max_chars=1500):
    path = str(path)
    if not os.path.exists(path):
        speak("File not found.")
        return
    ext = Path(path).suffix.lower()
    try:
        if ext in ['.txt', '.md', '.py', '.csv']:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read(max_chars)
                speak(text if text else "File is empty.")
        elif ext in ['.pdf']:
            with open(path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                if len(reader.pages) > 0:
                    page0 = reader.pages[0]
                    text = page0.extract_text() or ""
                    speak(text[:max_chars] if text else "I couldn't extract text from that PDF.")
                else:
                    speak("PDF has no pages.")
        else:
            speak("I can only read simple text files and PDFs for now.")
    except Exception as e:
        speak(f"Error reading file: {e}")

# Handle recognized command text
def handle_command(text):
    print("Heard:", text)
    if not text:
        return

    # Basic commands
    if text.startswith("open "):
        target = text.replace("open ", "", 1).strip()
        # search for file or app
        files = search_files(target, max_results=3)
        if files:
            open_with_default(files[0])
        else:
            # try to open application by name (windows: start)
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

    if text.startswith("search for "):
        target = text.replace("search for ", "", 1).strip()
        results = search_files(target, max_results=5)
        if results:
            speak(f"I found {len(results)} items. Opening first match.")
            open_with_default(results[0])
        else:
            speak("I couldn't find anything with that name.")
        return

    if text.startswith("read ") or "read file" in text:
        # try to parse filename
        target = text.replace("read ", "", 1).replace("read file ", "", 1).strip()
        files = search_files(target, max_results=3)
        if files:
            read_file(files[0])
        else:
            speak("I couldn't find that file to read.")
        return

    if "time" in text:
        speak(time.strftime("It is %H:%M on %A, %B %d, %Y"))
        return

    if "hello" in text or "hi" in text:
        speak("Hello. How can I help you today?")
        return

    if "stop listening" in text or "goodbye" in text or "shutdown" in text:
        speak("Shutting down. Bye!")
        raise SystemExit

    # fallback
    speak("I didn't understand exactly. I can open files, search, read files, tell the time. Try: 'Jarvis open resume pdf' or 'Jarvis read project notes'.")

def main_loop():
    speak("J. A. R. V. I. S. here. I'm listening.")
    while True:
        print("Listening for wake word...")
        text = listen(timeout=5, phrase_time_limit=6)
        if not text:
            continue
        print("Detected:", text)
        if WAKE_WORD in text:
            # remove wake-word from text and treat rest as command
            command = text.replace(WAKE_WORD, "").strip()
            if not command:
                speak("Yes?")
                # listen for the next phrase (the real command)
                command = listen(timeout=6, phrase_time_limit=8)
            if command:
                handle_command(command)
            else:
                speak("I didn't catch the command.")
        # else: ignore until wake word

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("Exiting...")
        speak("Goodbye.")
