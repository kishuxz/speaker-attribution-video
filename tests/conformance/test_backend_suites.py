"""Conformance suites against deterministic fakes (not empty placeholders)."""

from __future__ import annotations

import pytest

from speaker_attribution_video.backends.conformance import (
    conform_alignment,
    conform_attribution,
    conform_audio,
    conform_diarization,
    conform_telemetry,
    conform_transcription,
    conform_video,
)
from speaker_attribution_video.backends.testing import (
    FakeAlignmentBackend,
    FakeAttributionModelBackend,
    FakeAudioBackend,
    FakeDiarizationBackend,
    FakeTelemetryBackend,
    FakeTranscriptionBackend,
    FakeVideoEvidenceBackend,
)

pytestmark = pytest.mark.conformance


def test_fake_audio_conformance() -> None:
    conform_audio(FakeAudioBackend)


def test_fake_diarization_conformance() -> None:
    conform_diarization(FakeDiarizationBackend)


def test_fake_transcription_conformance() -> None:
    conform_transcription(FakeTranscriptionBackend)


def test_fake_alignment_conformance() -> None:
    conform_alignment(FakeAlignmentBackend)


def test_fake_video_conformance() -> None:
    conform_video(FakeVideoEvidenceBackend)


def test_fake_attribution_conformance() -> None:
    conform_attribution(FakeAttributionModelBackend)


def test_fake_telemetry_conformance() -> None:
    conform_telemetry(FakeTelemetryBackend)
