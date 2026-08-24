"""Unit tests for T1C/T1D backend contracts and deterministic fakes."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

import pytest

from speaker_attribution_video.backends import (
    AudioBackend,
    BackendError,
    CancellationToken,
    Capability,
    DiarizationBackend,
    FailureReason,
    MediaRef,
    RequestContext,
    ResultState,
    is_successful,
)
from speaker_attribution_video.backends.contracts import (
    BACKEND_INPUT_SCHEMA_VERSION,
    AlignmentRequest,
    AttributionModelRequest,
    AudioRequest,
    DiarizationRequest,
    TelemetryEvent,
    TelemetryRequest,
    TranscriptionRequest,
    VideoEvidenceRequest,
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
from speaker_attribution_video.graph.ids import JobId, NamespaceId, NodeId
from speaker_attribution_video.graph.nodes import AudioArtifact, DiarizationTurn

pytestmark = pytest.mark.unit

HASH = "a" * 64
NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")
MEDIA = MediaRef(
    uri="artifact://synth.example/media/primary",
    content_hash=HASH,
    duration_us=1_000_000,
    display_name="synthetic-audio-01",
)


def _ctx(
    *,
    metadata: Mapping[str, object] | None = None,
    requested_capabilities: frozenset[Capability] = frozenset(),
    timeout_ms: int | None = None,
    input_schema_version: str = BACKEND_INPUT_SCHEMA_VERSION,
) -> RequestContext:
    return RequestContext(
        namespace_id=NS,
        job_id=JOB,
        metadata={"note": "ok"} if metadata is None else metadata,
        requested_capabilities=requested_capabilities,
        timeout_ms=timeout_ms,
        input_schema_version=input_schema_version,
    )


def test_fakes_satisfy_runtime_protocols() -> None:
    assert isinstance(FakeAudioBackend(), AudioBackend)
    assert isinstance(FakeDiarizationBackend(), DiarizationBackend)


def test_audio_fake_preserves_media_and_namespace() -> None:
    backend = FakeAudioBackend()
    result = backend.process(AudioRequest(context=_ctx(), media=MEDIA))
    assert result.state is ResultState.SUCCESS
    assert result.fragment is not None
    node = result.fragment.nodes[0]
    assert node.namespace_id == NS
    assert node.job_id == JOB
    assert isinstance(node.payload, AudioArtifact)
    assert node.payload.uri == MEDIA.uri
    assert node.payload.content_hash == MEDIA.content_hash
    assert node.payload.duration_us == MEDIA.duration_us
    assert backend.invocations[0].redacted_metadata["note"] == "ok"


def test_non_synthetic_uri_is_rejected() -> None:
    backend = FakeAudioBackend()
    bad = MediaRef(uri="file:///tmp/secret.wav", content_hash=HASH, duration_us=10)
    with pytest.raises(BackendError) as exc:
        backend.process(AudioRequest(context=_ctx(), media=bad))
    assert exc.value.reason is FailureReason.INVALID_INPUT
    assert "secret" not in str(exc.value).lower()
    assert "/tmp" not in str(exc.value)


def test_unsupported_capability_is_typed_rejection() -> None:
    backend = FakeAudioBackend()
    ctx = _ctx(requested_capabilities=frozenset({Capability.GPU}))
    with pytest.raises(BackendError) as exc:
        backend.process(AudioRequest(context=ctx, media=MEDIA))
    assert exc.value.reason is FailureReason.UNSUPPORTED_CAPABILITY


def test_speaker_count_hint_rejected_when_unsupported() -> None:
    backend = FakeDiarizationBackend()
    with pytest.raises(BackendError) as exc:
        backend.process(
            DiarizationRequest(context=_ctx(), media=MEDIA, speaker_count_hint=2),
        )
    assert exc.value.reason is FailureReason.UNSUPPORTED_CAPABILITY


def test_diarization_overlap_and_duration_bounds() -> None:
    backend = FakeDiarizationBackend()
    result = backend.process(DiarizationRequest(context=_ctx(), media=MEDIA, allow_overlap=True))
    assert result.state is ResultState.SUCCESS
    assert result.fragment is not None
    turns = [n for n in result.fragment.nodes if isinstance(n.payload, DiarizationTurn)]
    assert len(turns) == 2
    for turn in turns:
        assert turn.payload.span.end_us <= MEDIA.duration_us
        assert turn.payload.span.start_us >= 0
    assert turns[0].payload.span.end_us > turns[1].payload.span.start_us


def test_timeout_and_cancellation_are_not_success() -> None:
    backend = FakeAudioBackend()
    timeout = backend.process(AudioRequest(context=_ctx(timeout_ms=0), media=MEDIA))
    assert timeout.state is ResultState.FAILED_TIMEOUT
    assert not is_successful(timeout.state)
    token = CancellationToken()
    token.cancel()
    cancelled = backend.process(AudioRequest(context=_ctx(), media=MEDIA), cancel=token)
    assert cancelled.state is ResultState.FAILED_CANCELLED
    assert not is_successful(cancelled.state)


def test_injected_failure_and_close() -> None:
    backend = FakeTranscriptionBackend(inject_exception=FailureReason.MISSING_MODEL)
    with pytest.raises(BackendError) as exc:
        backend.process(TranscriptionRequest(context=_ctx(), media=MEDIA))
    assert exc.value.reason is FailureReason.MISSING_MODEL
    assert "transcript" not in str(exc.value).lower()
    backend.close()
    healthy = FakeTranscriptionBackend()
    healthy.close()
    with pytest.raises(BackendError) as exc:
        healthy.process(TranscriptionRequest(context=_ctx(), media=MEDIA))
    assert exc.value.reason is FailureReason.UNAVAILABLE_BACKEND


def test_transcription_does_not_embed_text_in_exceptions_or_logs() -> None:
    metadata = {"transcript": "private-dialogue", "note": "ok"}
    ctx = _ctx(metadata=metadata)
    backend = FakeTranscriptionBackend()
    result = backend.process(TranscriptionRequest(context=ctx, media=MEDIA))
    assert result.state is ResultState.SUCCESS
    assert backend.invocations[0].redacted_metadata["transcript"] == "<redacted>"
    assert "private-dialogue" not in str(backend.invocations[0].redacted_metadata)


def test_alignment_word_timestamps_unsupported() -> None:
    backend = FakeAlignmentBackend()
    with pytest.raises(BackendError) as exc:
        backend.process(
            AlignmentRequest(context=_ctx(), media=MEDIA, want_word_timestamps=True),
        )
    assert exc.value.reason is FailureReason.UNSUPPORTED_CAPABILITY


def test_video_unavailable_is_unresolved_not_success() -> None:
    backend = FakeVideoEvidenceBackend()
    result = backend.process(
        VideoEvidenceRequest(context=_ctx(), media=MEDIA, video_available=False),
    )
    assert result.state is ResultState.UNRESOLVED
    assert not is_successful(result.state)
    assert result.fragment is not None
    assert result.fragment.nodes == ()


def test_attribution_confidence_does_not_admit() -> None:
    backend = FakeAttributionModelBackend()
    subject = NodeId.derive(NS, JOB, "AttributionDecision", {"k": "s"})
    result = backend.process(
        AttributionModelRequest(
            context=_ctx(),
            subject_id=subject,
            candidate_ids=(),
            evidence_ids=(),
            confidence_bp=9900,
        )
    )
    assert result.state is ResultState.UNRESOLVED
    assert not is_successful(result.state)


def test_telemetry_redacts_sensitive_attributes() -> None:
    backend = FakeTelemetryBackend()
    result = backend.process(
        TelemetryRequest(
            context=_ctx(),
            events=(
                TelemetryEvent(
                    span_name="backend.step",
                    attributes={
                        "job_id": JOB.value,
                        "transcript": "nope",
                        "path": "/home/private/file.wav",
                    },
                    reason=FailureReason.TIMEOUT,
                ),
            ),
        )
    )
    assert result.state is ResultState.SUCCESS
    assert result.export is not None
    attrs = result.export.spans[0]["attributes"]
    assert isinstance(attrs, dict)
    assert attrs["transcript"] == "<redacted>"
    assert attrs["path"] == "<redacted>"
    assert attrs["job_id"] == JOB.value


def test_caller_owned_metadata_is_not_mutated() -> None:
    metadata = {"note": "ok", "count": 1}
    original = deepcopy(metadata)
    backend = FakeAudioBackend()
    backend.process(AudioRequest(context=_ctx(metadata=metadata), media=MEDIA))
    assert metadata == original


def test_schema_mismatch_is_typed() -> None:
    backend = FakeAudioBackend()
    with pytest.raises(BackendError) as exc:
        backend.process(AudioRequest(context=_ctx(input_schema_version="nope.v0"), media=MEDIA))
    assert exc.value.reason is FailureReason.SCHEMA_MISMATCH
