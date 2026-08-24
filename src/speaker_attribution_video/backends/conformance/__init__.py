"""Reusable conformance API for future backend implementations."""

from speaker_attribution_video.backends.conformance.findings import ConformanceFailure, check
from speaker_attribution_video.backends.conformance.suites import (
    conform_alignment,
    conform_all_core,
    conform_attribution,
    conform_audio,
    conform_diarization,
    conform_telemetry,
    conform_transcription,
    conform_video,
)

__all__ = [
    "ConformanceFailure",
    "check",
    "conform_alignment",
    "conform_all_core",
    "conform_attribution",
    "conform_audio",
    "conform_diarization",
    "conform_telemetry",
    "conform_transcription",
    "conform_video",
]
