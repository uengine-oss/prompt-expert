"""Local speech-to-text with faster-whisper (CTranslate2)."""

import ctypes
import logging
import sys
import threading

import numpy as np

from .audio import SAMPLE_RATE

log = logging.getLogger(__name__)

# Whisper tends to "hear" these subtitles-credits phrases in silence.
HALLUCINATIONS = {
    "시청해 주셔서 감사합니다.", "시청해주셔서 감사합니다.", "구독과 좋아요 부탁드립니다.",
    "mbc 뉴스 이덕영입니다.", "thanks for watching!",
}


def cuda_usable():
    """An NVIDIA GPU alone is not enough: CTranslate2 also needs the CUDA 12
    cuBLAS DLL, which we do not ship. Without it inference would fail."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() == 0:
            return False
        if sys.platform == "win32":
            ctypes.WinDLL("cublas64_12.dll")
        return True
    except Exception:
        return False


def pick_device(device, compute_type):
    if device == "auto":
        device = "cuda" if cuda_usable() else "cpu"
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


class Transcriber:
    def __init__(self, model="large-v3-turbo", device="auto", compute_type="auto",
                 language="auto", initial_prompt="", beam_size=1, cpu_model="small"):
        self.device, self.compute_type = pick_device(device, compute_type)
        # The old default takes tens of seconds per short utterance on CPU.
        # Keep explicit CPU/model choices, but make automatic selection usable
        # on Windows PCs without CUDA (including existing default configs).
        self.model_name = (cpu_model if device == "auto" and self.device == "cpu"
                           and model == "large-v3-turbo" and cpu_model else model)
        self.language = None if language in (None, "", "auto") else language
        self.initial_prompt = initial_prompt or None
        self.beam_size = beam_size
        self.model = None
        self._lock = threading.Lock()  # the startup loader and a first dictation may race

    def load(self):
        with self._lock:
            if self.model is None:
                self._load()

    def _load(self):
        try:
            from faster_whisper import WhisperModel
        except OSError as error:  # ctranslate2.dll needs msvcp140.dll
            raise RuntimeError(
                "Microsoft Visual C++ 재배포 패키지(x64)가 필요합니다: "
                "https://aka.ms/vs/17/release/vc_redist.x64.exe") from error

        log.info("loading model %s on %s (%s)", self.model_name, self.device, self.compute_type)
        self.model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        log.info("model ready")

    def transcribe(self, samples):
        if len(samples) < SAMPLE_RATE * 0.3 or float(np.sqrt(np.mean(samples ** 2))) < 0.002:
            log.info("skipping: too short or silent")
            return ""
        self.load()
        try:
            text, info = self._run(samples)
        except RuntimeError:
            if self.device != "cuda":
                raise
            log.exception("GPU transcription failed; falling back to CPU")
            with self._lock:
                self.device, self.compute_type, self.model = "cpu", "int8", None
            self.load()
            text, info = self._run(samples)
        log.info("detected language %s (p=%.2f)", info.language, info.language_probability)
        if text.lower() in HALLUCINATIONS:
            log.info("dropping likely hallucination: %r", text)
            return ""
        return text

    def _run(self, samples):
        segments, info = self.model.transcribe(
            samples,
            language=self.language,
            beam_size=self.beam_size,
            initial_prompt=self.initial_prompt,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        # segments is lazy: the actual decoding (and any GPU error) happens here
        return " ".join(segment.text.strip() for segment in segments).strip(), info
