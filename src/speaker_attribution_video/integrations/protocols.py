"""Third-party backend interfaces only.

F0 does not implement or download pyannote, Whisper/WhisperX, ECAPA, Llama,
InsightFace, or LightASD. Apache-2.0 on original source does not apply to them.

InsightFace and LightASD are research-only until independent license review.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DiarizationBackend(Protocol):
    """Future adapter for pyannote-style deterministic diarization."""


@runtime_checkable
class TranscriptionBackend(Protocol):
    """Future adapter for Whisper / WhisperX transcription and alignment."""


@runtime_checkable
class VoiceSimilarityBackend(Protocol):
    """Future adapter for ECAPA-style embeddings."""


@runtime_checkable
class AttributionLanguageModelBackend(Protocol):
    """Future adapter for a bounded Llama-family attribution model."""


@runtime_checkable
class FaceEvidenceBackend(Protocol):
    """InsightFace: research-only / license review required. Not implemented."""


@runtime_checkable
class ActiveSpeakerBackend(Protocol):
    """LightASD: research-only / license review required. Not implemented."""
