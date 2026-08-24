"""Deterministic synthetic WAV bytes. Standard library only. Not a benchmark."""

from __future__ import annotations

import io
import math
import struct
import wave
from enum import Enum

SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2
CHANNELS = 1
DEFAULT_DURATION_MS = 100


class SyntheticKind(str, Enum):
    SILENCE = "silence"
    TONE = "tone"
    NOISE = "noise"
    TRANSCRIPT_TEXT = "transcript-text"


def sample_count(duration_ms: int = DEFAULT_DURATION_MS, sample_rate: int = SAMPLE_RATE) -> int:
    if duration_ms < 1 or duration_ms > 2000:
        raise ValueError("synthetic duration_ms is out of bounds")
    return sample_rate * duration_ms // 1000


def pcm_silence(n_samples: int) -> bytes:
    return b"\x00\x00" * n_samples


def pcm_tone(n_samples: int, *, freq_hz: int = 440, sample_rate: int = SAMPLE_RATE) -> bytes:
    amplitude = 8000
    out = bytearray()
    for index in range(n_samples):
        value = int(amplitude * math.sin(2.0 * math.pi * freq_hz * index / sample_rate))
        out += struct.pack("<h", max(-32767, min(32767, value)))
    return bytes(out)


def pcm_noise(n_samples: int, *, seed: int) -> bytes:
    """Deterministic non-speech waveform. Not a voice clone."""
    state = seed & 0xFFFFFFFF
    out = bytearray()
    for _ in range(n_samples):
        state = (1103515245 * state + 12345) & 0xFFFFFFFF
        value = int(state % 4001) - 2000
        out += struct.pack("<h", value)
    return bytes(out)


def wav_bytes(pcm: bytes, *, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(SAMPLE_WIDTH)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def render_fixture(
    kind: SyntheticKind, *, seed: int = 1, duration_ms: int = DEFAULT_DURATION_MS
) -> bytes:
    n_samples = sample_count(duration_ms)
    if kind is SyntheticKind.SILENCE:
        pcm = pcm_silence(n_samples)
    elif kind is SyntheticKind.TONE:
        pcm = pcm_tone(n_samples, freq_hz=440)
    elif kind is SyntheticKind.NOISE:
        pcm = pcm_noise(n_samples, seed=seed)
    elif kind is SyntheticKind.TRANSCRIPT_TEXT:
        pcm = pcm_silence(n_samples)
    else:
        raise ValueError("unsupported synthetic kind")
    return wav_bytes(pcm)
