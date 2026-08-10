"""
JARVIS Mark XLVI Voice Adapter
------------------------------

Voice extracted/adapted from the Mark-XLVI archive TTS system.

Default Mark XLVI voice:
- Engine: Microsoft Edge TTS
- Voice: en-US-GuyNeural

Optional engines included:
- EdgeTTS: online, free, no API key
- Kokoro: offline neural TTS, first run downloads model
- ElevenLabs: cloud TTS, needs API key

Recommended integration:
1. Put this file next to simple_voice_commands.py
2. Install requirements:
   pip install edge-tts miniaudio sounddevice numpy
3. In your JARVIS file, replace old speak() with:
   from jarvis_mark46_voice import speak, stop_voice
"""

from __future__ import annotations

import asyncio
import os
import queue
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd


# Faster startup / avoids unnecessary TensorFlow loading in some TTS stacks.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


# ==========================
# AUDIO HELPERS
# ==========================
def _to_numpy(samples) -> np.ndarray:
    """Convert audio samples to float32 numpy array."""
    if hasattr(samples, "detach"):
        tensor = samples.detach().cpu().float()

        try:
            return tensor.numpy()
        except RuntimeError:
            return np.asarray(tensor.tolist(), dtype=np.float32)

    return np.asarray(samples, dtype=np.float32)


def _compress_silence(
    arr: np.ndarray,
    sample_rate: int = 24000,
    max_silence_ms: int = 500,
    threshold: float = 0.003,
) -> np.ndarray:
    """Shortens long silence pauses while keeping the voice natural."""
    max_samples = int(max_silence_ms * sample_rate / 1000)
    frame_len = 240
    output = []
    silent_acc = 0

    for index in range(0, len(arr), frame_len):
        chunk = arr[index:index + frame_len]

        if np.sqrt(np.mean(chunk ** 2) + 1e-12) < threshold:
            silent_acc += len(chunk)

            if silent_acc <= max_samples:
                output.append(chunk)
        else:
            silent_acc = 0
            output.append(chunk)

    return np.concatenate(output) if output else arr


def _play_np(samples, sample_rate: int) -> None:
    sd.play(_to_numpy(samples), sample_rate)
    sd.wait()


def _play_audio_bytes(audio_bytes: bytes) -> None:
    import miniaudio

    decoded = miniaudio.decode(
        audio_bytes,
        output_format=miniaudio.SampleFormat.FLOAT32,
        nchannels=1,
    )

    samples = np.array(decoded.samples, dtype=np.float32)

    sd.play(samples, decoded.sample_rate)
    sd.wait()


# ==========================
# EDGE TTS - DEFAULT MARK XLVI VOICE
# ==========================
class EdgeTTSEngine:
    """
    Microsoft Edge TTS.

    This is the default voice style used by Mark XLVI:
    en-US-GuyNeural
    """

    def __init__(self, voice: str = "en-US-GuyNeural"):
        self.voice = voice

    def speak(self, text: str) -> None:
        if not text or not str(text).strip():
            return

        loop = asyncio.new_event_loop()

        try:
            audio_bytes = loop.run_until_complete(
                self._synth(str(text))
            )
        finally:
            loop.close()

        if audio_bytes:
            _play_audio_bytes(audio_bytes)

    async def _synth(self, text: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            self.voice
        )

        audio_buffer = bytearray()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])

        return bytes(audio_buffer)


# ==========================
# KOKORO TTS - OPTIONAL OFFLINE VOICE
# ==========================
_KOKORO_COMPAT_ERRORS = (
    "AlbertModel",
    "AutoModel",
    "cannot import name",
)


_KOKORO_LANG_CODES = {
    "a": "a",  # American English
    "b": "b",  # British English
    "j": "j",  # Japanese
    "z": "z",  # Mandarin Chinese
    "s": "s",  # Spanish
    "f": "f",  # French
    "h": "h",  # Hindi
    "i": "i",  # Italian
    "p": "p",  # Brazilian Portuguese
    "r": "r",  # Russian
    "e": "e",  # German
}


def _import_kokoro_pipeline():
    import subprocess
    import sys

    def _try_import():
        from kokoro import KPipeline
        return KPipeline

    try:
        return _try_import()
    except Exception as first_error:
        message = str(first_error)

        if not any(marker in message for marker in _KOKORO_COMPAT_ERRORS):
            raise RuntimeError(
                f"Kokoro import failed: {first_error}\n"
                "Run: pip install kokoro>=0.9 soundfile"
            ) from first_error

        print("[TTS] Kokoro/transformers mismatch detected. Updating Kokoro...")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "kokoro>=0.9",
                "--upgrade",
                "--quiet",
                "--disable-pip-version-check",
            ],
            capture_output=True,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()

            raise RuntimeError(
                f"Kokoro auto-upgrade failed: {stderr[:200]}\n"
                "Run manually: pip install kokoro>=0.9 soundfile"
            ) from first_error

        stale_modules = [
            key for key in sys.modules
            if key == "kokoro" or key.startswith("kokoro.")
        ]

        for key in stale_modules:
            del sys.modules[key]

        return _try_import()


class KokoroTTSEngine:
    """
    Optional offline neural TTS.

    Default Kokoro voice from Mark XLVI:
    af_heart
    """

    def __init__(self, voice: str = "af_heart", speed: float = 1.0):
        self.voice = voice
        self.speed = speed
        self._pipeline = None
        self._lock = threading.Lock()
        self._init()

    @property
    def _lang_code(self) -> str:
        prefix = self.voice[0].lower() if self.voice else "a"
        return _KOKORO_LANG_CODES.get(prefix, "a")

    def _init(self) -> None:
        if self._pipeline is not None:
            return

        lang = self._lang_code

        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"

            if device == "cpu":
                threads = max(
                    1,
                    min(4, (os.cpu_count() or 4) // 2)
                )

                try:
                    torch.set_num_threads(threads)
                    torch.set_num_interop_threads(2)
                except RuntimeError:
                    pass

        except Exception:
            device = "cpu"

        print(f"[TTS] Kokoro loading lang={lang}, device={device}...")

        KPipeline = _import_kokoro_pipeline()

        def create_pipeline():
            try:
                return KPipeline(
                    lang_code=lang,
                    device=device
                )
            except TypeError:
                return KPipeline(lang_code=lang)

        try:
            self._pipeline = create_pipeline()
        except Exception as first_error:
            error_text = str(first_error).lower()

            offline_keywords = (
                "offline",
                "not found",
                "cache",
                "localentry",
                "does not exist",
                "outgoing",
                "local_files_only",
            )

            if any(keyword in error_text for keyword in offline_keywords):
                print("[TTS] Kokoro model not cached. Downloading once...")

                os.environ.pop("HF_HUB_OFFLINE", None)
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
                os.environ.pop("HF_DATASETS_OFFLINE", None)

                self._pipeline = create_pipeline()
            else:
                raise

        try:
            for _ in self._pipeline(
                "hello",
                voice=self.voice,
                speed=self.speed
            ):
                pass

            print("[TTS] Kokoro ready.")
        except Exception as error:
            print(f"[TTS] Kokoro warmup warning: {error}")

    def speak(self, text: str) -> None:
        if not text or not str(text).strip():
            return

        with self._lock:
            if self._pipeline is None:
                self._init()

        audio_queue: "queue.Queue[np.ndarray | None]" = queue.Queue(
            maxsize=4
        )
        synth_errors = []

        def synthesize():
            try:
                for _, _, audio in self._pipeline(
                    str(text),
                    voice=self.voice,
                    speed=self.speed
                ):
                    if audio is not None:
                        arr = _to_numpy(audio)
                        arr = _compress_silence(arr)

                        if arr.size > 0:
                            audio_queue.put(arr)
            except Exception as error:
                synth_errors.append(error)
            finally:
                audio_queue.put(None)

        synth_thread = threading.Thread(
            target=synthesize,
            daemon=True
        )
        synth_thread.start()

        while True:
            arr = audio_queue.get()

            if arr is None:
                break

            _play_np(arr, 24000)

        synth_thread.join()

        if synth_errors:
            raise synth_errors[0]


# ==========================
# ELEVENLABS - OPTIONAL CLOUD VOICE
# ==========================
class ElevenLabsTTSEngine:
    def __init__(
        self,
        api_key: str,
        voice_id: str = "pNInz6obpgDQGcFmaJgB"
    ):
        self.api_key = api_key
        self.voice_id = voice_id

    def speak(self, text: str) -> None:
        if not text or not str(text).strip():
            return

        import requests

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "text": str(text),
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
            },
        }

        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}",
            json=payload,
            headers=headers,
            timeout=30,
        )

        response.raise_for_status()
        _play_audio_bytes(response.content)


# ==========================
# THREAD-SAFE PLAYER
# ==========================
class TTSPlayer:
    def __init__(self, engine):
        self._engine = engine
        self._playing = False
        self._lock = threading.Lock()

    @property
    def is_playing(self) -> bool:
        return self._playing

    def speak(
        self,
        text: str,
        on_start: Optional[Callable] = None,
        on_done: Optional[Callable] = None,
    ) -> None:
        try:
            with self._lock:
                self._playing = True

            if on_start:
                on_start()

            self._engine.speak(text)

        except Exception as error:
            print(f"[TTS] Error: {error}")

        finally:
            with self._lock:
                self._playing = False

            if on_done:
                on_done()

    def stop(self) -> None:
        sd.stop()

        with self._lock:
            self._playing = False


# ==========================
# FACTORY + GLOBAL SHORTCUTS
# ==========================
def create_tts_player(config: dict | None = None) -> TTSPlayer:
    config = config or {}

    engine_name = config.get(
        "tts_engine",
        "edgetts"
    ).lower()

    if engine_name == "kokoro":
        engine = KokoroTTSEngine(
            voice=config.get("tts_voice", "af_heart"),
            speed=float(config.get("tts_speed", 1.0)),
        )

    elif engine_name == "elevenlabs":
        engine = ElevenLabsTTSEngine(
            api_key=config.get("elevenlabs_api_key", ""),
            voice_id=config.get("tts_voice", "pNInz6obpgDQGcFmaJgB"),
        )

    else:
        # Exact Mark XLVI default voice.
        engine = EdgeTTSEngine(
            voice=config.get("tts_voice", "en-US-GuyNeural")
        )

    return TTSPlayer(engine)


_DEFAULT_CONFIG = {
    "tts_engine": "edgetts",
    "tts_voice": "en-US-GuyNeural",
    "tts_speed": 1.0,
}

_PLAYER: TTSPlayer | None = None
_PLAYER_LOCK = threading.Lock()


def get_voice_player(config: dict | None = None) -> TTSPlayer:
    global _PLAYER

    with _PLAYER_LOCK:
        if _PLAYER is None:
            _PLAYER = create_tts_player(
                config or _DEFAULT_CONFIG
            )

        return _PLAYER


def speak(text: str) -> None:
    """Blocking speak function using the Mark XLVI default voice."""
    get_voice_player().speak(text)


def speak_async(text: str) -> threading.Thread:
    """Non-blocking speak function."""
    thread = threading.Thread(
        target=speak,
        args=(text,),
        daemon=True
    )
    thread.start()

    return thread


def stop_voice() -> None:
    """Stops current voice playback."""
    player = get_voice_player()
    player.stop()


if __name__ == "__main__":
    speak("Voice module is ready. I am using the Mark forty six default voice.")
