"""Reusable backend conformance suites. Future implementations call these; do not copy tests."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import TypeVar

from speaker_attribution_video.backends.conformance.findings import ConformanceFailure, check
from speaker_attribution_video.backends.conformance.harness import (
    MEDIA,
    NS,
    assert_fragment_integrity,
    assert_not_success,
    context,
    redacted_record,
    spans_within,
)
from speaker_attribution_video.backends.contracts import (
    AlignmentBackend,
    AlignmentRequest,
    AttributionModelBackend,
    AttributionModelRequest,
    AudioBackend,
    AudioRequest,
    CancellationToken,
    DiarizationBackend,
    DiarizationRequest,
    MediaRef,
    TelemetryBackend,
    TelemetryEvent,
    TelemetryRequest,
    TranscriptionBackend,
    TranscriptionRequest,
    VideoEvidenceBackend,
    VideoEvidenceRequest,
)
from speaker_attribution_video.backends.failures import BackendError, FailureReason, ResultState
from speaker_attribution_video.graph.enums import DecisionState
from speaker_attribution_video.graph.ids import JobId, NodeId
from speaker_attribution_video.graph.nodes import (
    AudioArtifact,
    DiarizationTurn,
    TranscriptUtterance,
)

B = TypeVar("B")
Factory = Callable[[], B]


def _common_failure_checks(backend: AudioBackend | DiarizationBackend) -> None:
    identity = backend.identity()
    check("protocol_compliance", bool(identity.name) and bool(identity.version), "identity missing")
    health = backend.health()
    check("protocol_compliance", health.ready and health.live, "backend is not ready")
    caps = backend.capabilities()
    check("capability_honesty", not caps.gpu, "test doubles must not claim GPU")
    backend.close()
    check("cleanup", not backend.health().ready, "close() left the backend ready")


def conform_audio(factory: Factory[AudioBackend]) -> None:
    backend = factory()
    check("protocol_compliance", isinstance(backend, AudioBackend), "not an AudioBackend")
    metadata = {"note": "ok", "transcript": "private-dialogue"}
    original = deepcopy(dict(metadata))
    result = backend.process(AudioRequest(context=context(metadata=metadata), media=MEDIA))
    check(
        "valid_synthetic_input", result.state is ResultState.SUCCESS, "valid synthetic audio failed"
    )
    check("valid_synthetic_input", result.fragment is not None, "missing audio fragment")
    assert result.fragment is not None
    assert_fragment_integrity(result.fragment, namespace=NS, job=context().job_id)
    node = result.fragment.nodes[0]
    check("semantic_correspondence", isinstance(node.payload, AudioArtifact), "audio node missing")
    assert isinstance(node.payload, AudioArtifact)
    check("media_reference", node.payload.uri == MEDIA.uri, "media URI was not preserved")
    check("integer_timeline", node.payload.duration_us == MEDIA.duration_us, "duration changed")
    check("content_hash", node.payload.content_hash == MEDIA.content_hash, "content hash changed")
    check("no_input_mutation", dict(metadata) == original, "caller metadata was mutated")
    record = getattr(backend, "invocations", None)
    if isinstance(record, list) and record:
        redacted_record(record[0].redacted_metadata)
    other = MediaRef(
        uri="artifact://synth.example/media/other",
        content_hash="b" * 64,
        duration_us=2_000_000,
        display_name="synthetic-audio-02",
    )
    second = factory().process(AudioRequest(context=context(), media=other))
    check("semantic_correspondence", second.fragment is not None, "second audio result empty")
    assert second.fragment is not None
    payload = second.fragment.nodes[0].payload
    check(
        "semantic_correspondence",
        isinstance(payload, AudioArtifact) and payload.uri == other.uri,
        "output is not a function of the input",
    )
    try:
        factory().process(
            AudioRequest(
                context=context(),
                media=MediaRef(
                    uri="file:///home/private/file.wav", content_hash="a" * 64, duration_us=1
                ),
            )
        )
        raise ConformanceFailure("invalid_input_rejected", "non-synthetic URI was accepted")
    except BackendError as exc:
        check(
            "invalid_input_rejected",
            exc.reason is FailureReason.INVALID_INPUT,
            "wrong reason for invalid URI",
        )
        check("sensitive_redaction", "/home/private" not in str(exc), "path leaked in exception")
    try:
        factory().process(AudioRequest(context=context(input_schema_version="nope"), media=MEDIA))
        raise ConformanceFailure("schema_version", "unsupported schema was accepted")
    except BackendError as exc:
        check(
            "schema_version",
            exc.reason is FailureReason.SCHEMA_MISMATCH,
            "schema mismatch not typed",
        )
    timeout = factory().process(AudioRequest(context=context(timeout_ms=0), media=MEDIA))
    check(
        "timeout_behavior",
        timeout.state is ResultState.FAILED_TIMEOUT,
        "timeout was not FAILED_TIMEOUT",
    )
    assert_not_success(timeout.state, "timeout_behavior")
    token = CancellationToken()
    token.cancel()
    cancelled = factory().process(AudioRequest(context=context(), media=MEDIA), cancel=token)
    check(
        "cancellation_behavior",
        cancelled.state is ResultState.FAILED_CANCELLED,
        "cancel was not FAILED_CANCELLED",
    )
    replay_backend = factory()
    if replay_backend.capabilities().deterministic_replay:
        replay_a = replay_backend.process(AudioRequest(context=context(), media=MEDIA))
        replay_b = replay_backend.process(AudioRequest(context=context(), media=MEDIA))
        check(
            "deterministic_replay",
            replay_a.fragment == replay_b.fragment,
            "declared deterministic backend returned variable output",
        )
    _common_failure_checks(factory())


def conform_diarization(factory: Factory[DiarizationBackend]) -> None:
    backend = factory()
    check(
        "protocol_compliance", isinstance(backend, DiarizationBackend), "not a DiarizationBackend"
    )
    result = backend.process(DiarizationRequest(context=context(), media=MEDIA, allow_overlap=True))
    check("valid_synthetic_input", result.state is ResultState.SUCCESS, "valid diarization failed")
    assert result.fragment is not None
    assert_fragment_integrity(result.fragment, namespace=NS, job=context().job_id)
    turns = [n for n in result.fragment.nodes if isinstance(n.payload, DiarizationTurn)]
    check("graph_output_validity", len(turns) >= 1, "no diarization turns")
    for turn in turns:
        spans_within(turn, MEDIA.duration_us)
    if backend.capabilities().overlapping_speech:
        check(
            "overlap_claim_mismatch",
            len(turns) >= 2,
            "overlap support claimed but overlapping turns were not produced",
        )
    try:
        factory().process(DiarizationRequest(context=context(), media=MEDIA, speaker_count_hint=3))
        if not factory().capabilities().speaker_count_hints:
            raise ConformanceFailure(
                "capability_honesty",
                "speaker-count hint was accepted without the capability",
            )
    except BackendError as exc:
        check(
            "capability_honesty",
            exc.reason is FailureReason.UNSUPPORTED_CAPABILITY,
            "hint rejection was not typed",
        )
    timeout = factory().process(DiarizationRequest(context=context(timeout_ms=0), media=MEDIA))
    check("timeout_behavior", timeout.state is ResultState.FAILED_TIMEOUT, "timeout not mapped")
    assert_not_success(timeout.state, "timeout_behavior")


def conform_transcription(factory: Factory[TranscriptionBackend]) -> None:
    backend = factory()
    result = backend.process(TranscriptionRequest(context=context(), media=MEDIA))
    check("valid_synthetic_input", result.state is ResultState.SUCCESS, "transcription failed")
    assert result.fragment is not None
    utt_node = next(n for n in result.fragment.nodes if isinstance(n.payload, TranscriptUtterance))
    spans_within(utt_node, MEDIA.duration_us)
    utt_payload = utt_node.payload
    if not isinstance(utt_payload, TranscriptUtterance):
        raise ConformanceFailure("graph_output_validity", "utterance payload mismatch")
    check(
        "sensitive_text", utt_payload.text.embedded is None, "fake transcription embedded raw text"
    )
    try:
        factory().process(
            TranscriptionRequest(
                context=context(metadata={"transcript": "private-dialogue"}),
                media=MediaRef(uri="file:///x", content_hash="a" * 64, duration_us=1),
            )
        )
        raise ConformanceFailure("invalid_input_rejected", "bad URI accepted")
    except BackendError as exc:
        check(
            "sensitive_redaction",
            "private-dialogue" not in str(exc),
            "transcript leaked in exception",
        )
        check(
            "typed_failure_mapping",
            exc.reason is FailureReason.INVALID_INPUT,
            "URI failure not typed",
        )
    except Exception as exc:
        check(
            "sensitive_redaction",
            "private-dialogue" not in str(exc),
            "transcript leaked in exception",
        )
        raise ConformanceFailure("typed_failure_mapping", "failure was not a BackendError") from exc


def conform_alignment(factory: Factory[AlignmentBackend]) -> None:
    backend = factory()
    result = backend.process(AlignmentRequest(context=context(), media=MEDIA))
    check("valid_synthetic_input", result.state is ResultState.SUCCESS, "alignment failed")
    assert result.fragment is not None
    assert_fragment_integrity(result.fragment, namespace=NS, job=context().job_id)
    for node in result.fragment.nodes:
        spans_within(node, MEDIA.duration_us)
    if not backend.capabilities().word_timestamps:
        try:
            factory().process(
                AlignmentRequest(context=context(), media=MEDIA, want_word_timestamps=True)
            )
            raise ConformanceFailure(
                "capability_honesty", "word timestamps accepted without capability"
            )
        except BackendError as exc:
            check(
                "capability_honesty",
                exc.reason is FailureReason.UNSUPPORTED_CAPABILITY,
                "word-timestamp rejection not typed",
            )


def conform_video(factory: Factory[VideoEvidenceBackend]) -> None:
    backend = factory()
    missing = backend.process(
        VideoEvidenceRequest(context=context(), media=MEDIA, video_available=False)
    )
    check(
        "unavailable_video",
        missing.state is ResultState.UNRESOLVED,
        "unavailable video was not unresolved",
    )
    assert_not_success(missing.state, "unavailable_video")
    check(
        "manufactured_identity",
        missing.fragment is not None and missing.fragment.nodes == (),
        "unavailable video fabricated identity nodes",
    )


def conform_attribution(factory: Factory[AttributionModelBackend]) -> None:
    backend = factory()
    subject = NodeId.derive(NS, JobId.derive(NS, "job01"), "AttributionDecision", {"k": "subject"})
    result = backend.process(
        AttributionModelRequest(
            context=context(),
            subject_id=subject,
            candidate_ids=(),
            evidence_ids=(),
            confidence_bp=9900,
        )
    )
    check(
        "unsupported_attribution",
        result.state is ResultState.UNRESOLVED,
        "empty evidence was not unresolved",
    )
    assert_not_success(result.state, "unsupported_attribution")
    assert result.fragment is not None
    decision = result.fragment.nodes[0].payload
    check(
        "confidence_not_admission",
        getattr(decision, "state", None) is DecisionState.UNRESOLVED,
        "confidence admitted attribution",
    )
    check(
        "confidence_not_admission",
        getattr(decision, "selected_candidate_id", "x") is None,
        "selected a candidate without evidence",
    )


def conform_telemetry(factory: Factory[TelemetryBackend]) -> None:
    backend = factory()
    result = backend.process(
        TelemetryRequest(
            context=context(),
            events=(
                TelemetryEvent(
                    span_name="backend.step",
                    attributes={
                        "job_id": context().job_id.value,
                        "transcript": "private-dialogue",
                        "path": "/home/private/file.wav",
                    },
                    reason=FailureReason.TIMEOUT,
                ),
            ),
        )
    )
    check("valid_synthetic_input", result.state is ResultState.SUCCESS, "telemetry export failed")
    assert result.export is not None
    blob = str(result.export)
    check("sensitive_redaction", "private-dialogue" not in blob, "transcript in telemetry")
    check("sensitive_redaction", "/home/private" not in blob, "path in telemetry")
    check("safe_ids", context().job_id.value in blob, "job id missing from telemetry")
    check(
        "typed_failure_mapping",
        result.export.spans[0].get("reason") == FailureReason.TIMEOUT.value,
        "reason code missing from span",
    )


def conform_all_core() -> None:
    """Placeholder imported by tests; individual suites are the API."""
    return None
