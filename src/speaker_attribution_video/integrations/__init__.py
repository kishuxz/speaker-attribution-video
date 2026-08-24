"""Re-export integration protocols."""

from speaker_attribution_video.integrations.protocols import (
    ActiveSpeakerBackend,
    AttributionLanguageModelBackend,
    DiarizationBackend,
    FaceEvidenceBackend,
    TranscriptionBackend,
    VoiceSimilarityBackend,
)

__all__ = [
    "ActiveSpeakerBackend",
    "AttributionLanguageModelBackend",
    "DiarizationBackend",
    "FaceEvidenceBackend",
    "TranscriptionBackend",
    "VoiceSimilarityBackend",
]
