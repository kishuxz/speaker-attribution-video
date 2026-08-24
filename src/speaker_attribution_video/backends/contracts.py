"""Model-neutral backend contracts. No real audio or model processing."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from speaker_attribution_video.backends.capabilities import Capabilities, Capability
from speaker_attribution_video.backends.failures import BackendError, FailureReason, ResultState
from speaker_attribution_video.graph.edges import GraphEdge
from speaker_attribution_video.graph.ids import JobId, NamespaceId, NodeId
from speaker_attribution_video.graph.jsonutil import canonical_object
from speaker_attribution_video.graph.nodes import GraphNode
from speaker_attribution_video.graph.versions import GRAPH_SCHEMA_VERSION

BACKEND_INPUT_SCHEMA_VERSION = "t1.backend.input.v1"
BACKEND_OUTPUT_SCHEMA_VERSION = "t1.backend.output.v1"
SUPPORTED_INPUT_SCHEMA_VERSIONS = frozenset({BACKEND_INPUT_SCHEMA_VERSION})
SUPPORTED_OUTPUT_SCHEMA_VERSIONS = frozenset({BACKEND_OUTPUT_SCHEMA_VERSION})
SYNTHETIC_URI_PREFIX = "artifact://synth.example/"


@dataclass(frozen=True, slots=True)
class BackendIdentity:
    name: str
    version: str
    configuration_fingerprint: str
    deterministic: bool
    input_schema_version: str
    output_schema_version: str
    supports_timeout: bool
    supports_cancellation: bool

    @property
    def backend_id(self) -> str:
        return f"{self.name}/{self.version}"


def fingerprint_config(config: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_object(dict(config)).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class HealthResult:
    ready: bool
    live: bool
    reason: FailureReason | None = None


class CancellationToken:
    """Caller-owned cancellation flag. Backends must not clear it."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled


@dataclass(frozen=True, slots=True)
class RequestContext:
    namespace_id: NamespaceId
    job_id: JobId
    input_schema_version: str = BACKEND_INPUT_SCHEMA_VERSION
    requested_capabilities: frozenset[Capability] = field(default_factory=frozenset)
    timeout_ms: int | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GraphFragment:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    graph_schema_version: str = GRAPH_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class InvocationRecord:
    backend_id: str
    backend_version: str
    configuration_fingerprint: str
    namespace_id: str
    job_id: str
    request_kind: str
    redacted_metadata: Mapping[str, object]
    result_state: ResultState | None = None
    failure_reason: FailureReason | None = None


@dataclass(frozen=True, slots=True)
class BackendResult:
    state: ResultState
    identity: BackendIdentity
    output_schema_version: str
    fragment: GraphFragment | None = None
    failure_reason: FailureReason | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.state is ResultState.SUCCESS and self.failure_reason is not None:
            raise ValueError("successful results cannot carry a failure reason")
        if self.state is ResultState.SUCCESS and self.fragment is None:
            raise ValueError("successful graph results require a fragment")


@dataclass(frozen=True, slots=True)
class MediaRef:
    uri: str
    content_hash: str
    duration_us: int
    display_name: str = "synthetic-media"


@dataclass(frozen=True, slots=True)
class AudioRequest:
    context: RequestContext
    media: MediaRef


@dataclass(frozen=True, slots=True)
class DiarizationRequest:
    context: RequestContext
    media: MediaRef
    speaker_count_hint: int | None = None
    allow_overlap: bool = True


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    context: RequestContext
    media: MediaRef
    turn_ids: tuple[NodeId, ...] = ()
    language_tag: str | None = None


@dataclass(frozen=True, slots=True)
class AlignmentRequest:
    context: RequestContext
    media: MediaRef
    utterance_ids: tuple[NodeId, ...] = ()
    turn_ids: tuple[NodeId, ...] = ()
    want_word_timestamps: bool = False


@dataclass(frozen=True, slots=True)
class VideoEvidenceRequest:
    context: RequestContext
    media: MediaRef
    segment_ids: tuple[NodeId, ...] = ()
    candidate_ids: tuple[NodeId, ...] = ()
    video_available: bool = False


@dataclass(frozen=True, slots=True)
class AttributionModelRequest:
    context: RequestContext
    subject_id: NodeId
    candidate_ids: tuple[NodeId, ...] = ()
    evidence_ids: tuple[NodeId, ...] = ()
    confidence_bp: int | None = None


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    span_name: str
    attributes: Mapping[str, object]
    reason: FailureReason | None = None


@dataclass(frozen=True, slots=True)
class TelemetryRequest:
    context: RequestContext
    events: tuple[TelemetryEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class TelemetryExport:
    spans: tuple[Mapping[str, object], ...]
    metrics: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class TelemetryResult:
    state: ResultState
    identity: BackendIdentity
    output_schema_version: str
    export: TelemetryExport | None = None
    failure_reason: FailureReason | None = None
    message: str | None = None


class BackendCore(Protocol):
    def identity(self) -> BackendIdentity: ...

    def capabilities(self) -> Capabilities: ...

    def health(self) -> HealthResult: ...

    def close(self) -> None: ...


@runtime_checkable
class AudioBackend(BackendCore, Protocol):
    def process(
        self,
        request: AudioRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> BackendResult: ...


@runtime_checkable
class DiarizationBackend(BackendCore, Protocol):
    def process(
        self,
        request: DiarizationRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> BackendResult: ...


@runtime_checkable
class TranscriptionBackend(BackendCore, Protocol):
    def process(
        self,
        request: TranscriptionRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> BackendResult: ...


@runtime_checkable
class AlignmentBackend(BackendCore, Protocol):
    def process(
        self,
        request: AlignmentRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> BackendResult: ...


@runtime_checkable
class VideoEvidenceBackend(BackendCore, Protocol):
    def process(
        self,
        request: VideoEvidenceRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> BackendResult: ...


@runtime_checkable
class AttributionModelBackend(BackendCore, Protocol):
    def process(
        self,
        request: AttributionModelRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> BackendResult: ...


@runtime_checkable
class TelemetryBackend(BackendCore, Protocol):
    def process(
        self,
        request: TelemetryRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> TelemetryResult: ...


def require_synthetic_uri(uri: str) -> str:
    if not isinstance(uri, str) or not uri.startswith(SYNTHETIC_URI_PREFIX):
        raise BackendError(
            FailureReason.INVALID_INPUT,
            "synthetic media reference is required",
            details={"uri_kind": "non_synthetic"},
        )
    return uri


def require_input_schema(version: str) -> str:
    if version not in SUPPORTED_INPUT_SCHEMA_VERSIONS:
        raise BackendError(
            FailureReason.SCHEMA_MISMATCH,
            "unsupported backend input schema version",
            details={"schema": version},
        )
    return version
