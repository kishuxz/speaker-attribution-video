"""Anti-vacuity: conformance suites must fail known-broken backends with stable findings."""

from __future__ import annotations

import pytest

from speaker_attribution_video.backends.conformance import (
    ConformanceFailure,
    conform_audio,
    conform_diarization,
    conform_transcription,
    conform_video,
)
from speaker_attribution_video.backends.testing.broken import (
    ConstantAudioBackend,
    LeakTranscriptBackend,
    MissingEndpointDiarizationBackend,
    MutatingAudioBackend,
    NamespaceRewritingAudioBackend,
    OverlapClaimDiarizationBackend,
    TimeoutSuccessAudioBackend,
    UnresolvedAsSuccessVideoBackend,
    VariableAudioBackend,
)

pytestmark = pytest.mark.conformance


def _finding(exc: ConformanceFailure) -> str:
    return exc.finding


def test_constant_output_fails_semantic_correspondence() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_audio(ConstantAudioBackend)
    assert _finding(exc.value) == "media_reference"


def test_namespace_rewrite_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_audio(NamespaceRewritingAudioBackend)
    assert _finding(exc.value) == "namespace_job_preservation"


def test_timeout_success_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_audio(TimeoutSuccessAudioBackend)
    assert _finding(exc.value) == "timeout_behavior"


def test_mutation_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_audio(MutatingAudioBackend)
    assert _finding(exc.value) == "no_input_mutation"


def test_variable_output_fails_deterministic_replay() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_audio(VariableAudioBackend)
    assert _finding(exc.value) == "deterministic_replay"


def test_overlap_capability_mismatch_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_diarization(OverlapClaimDiarizationBackend)
    assert _finding(exc.value) == "overlap_claim_mismatch"


def test_missing_edge_endpoint_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_diarization(MissingEndpointDiarizationBackend)
    assert _finding(exc.value) == "referential_integrity"


def test_transcript_leak_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_transcription(LeakTranscriptBackend)
    assert _finding(exc.value) == "sensitive_redaction"


def test_unresolved_as_success_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_video(UnresolvedAsSuccessVideoBackend)
    assert _finding(exc.value) == "unavailable_video"
