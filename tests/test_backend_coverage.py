"""Additional unit tests for backend contract branches that G1 tests do not hit."""

from __future__ import annotations

import runpy
import sys

import pytest

from speaker_attribution_video.backends.capabilities import (
    Capabilities,
    Capability,
    require_capabilities,
)
from speaker_attribution_video.backends.conformance import conform_all_core
from speaker_attribution_video.backends.contracts import (
    AlignmentRequest,
    AttributionModelRequest,
    AudioRequest,
    BackendIdentity,
    BackendResult,
    CancellationToken,
    GraphFragment,
    TelemetryEvent,
    TelemetryRequest,
    TranscriptionRequest,
    VideoEvidenceRequest,
    fingerprint_config,
)
from speaker_attribution_video.backends.failures import BackendError, FailureReason, ResultState
from speaker_attribution_video.backends.testing import (
    FakeAlignmentBackend,
    FakeAttributionModelBackend,
    FakeAudioBackend,
    FakeTelemetryBackend,
    FakeTranscriptionBackend,
    FakeVideoEvidenceBackend,
)
from speaker_attribution_video.graph.ids import JobId, NamespaceId, NodeId
from test_backend_contracts import MEDIA, _ctx

pytestmark = pytest.mark.unit


def test_capabilities_offered_and_gpu_rejection() -> None:
    caps = Capabilities(gpu=True, offline=True)
    assert Capability.GPU in caps.offered()
    with pytest.raises(BackendError) as exc:
        require_capabilities(Capabilities(), (Capability.GPU,))
    assert exc.value.reason is FailureReason.UNSUPPORTED_CAPABILITY


def test_backend_result_success_invariants() -> None:
    identity = BackendIdentity(
        name="x",
        version="0",
        configuration_fingerprint=fingerprint_config({"n": "x"}),
        deterministic=True,
        input_schema_version="t1.backend.input.v1",
        output_schema_version="t1.backend.output.v1",
        supports_timeout=True,
        supports_cancellation=True,
    )
    with pytest.raises(ValueError):
        BackendResult(
            state=ResultState.SUCCESS,
            identity=identity,
            output_schema_version="t1.backend.output.v1",
            fragment=GraphFragment(nodes=(), edges=()),
            failure_reason=FailureReason.TIMEOUT,
        )
    with pytest.raises(ValueError):
        BackendResult(
            state=ResultState.SUCCESS,
            identity=identity,
            output_schema_version="t1.backend.output.v1",
            fragment=None,
        )


def test_failure_details_redact_paths_and_blocked_keys() -> None:
    err = BackendError(
        FailureReason.INVALID_INPUT,
        "bad",
        details={
            "transcript": "private-dialogue",
            "note": "/home/private/file.wav",
            "ok": "artifact://synth.example/x",
        },
    )
    assert "private-dialogue" not in str(err.details)
    assert err.details["ok"] == "artifact://synth.example/x"
    assert err.details["transcript"] == "<redacted>"
    assert err.details["note"] == "<redacted>"


def test_fake_injected_state_and_closed_backend() -> None:
    closed = FakeAudioBackend()
    closed.close()
    with pytest.raises(BackendError) as exc:
        closed.process(AudioRequest(context=_ctx(), media=MEDIA))
    assert exc.value.reason is FailureReason.UNAVAILABLE_BACKEND
    injected = FakeAudioBackend(inject_state=ResultState.FAILED_RESOURCE_LIMIT)
    result = injected.process(AudioRequest(context=_ctx(), media=MEDIA))
    assert result.state is ResultState.FAILED_RESOURCE_LIMIT
    typed = FakeAudioBackend(inject_exception=FailureReason.MISSING_MODEL)
    with pytest.raises(BackendError) as missing:
        typed.process(AudioRequest(context=_ctx(), media=MEDIA))
    assert missing.value.reason is FailureReason.MISSING_MODEL


def test_fake_timeout_paths_on_remaining_backends() -> None:
    token = CancellationToken()
    token.cancel()
    timeout_ctx = _ctx(timeout_ms=0)
    assert (
        FakeTranscriptionBackend()
        .process(TranscriptionRequest(context=timeout_ctx, media=MEDIA))
        .state
        is ResultState.FAILED_TIMEOUT
    )
    assert (
        FakeAlignmentBackend().process(AlignmentRequest(context=timeout_ctx, media=MEDIA)).state
        is ResultState.FAILED_TIMEOUT
    )
    assert (
        FakeVideoEvidenceBackend()
        .process(VideoEvidenceRequest(context=timeout_ctx, media=MEDIA))
        .state
        is ResultState.FAILED_TIMEOUT
    )
    assert (
        FakeAttributionModelBackend()
        .process(
            AttributionModelRequest(
                context=timeout_ctx,
                subject_id=NodeId.derive(
                    NamespaceId.from_slug("synth.example"),
                    JobId.derive(NamespaceId.from_slug("synth.example"), "job01"),
                    "AttributionDecision",
                    {"k": "s"},
                ),
            )
        )
        .state
        is ResultState.FAILED_TIMEOUT
    )
    assert (
        FakeTelemetryBackend()
        .process(
            TelemetryRequest(
                context=timeout_ctx, events=(TelemetryEvent(span_name="x", attributes={}),)
            )
        )
        .state
        is ResultState.FAILED_TIMEOUT
    )
    assert (
        FakeTranscriptionBackend()
        .process(TranscriptionRequest(context=_ctx(), media=MEDIA), cancel=token)
        .state
        is ResultState.FAILED_CANCELLED
    )
    video = FakeVideoEvidenceBackend().process(
        VideoEvidenceRequest(
            context=_ctx(),
            media=MEDIA,
            video_available=True,
            segment_ids=(
                NodeId.derive(
                    NamespaceId.from_slug("synth.example"),
                    JobId.derive(NamespaceId.from_slug("synth.example"), "job01"),
                    "AudioSegment",
                    {"k": "s"},
                ),
            ),
            candidate_ids=(
                NodeId.derive(
                    NamespaceId.from_slug("synth.example"),
                    JobId.derive(NamespaceId.from_slug("synth.example"), "job01"),
                    "CandidateIdentity",
                    {"k": "c"},
                ),
            ),
        )
    )
    assert video.state is ResultState.SUCCESS
    unresolved = FakeVideoEvidenceBackend().process(
        VideoEvidenceRequest(context=_ctx(), media=MEDIA, video_available=True)
    )
    assert unresolved.state is ResultState.UNRESOLVED


def test_module_entrypoint_and_conform_placeholder() -> None:
    conform_all_core()
    argv = sys.argv
    sys.argv = ["speaker-attribution-video", "--version"]
    try:
        with pytest.raises(SystemExit) as exc:
            runpy.run_module("speaker_attribution_video", run_name="__main__")
        assert exc.value.code == 0
    finally:
        sys.argv = argv
