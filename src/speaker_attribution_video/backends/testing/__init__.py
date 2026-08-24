"""Test-only deterministic backend doubles.

These modules are testing utilities. They accept synthetic inputs only, perform
no network I/O, load no models, and must not be used as production backends.
"""

from speaker_attribution_video.backends.testing.fakes import (
    FakeAlignmentBackend,
    FakeAttributionModelBackend,
    FakeAudioBackend,
    FakeDiarizationBackend,
    FakeTelemetryBackend,
    FakeTranscriptionBackend,
    FakeVideoEvidenceBackend,
)

__all__ = [
    "FakeAlignmentBackend",
    "FakeAttributionModelBackend",
    "FakeAudioBackend",
    "FakeDiarizationBackend",
    "FakeTelemetryBackend",
    "FakeTranscriptionBackend",
    "FakeVideoEvidenceBackend",
]
