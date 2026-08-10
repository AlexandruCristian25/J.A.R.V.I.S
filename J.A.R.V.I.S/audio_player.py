import wave
import numpy as np
import sounddevice as sd
import time

VOICE_FILE = "voice_level.txt"

def play_wav_with_pulse(path):
    wf = wave.open(path, 'rb')

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
        dtype='int16',
        callback=callback
    ):
        sd.sleep(int(wf.getnframes() / samplerate * 1000))

    # reset după terminare
    with open(VOICE_FILE, "w") as f:
        f.write("0.0")
 