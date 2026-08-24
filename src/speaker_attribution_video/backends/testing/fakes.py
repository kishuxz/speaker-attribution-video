"""Deterministic fake backends. Synthetic fixtures only; no models or network."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from speaker_attribution_video.backends.capabilities import (
    Capabilities,
    Capability,
    require_capabilities,
)
from speaker_attribution_video.backends.contracts import (
    BACKEND_OUTPUT_SCHEMA_VERSION,
    AlignmentRequest,
    AttributionModelRequest,
    AudioRequest,
    BackendIdentity,
    BackendResult,
    CancellationToken,
    DiarizationRequest,
    GraphFragment,
    HealthResult,
    InvocationRecord,
    MediaRef,
    TelemetryExport,
    TelemetryRequest,
    TelemetryResult,
    TranscriptionRequest,
    VideoEvidenceRequest,
    fingerprint_config,
    require_input_schema,
    require_synthetic_uri,
)
from speaker_attribution_video.backends.failures import BackendError, FailureReason, ResultState
from speaker_attribution_video.graph.edges import EdgeType, GraphEdge, make_edge
from speaker_attribution_video.graph.enums import (
    DecisionState,
    EvidenceSummary,
    ProducerKind,
    ReasonCode,
    Sensitivity,
    TextMode,
)
from speaker_attribution_video.graph.ids import MediaId
from speaker_attribution_video.graph.nodes import (
    AttributionDecision,
    AudioArtifact,
    DiarizationTurn,
    SpeakerCluster,
    TranscriptToken,
    TranscriptUtterance,
    VisualEvidence,
    make_node,
)
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.text import SensitiveText
from speaker_attribution_video.graph.time import TimeSpan

FIXED = datetime(2026, 8, 24, 19, 0, 0, tzinfo=UTC)
FAKE_VERSION = "0.1.0"


def _redacted_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    blocked = {
        "transcript",
        "text",
        "embedded",
        "tokens",
        "audio_bytes",
        "video_bytes",
        "path",
        "filepath",
    }
    return {
        key: "<redacted>" if key.lower() in blocked else value for key, value in metadata.items()
    }


def _snapshot(metadata: Mapping[str, object]) -> dict[str, object]:
    return dict(metadata)


@dataclass
class _FakeBase:
    name: str
    extra_config: Mapping[str, object] = field(default_factory=dict)
    offered: Capabilities = field(default_factory=Capabilities)
    inject_exception: FailureReason | None = None
    inject_state: ResultState | None = None
    closed: bool = False
    invocations: list[InvocationRecord] = field(default_factory=list)

    def identity(self) -> BackendIdentity:
        return BackendIdentity(
            name=self.name,
            version=FAKE_VERSION,
            configuration_fingerprint=fingerprint_config(
                {"name": self.name, **dict(self.extra_config)}
            ),
            deterministic=self.offered.deterministic_replay,
            input_schema_version="t1.backend.input.v1",
            output_schema_version=BACKEND_OUTPUT_SCHEMA_VERSION,
            supports_timeout=True,
            supports_cancellation=True,
        )

    def capabilities(self) -> Capabilities:
        return self.offered

    def health(self) -> HealthResult:
        if self.closed:
            return HealthResult(ready=False, live=False, reason=FailureReason.UNAVAILABLE_BACKEND)
        return HealthResult(ready=True, live=True)

    def close(self) -> None:
        self.closed = True

    def _preflight(
        self,
        *,
        request_kind: str,
        context_schema: str,
        requested: frozenset[Capability],
        metadata: Mapping[str, object],
        media: MediaRef | None,
        timeout_ms: int | None,
        cancel: CancellationToken | None,
        namespace: str,
        job: str,
    ) -> ResultState | None:
        if self.closed:
            raise BackendError(FailureReason.UNAVAILABLE_BACKEND, "backend is closed")
        require_input_schema(context_schema)
        require_capabilities(self.offered, requested)
        if media is not None:
            require_synthetic_uri(media.uri)
        copied = _snapshot(metadata)
        if copied != dict(metadata):
            raise BackendError(FailureReason.INVALID_INPUT, "metadata snapshot failed")
        record = InvocationRecord(
            backend_id=self.identity().backend_id,
            backend_version=FAKE_VERSION,
            configuration_fingerprint=self.identity().configuration_fingerprint,
            namespace_id=namespace,
            job_id=job,
            request_kind=request_kind,
            redacted_metadata=_redacted_metadata(metadata),
        )
        self.invocations.append(record)
        if self.inject_exception is not None:
            raise BackendError(self.inject_exception, "injected typed failure")
        if cancel is not None and cancel.is_cancelled():
            return ResultState.FAILED_CANCELLED
        if timeout_ms is not None and timeout_ms <= 0:
            return ResultState.FAILED_TIMEOUT
        if self.inject_state is not None:
            return self.inject_state
        return None

    def _finish(
        self,
        state: ResultState,
        fragment: GraphFragment | None,
        reason: FailureReason | None = None,
        message: str | None = None,
    ) -> BackendResult:
        if self.invocations:
            last = self.invocations[-1]
            self.invocations[-1] = InvocationRecord(
                backend_id=last.backend_id,
                backend_version=last.backend_version,
                configuration_fingerprint=last.configuration_fingerprint,
                namespace_id=last.namespace_id,
                job_id=last.job_id,
                request_kind=last.request_kind,
                redacted_metadata=last.redacted_metadata,
                result_state=state,
                failure_reason=reason,
            )
        if state is ResultState.SUCCESS:
            return BackendResult(
                state=state,
                identity=self.identity(),
                output_schema_version=BACKEND_OUTPUT_SCHEMA_VERSION,
                fragment=fragment,
            )
        return BackendResult(
            state=state,
            identity=self.identity(),
            output_schema_version=BACKEND_OUTPUT_SCHEMA_VERSION,
            fragment=fragment,
            failure_reason=reason,
            message=message,
        )

    def _producer(self) -> Producer:
        return Producer(ProducerKind.TEST, self.name.replace("-", "."))


class FakeAudioBackend(_FakeBase):
    def __init__(self, **kwargs: Any) -> None:
        offered = kwargs.pop(
            "offered", Capabilities(offline=True, deterministic_replay=True, batch=True)
        )
        super().__init__(name="fake-audio", offered=offered, **kwargs)

    def process(
        self, request: AudioRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        early = self._preflight(
            request_kind="audio",
            context_schema=request.context.input_schema_version,
            requested=request.context.requested_capabilities,
            metadata=request.context.metadata,
            media=request.media,
            timeout_ms=request.context.timeout_ms,
            cancel=cancel,
            namespace=request.context.namespace_id.value,
            job=request.context.job_id.value,
        )
        if isinstance(early, ResultState):
            reason = {
                ResultState.FAILED_TIMEOUT: FailureReason.TIMEOUT,
                ResultState.FAILED_CANCELLED: FailureReason.CANCELLATION,
                ResultState.FAILED_RESOURCE_LIMIT: FailureReason.RESOURCE_LIMIT,
            }.get(early)
            return self._finish(early, None, reason)
        ns = request.context.namespace_id
        job = request.context.job_id
        media_id = MediaId.derive(ns, job, request.media.content_hash, request.media.uri)
        node = make_node(
            namespace=ns,
            job=job,
            payload=AudioArtifact(
                content_hash=request.media.content_hash,
                uri=request.media.uri,
                display_name=request.media.display_name,
                duration_us=request.media.duration_us,
                mime_type="audio/wav",
                parent_media_id=media_id,
            ),
            producer=self._producer(),
            created_at=FIXED,
            identity_parts={
                "content_hash": request.media.content_hash,
                "uri": request.media.uri,
                "job": job.value,
            },
        )
        return self._finish(ResultState.SUCCESS, GraphFragment(nodes=(node,), edges=()))


class FakeDiarizationBackend(_FakeBase):
    def __init__(self, **kwargs: Any) -> None:
        offered = kwargs.pop(
            "offered",
            Capabilities(
                offline=True,
                deterministic_replay=True,
                overlapping_speech=True,
                confidence=True,
            ),
        )
        super().__init__(name="fake-diarization", offered=offered, **kwargs)

    def process(
        self, request: DiarizationRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        if request.speaker_count_hint is not None:
            require_capabilities(self.offered, (Capability.SPEAKER_COUNT_HINTS,))
        early = self._preflight(
            request_kind="diarization",
            context_schema=request.context.input_schema_version,
            requested=request.context.requested_capabilities,
            metadata=request.context.metadata,
            media=request.media,
            timeout_ms=request.context.timeout_ms,
            cancel=cancel,
            namespace=request.context.namespace_id.value,
            job=request.context.job_id.value,
        )
        if isinstance(early, ResultState):
            reason = {
                ResultState.FAILED_TIMEOUT: FailureReason.TIMEOUT,
                ResultState.FAILED_CANCELLED: FailureReason.CANCELLATION,
            }.get(early)
            return self._finish(early, None, reason)
        ns = request.context.namespace_id
        job = request.context.job_id
        duration = request.media.duration_us
        cluster = make_node(
            namespace=ns,
            job=job,
            payload=SpeakerCluster(cluster_key="speaker_00", display_label="speaker_00"),
            producer=self._producer(),
            created_at=FIXED,
            identity_parts={"cluster": "speaker_00", "job": job.value},
        )
        first_end = max(1, duration // 2)
        turns = [
            make_node(
                namespace=ns,
                job=job,
                payload=DiarizationTurn(
                    span=TimeSpan(0, first_end),
                    cluster_key="speaker_00",
                    confidence_bp=9000 if self.offered.confidence else None,
                ),
                producer=self._producer(),
                created_at=FIXED,
                identity_parts={"turn": "0", "job": job.value},
            )
        ]
        if request.allow_overlap:
            overlap_start = max(0, first_end - max(1, duration // 10))
            turns.append(
                make_node(
                    namespace=ns,
                    job=job,
                    payload=DiarizationTurn(
                        span=TimeSpan(overlap_start, duration),
                        cluster_key="speaker_00",
                        confidence_bp=8000 if self.offered.confidence else None,
                    ),
                    producer=self._producer(),
                    created_at=FIXED,
                    identity_parts={"turn": "1", "job": job.value},
                )
            )
        edges: list[GraphEdge] = []
        audio_stub = make_node(
            namespace=ns,
            job=job,
            payload=AudioArtifact(
                content_hash=request.media.content_hash,
                uri=request.media.uri,
                display_name=request.media.display_name,
                duration_us=duration,
            ),
            producer=self._producer(),
            created_at=FIXED,
            identity_parts={
                "content_hash": request.media.content_hash,
                "uri": request.media.uri,
                "job": job.value,
            },
        )
        for turn in turns:
            edges.append(
                make_edge(
                    edge_type=EdgeType.DIARIZED_AS,
                    source=turn,
                    target=audio_stub,
                    producer=self._producer(),
                    created_at=FIXED,
                )
            )
            edges.append(
                make_edge(
                    edge_type=EdgeType.ASSIGNED_TO,
                    source=turn,
                    target=cluster,
                    producer=self._producer(),
                    created_at=FIXED,
                )
            )
        nodes = (audio_stub, cluster, *turns)
        return self._finish(ResultState.SUCCESS, GraphFragment(nodes=nodes, edges=tuple(edges)))


class FakeTranscriptionBackend(_FakeBase):
    def __init__(self, **kwargs: Any) -> None:
        offered = kwargs.pop(
            "offered",
            Capabilities(offline=True, deterministic_replay=True, confidence=True),
        )
        super().__init__(name="fake-transcription", offered=offered, **kwargs)

    def process(
        self, request: TranscriptionRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        early = self._preflight(
            request_kind="transcription",
            context_schema=request.context.input_schema_version,
            requested=request.context.requested_capabilities,
            metadata=request.context.metadata,
            media=request.media,
            timeout_ms=request.context.timeout_ms,
            cancel=cancel,
            namespace=request.context.namespace_id.value,
            job=request.context.job_id.value,
        )
        if isinstance(early, ResultState):
            reason = {
                ResultState.FAILED_TIMEOUT: FailureReason.TIMEOUT,
                ResultState.FAILED_CANCELLED: FailureReason.CANCELLATION,
            }.get(early)
            return self._finish(early, None, reason)
        ns = request.context.namespace_id
        job = request.context.job_id
        utterance = make_node(
            namespace=ns,
            job=job,
            payload=TranscriptUtterance(
                span=TimeSpan(0, request.media.duration_us),
                text=SensitiveText(
                    mode=TextMode.REDACTED,
                    sensitivity=Sensitivity.SENSITIVE,
                    redacted="[redacted]",
                    sha256="b" * 64,
                ),
                language_tag=request.language_tag,
                confidence_bp=5000 if self.offered.confidence else None,
            ),
            producer=self._producer(),
            created_at=FIXED,
            identity_parts={"utt": "0", "job": job.value},
            sensitivity=Sensitivity.SENSITIVE,
        )
        return self._finish(ResultState.SUCCESS, GraphFragment(nodes=(utterance,), edges=()))


class FakeAlignmentBackend(_FakeBase):
    def __init__(self, **kwargs: Any) -> None:
        offered = kwargs.pop(
            "offered",
            Capabilities(offline=True, deterministic_replay=True),
        )
        super().__init__(name="fake-alignment", offered=offered, **kwargs)

    def process(
        self, request: AlignmentRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        if request.want_word_timestamps:
            require_capabilities(self.offered, (Capability.WORD_TIMESTAMPS,))
        early = self._preflight(
            request_kind="alignment",
            context_schema=request.context.input_schema_version,
            requested=request.context.requested_capabilities,
            metadata=request.context.metadata,
            media=request.media,
            timeout_ms=request.context.timeout_ms,
            cancel=cancel,
            namespace=request.context.namespace_id.value,
            job=request.context.job_id.value,
        )
        if isinstance(early, ResultState):
            reason = {
                ResultState.FAILED_TIMEOUT: FailureReason.TIMEOUT,
                ResultState.FAILED_CANCELLED: FailureReason.CANCELLATION,
            }.get(early)
            return self._finish(early, None, reason)
        ns = request.context.namespace_id
        job = request.context.job_id
        utterance = make_node(
            namespace=ns,
            job=job,
            payload=TranscriptUtterance(
                span=TimeSpan(0, request.media.duration_us),
                text=SensitiveText(
                    mode=TextMode.HASH,
                    sensitivity=Sensitivity.SENSITIVE,
                    sha256="c" * 64,
                ),
            ),
            producer=self._producer(),
            created_at=FIXED,
            identity_parts={"utt": "align", "job": job.value},
            sensitivity=Sensitivity.SENSITIVE,
        )
        token = make_node(
            namespace=ns,
            job=job,
            payload=TranscriptToken(
                utterance_id=utterance.id,
                span=TimeSpan(0, min(1, request.media.duration_us)),
                text=SensitiveText(
                    mode=TextMode.HASH,
                    sensitivity=Sensitivity.SENSITIVE,
                    sha256="d" * 64,
                ),
            ),
            producer=self._producer(),
            created_at=FIXED,
            identity_parts={"tok": "0", "job": job.value},
            sensitivity=Sensitivity.SENSITIVE,
        )
        edge = make_edge(
            edge_type=EdgeType.ALIGNED_TO,
            source=token,
            target=utterance,
            producer=self._producer(),
            created_at=FIXED,
        )
        return self._finish(
            ResultState.SUCCESS, GraphFragment(nodes=(utterance, token), edges=(edge,))
        )


class FakeVideoEvidenceBackend(_FakeBase):
    def __init__(self, **kwargs: Any) -> None:
        offered = kwargs.pop(
            "offered",
            Capabilities(
                offline=True,
                deterministic_replay=True,
                video_evidence=True,
            ),
        )
        super().__init__(name="fake-video-evidence", offered=offered, **kwargs)

    def process(
        self, request: VideoEvidenceRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        early = self._preflight(
            request_kind="video_evidence",
            context_schema=request.context.input_schema_version,
            requested=request.context.requested_capabilities,
            metadata=request.context.metadata,
            media=request.media,
            timeout_ms=request.context.timeout_ms,
            cancel=cancel,
            namespace=request.context.namespace_id.value,
            job=request.context.job_id.value,
        )
        if isinstance(early, ResultState):
            reason = {
                ResultState.FAILED_TIMEOUT: FailureReason.TIMEOUT,
                ResultState.FAILED_CANCELLED: FailureReason.CANCELLATION,
            }.get(early)
            return self._finish(early, None, reason)
        if not request.video_available:
            return self._finish(
                ResultState.UNRESOLVED,
                GraphFragment(nodes=(), edges=()),
                FailureReason.EXTERNAL_DEPENDENCY_FAILURE,
                "video is unavailable",
            )
        if not request.candidate_ids or not request.segment_ids:
            return self._finish(
                ResultState.UNRESOLVED,
                GraphFragment(nodes=(), edges=()),
                message="video evidence requires existing segments and candidates",
            )
        ns = request.context.namespace_id
        job = request.context.job_id
        evidence = make_node(
            namespace=ns,
            job=job,
            payload=VisualEvidence(summary=EvidenceSummary.OTHER),
            producer=self._producer(),
            created_at=FIXED,
            identity_parts={"visual": "0", "job": job.value},
        )
        return self._finish(ResultState.SUCCESS, GraphFragment(nodes=(evidence,), edges=()))


class FakeAttributionModelBackend(_FakeBase):
    def __init__(self, **kwargs: Any) -> None:
        offered = kwargs.pop(
            "offered",
            Capabilities(offline=True, deterministic_replay=True, confidence=True),
        )
        super().__init__(name="fake-attribution-model", offered=offered, **kwargs)

    def process(
        self, request: AttributionModelRequest, *, cancel: CancellationToken | None = None
    ) -> BackendResult:
        early = self._preflight(
            request_kind="attribution_model",
            context_schema=request.context.input_schema_version,
            requested=request.context.requested_capabilities,
            metadata=request.context.metadata,
            media=None,
            timeout_ms=request.context.timeout_ms,
            cancel=cancel,
            namespace=request.context.namespace_id.value,
            job=request.context.job_id.value,
        )
        if isinstance(early, ResultState):
            reason = {
                ResultState.FAILED_TIMEOUT: FailureReason.TIMEOUT,
                ResultState.FAILED_CANCELLED: FailureReason.CANCELLATION,
            }.get(early)
            return self._finish(early, None, reason)
        ns = request.context.namespace_id
        job = request.context.job_id
        payload = AttributionDecision(
            state=DecisionState.UNRESOLVED,
            subject_id=request.subject_id,
            reason_code=ReasonCode.INSUFFICIENT_EVIDENCE,
            selected_candidate_id=None,
            confidence_bp=request.confidence_bp if self.offered.confidence else None,
        )
        decision = make_node(
            namespace=ns,
            job=job,
            payload=payload,
            producer=self._producer(),
            created_at=FIXED,
            identity_parts={"subject": request.subject_id.value, "job": job.value},
        )
        return self._finish(
            ResultState.UNRESOLVED,
            GraphFragment(nodes=(decision,), edges=()),
            message="fake attribution remains unresolved without a real model",
        )


class FakeTelemetryBackend(_FakeBase):
    def __init__(self, **kwargs: Any) -> None:
        offered = kwargs.pop(
            "offered",
            Capabilities(offline=True, deterministic_replay=True, redacted_telemetry=True),
        )
        super().__init__(name="fake-telemetry", offered=offered, **kwargs)

    def process(
        self, request: TelemetryRequest, *, cancel: CancellationToken | None = None
    ) -> TelemetryResult:
        early = self._preflight(
            request_kind="telemetry",
            context_schema=request.context.input_schema_version,
            requested=request.context.requested_capabilities,
            metadata=request.context.metadata,
            media=None,
            timeout_ms=request.context.timeout_ms,
            cancel=cancel,
            namespace=request.context.namespace_id.value,
            job=request.context.job_id.value,
        )
        if isinstance(early, ResultState):
            reason = {
                ResultState.FAILED_TIMEOUT: FailureReason.TIMEOUT,
                ResultState.FAILED_CANCELLED: FailureReason.CANCELLATION,
            }.get(early)
            return TelemetryResult(
                state=early,
                identity=self.identity(),
                output_schema_version=BACKEND_OUTPUT_SCHEMA_VERSION,
                failure_reason=reason,
            )
        spans: list[Mapping[str, object]] = []
        for event in request.events:
            attrs = _redacted_metadata(event.attributes)
            spans.append(
                {
                    "name": event.span_name,
                    "namespace_id": request.context.namespace_id.value,
                    "job_id": request.context.job_id.value,
                    "attributes": attrs,
                    "reason": None if event.reason is None else event.reason.value,
                }
            )
        export = TelemetryExport(
            spans=tuple(spans),
            metrics=(
                {
                    "name": "backend.invocations",
                    "value": len(self.invocations),
                    "job_id": request.context.job_id.value,
                },
            ),
        )
        return TelemetryResult(
            state=ResultState.SUCCESS,
            identity=self.identity(),
            output_schema_version=BACKEND_OUTPUT_SCHEMA_VERSION,
            export=export,
        )
