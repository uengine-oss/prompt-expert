"""Microphone capture at the 16 kHz mono float32 that Whisper expects."""

import threading
import time
import wave

import numpy as np

SAMPLE_RATE = 16000


def resample(samples, source_rate, target_rate=SAMPLE_RATE):
    if source_rate == target_rate or len(samples) == 0:
        return samples.astype(np.float32)
    duration = len(samples) / source_rate
    target_len = int(round(duration * target_rate))
    x_old = np.linspace(0.0, duration, num=len(samples), endpoint=False)
    x_new = np.linspace(0.0, duration, num=target_len, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def read_wav(path):
    with wave.open(str(path), "rb") as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("only 16-bit PCM WAV files are supported")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return resample(samples, rate)


class Recorder:
    def __init__(self, device=None, max_seconds=300):
        self.device = device
        self.max_frames = int(max_seconds * SAMPLE_RATE)
        self._stream = None
        self._chunks = []
        self._frames = 0
        self._rate = SAMPLE_RATE
        self._lock = threading.Lock()
        self.level = 0.0  # RMS of the latest block, for the overlay meter

    def _callback(self, data, frames, time_info, status):
        self.level = float(np.sqrt(np.mean(data[:, 0] ** 2)))
        with self._lock:
            if self._frames < self.max_frames * self._rate // SAMPLE_RATE:
                self._chunks.append(data[:, 0].copy())
                self._frames += frames

    def start(self):
        import sounddevice as sd

        with self._lock:
            self._chunks, self._frames = [], 0
        try:
            self._rate = SAMPLE_RATE
            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                          device=self.device, callback=self._callback)
        except sd.PortAudioError:
            # Some drivers refuse 16 kHz; capture natively and resample later.
            info = sd.query_devices(self.device, "input")
            self._rate = int(info["default_samplerate"])
            self._stream = sd.InputStream(samplerate=self._rate, channels=1, dtype="float32",
                                          device=self.device, callback=self._callback)
        self._stream.start()

    def stop(self):
        self.level = 0.0
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        with self._lock:
            chunks, self._chunks = self._chunks, []
        samples = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return resample(samples, self._rate)


class FileRecorder:
    """Stands in for the microphone in tests and demos: each recording is the
    next of these files, cycling."""

    def __init__(self, paths):
        self.clips = [read_wav(path) for path in paths]
        self.next = 0
        self._started = None

    @property
    def level(self):
        # Pretend the clip is being spoken live so the overlay meter moves.
        if self._started is None:
            return 0.0
        clip = self.clips[self.next % len(self.clips)]
        pos = int((time.monotonic() - self._started) * SAMPLE_RATE)
        window = clip[pos:pos + SAMPLE_RATE // 20]
        return float(np.sqrt(np.mean(window ** 2))) if len(window) else 0.0

    def start(self):
        self._started = time.monotonic()

    def stop(self):
        self._started = None
        samples = self.clips[self.next % len(self.clips)]
        self.next += 1
        return samples
