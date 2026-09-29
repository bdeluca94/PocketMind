"""
Voice input: transcribes short WAV recordings from the browser using
faster-whisper (runs on CPU, small model). The model downloads itself
once via Hugging Face Hub on first use, then works offline.
"""

import io
import sys
import threading
import wave
from pathlib import Path

import numpy as np

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

WHISPER_CACHE = ROOT / "whisper_models"

_model = None
_model_lock = threading.Lock()


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel
            WHISPER_CACHE.mkdir(parents=True, exist_ok=True)
            _model = WhisperModel(
                "base",
                device="cpu",
                compute_type="int8",
                download_root=str(WHISPER_CACHE),
            )
        return _model


def transcribe_wav_bytes(wav_bytes: bytes) -> str:
    """Takes WAV bytes (any sample rate/channel count) and returns the
    transcribed text. Resamples to the 16kHz mono float32 that
    faster-whisper expects, regardless of what the client actually sent —
    don't rely on the frontend having gotten the encoding exactly right."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        framerate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if sample_width == 2:
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sample_width == 1:
        audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).mean(axis=1)

    target_rate = 16000
    if framerate != target_rate and len(audio) > 0:
        ratio = framerate / target_rate
        out_len = max(int(len(audio) / ratio), 1)
        idx = (np.arange(out_len) * ratio).astype(np.int64)
        idx = np.clip(idx, 0, len(audio) - 1)
        audio = audio[idx]

    model = get_model()
    segments, _ = model.transcribe(audio, language=None, vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments)
    return text.strip()
