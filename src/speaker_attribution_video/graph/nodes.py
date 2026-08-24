"""Typed graph nodes. Graph-level invariants are enforced later (G1F)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Union

from speaker_attribution_video.graph.enums import (
    DecisionState,
    DialogueKind,
    EvidenceSummary,
    FindingSeverity,
    ModelRole,
    NodeType,
    ReasonCode,
    RepairCategory,
    ReviewOutcome,
    Sensitivity,
    parse_enum,
)
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import (
    JobId,
    MediaId,
    ModelInvocationId,
    NamespaceId,
    NodeId,
    ReviewerId,
    require_hex64,
    require_slug,
)
from speaker_attribution_video.graph.jsonutil import JsonObject, as_json_object
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.text import SensitiveText, require_display_name, require_logical_uri
from speaker_attribution_video.graph.time import TimeSpan, format_utc, parse_utc, require_nonneg_int, require_utc
from speaker_attribution_video.graph.versions import NODE_SCHEMA_VERSION, SUPPORTED_NODE_SCHEMA_VERSIONS


def require_confidence_bp(value: object, *, required: bool = False) -> int | None:
    if value is None:
        if required:
            raise GraphContractError("confidence.required", "confidence_bp is required")
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 10000:
        raise GraphContractError("confidence.range", "confidence_bp must be an integer in 0..10000")
    return value


def require_mime(value: str) -> str:
    if not isinstance(value, str) or "/" not in value or len(value) > 128:
        raise GraphContractError("mime.invalid", "mime type is invalid")
    return value


@dataclass(frozen=True, slots=True)
class MediaArtifact:
    content_hash: str
    mime_type: str
    uri: str
    display_name: str
    media_id: MediaId
    duration_us: int | None = None
    container: str | None = None
    byte_size: int | None = None

    def __post_init__(self) -> None:
        require_hex64(self.content_hash, label="content_hash")
        require_mime(self.mime_type)
        require_logical_uri(self.uri, label="uri")
        require_display_name(self.display_name)
        if self.duration_us is not None:
            require_nonneg_int(self.duration_us, code="media.duration", label="duration_us")
        if self.container is not None:
            require_slug(self.container, label="container")
        if self.byte_size is not None:
            require_nonneg_int(self.byte_size, code="media.bytes", label="byte_size")


@dataclass(frozen=True, slots=True)
class AudioArtifact:
    content_hash: str
    uri: str
    display_name: str
    duration_us: int | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    mime_type: str | None = None
    parent_media_id: MediaId | None = None

    def __post_init__(self) -> None:
        require_hex64(self.content_hash, label="content_hash")
        require_logical_uri(self.uri, label="uri")
        require_display_name(self.display_name)
        if self.duration_us is not None:
            require_nonneg_int(self.duration_us, code="audio.duration", label="duration_us")
        if self.sample_rate_hz is not None:
            require_nonneg_int(self.sample_rate_hz, code="audio.rate", label="sample_rate_hz")
            if self.sample_rate_hz < 1:
                raise GraphContractError("audio.rate", "sample_rate_hz must be >= 1")
        if self.channels is not None:
            require_nonneg_int(self.channels, code="audio.channels", label="channels")
            if self.channels < 1:
                raise GraphContractError("audio.channels", "channels must be >= 1")
        if self.mime_type is not None:
            require_mime(self.mime_type)


@dataclass(frozen=True, slots=True)
class ProcessingStep:
    step_name: str
    sequence_index: int
    parameters: JsonObject | None = None

    def __post_init__(self) -> None:
        require_slug(self.step_name, label="step_name")
        require_nonneg_int(self.sequence_index, code="step.index", label="sequence_index")
        if self.parameters is not None:
            as_json_object(self.parameters)


@dataclass(frozen=True, slots=True)
class ModelInvocation:
    invocation_id: ModelInvocationId
    role: ModelRole
    parameter_digest: str
    logical_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, ModelRole):
            raise GraphContractError("model.role", "model role is invalid")
        require_hex64(self.parameter_digest, label="parameter_digest")
        if self.logical_name is not None:
            require_slug(self.logical_name, label="logical_name")


@dataclass(frozen=True, slots=True)
class OutputArtifact:
    artifact_kind: str
    uri: str
    display_name: str
    content_hash: str | None = None
    media_type: str | None = None

    def __post_init__(self) -> None:
        require_slug(self.artifact_kind, label="artifact_kind")
        require_logical_uri(self.uri, label="uri")
        require_display_name(self.display_name)
        if self.content_hash is not None:
            require_hex64(self.content_hash, label="content_hash")
        if self.media_type is not None:
            require_mime(self.media_type)


@dataclass(frozen=True, slots=True)
class AudioSegment:
    source_node_id: NodeId
    span: TimeSpan
    channel_index: int | None = None

    def __post_init__(self) -> None:
        if self.channel_index is not None:
            require_nonneg_int(self.channel_index, code="segment.channel", label="channel_index")


@dataclass(frozen=True, slots=True)
class DiarizationTurn:
    span: TimeSpan
    cluster_key: str
    confidence_bp: int | None = None

    def __post_init__(self) -> None:
        require_slug(self.cluster_key, label="cluster_key")
        require_confidence_bp(self.confidence_bp)


@dataclass(frozen=True, slots=True)
class TranscriptUtterance:
    span: TimeSpan
    text: SensitiveText
    language_tag: str | None = None
    confidence_bp: int | None = None

    def __post_init__(self) -> None:
        require_confidence_bp(self.confidence_bp)
        if self.language_tag is not None:
            require_slug(self.language_tag, label="language_tag")
        if self.text.sensitivity not in (Sensitivity.SENSITIVE, Sensitivity.RESTRICTED):
            raise GraphContractError("utterance.sensitivity", "utterance text must be sensitive")


@dataclass(frozen=True, slots=True)
class TranscriptToken:
    utterance_id: NodeId
    span: TimeSpan
    text: SensitiveText
    confidence_bp: int | None = None

    def __post_init__(self) -> None:
        require_confidence_bp(self.confidence_bp)
        if self.text.sensitivity not in (Sensitivity.SENSITIVE, Sensitivity.RESTRICTED):
            raise GraphContractError("token.sensitivity", "token text must be sensitive")


@dataclass(frozen=True, slots=True)
class SpeakerCluster:
    cluster_key: str
    display_label: str | None = None

    def __post_init__(self) -> None:
        require_slug(self.cluster_key, label="cluster_key")
        if self.display_label is not None:
            require_slug(self.display_label, label="display_label")


@dataclass(frozen=True, slots=True)
class CandidateIdentity:
    candidate_key: str
    display_label: str

    def __post_init__(self) -> None:
        require_slug(self.candidate_key, label="candidate_key")
        require_slug(self.display_label, label="display_label")


@dataclass(frozen=True, slots=True)
class AudioEvidence:
    summary: EvidenceSummary
    score_bp: int | None = None
    span: TimeSpan | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.summary, EvidenceSummary):
            raise GraphContractError("evidence.summary", "audio evidence summary is invalid")
        require_confidence_bp(self.score_bp)


@dataclass(frozen=True, slots=True)
class VisualEvidence:
    """Optional visual evidence record. No vendor backend is implemented in G1."""

    summary: EvidenceSummary
    score_bp: int | None = None
    span: TimeSpan | None = None

    def __post_init__(self) -> None:
        if self.summary not in (EvidenceSummary.FACE_COPRESENCE, EvidenceSummary.ACTIVE_SPEAKER, EvidenceSummary.OTHER):
            raise GraphContractError("evidence.summary", "visual evidence summary is invalid")
        require_confidence_bp(self.score_bp)


@dataclass(frozen=True, slots=True)
class DialogueEvidence:
    kind: DialogueKind
    span: TimeSpan | None = None
    text: SensitiveText | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DialogueKind):
            raise GraphContractError("dialogue.kind", "dialogue kind is invalid")
        if self.text is not None and self.text.sensitivity not in (
            Sensitivity.SENSITIVE,
            Sensitivity.RESTRICTED,
        ):
            raise GraphContractError("dialogue.sensitivity", "dialogue text must be sensitive")


@dataclass(frozen=True, slots=True)
class AttributionDecision:
    state: DecisionState
    subject_id: NodeId
    reason_code: ReasonCode
    selected_candidate_id: NodeId | None = None
    confidence_bp: int | None = None
    review_reason_code: ReasonCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, DecisionState):
            raise GraphContractError("decision.state", "decision state is invalid")
        if not isinstance(self.reason_code, ReasonCode):
            raise GraphContractError("decision.reason", "reason code is invalid")
        require_confidence_bp(self.confidence_bp)
        if self.review_reason_code is not None and not isinstance(self.review_reason_code, ReasonCode):
            raise GraphContractError("decision.review_reason", "review reason code is invalid")
        # Per-node structural checks; graph admission is G1D/G1F.
        if self.state is DecisionState.ATTRIBUTED and self.selected_candidate_id is None:
            raise GraphContractError("decision.attributed", "ATTRIBUTED requires exactly one selected candidate")
        if self.state is DecisionState.UNRESOLVED and self.selected_candidate_id is not None:
            raise GraphContractError("decision.unresolved", "UNRESOLVED must not contain a selected identity")
        if self.state is DecisionState.REQUIRES_REVIEW and self.review_reason_code is None:
            raise GraphContractError("decision.review", "REQUIRES_REVIEW must identify a review reason")


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    code: str
    severity: FindingSeverity
    subject_id: NodeId
    repair_category: RepairCategory
    message: str

    def __post_init__(self) -> None:
        require_slug(self.code, label="finding.code")
        if not isinstance(self.severity, FindingSeverity):
            raise GraphContractError("finding.severity", "severity is invalid")
        if not isinstance(self.repair_category, RepairCategory):
            raise GraphContractError("finding.repair", "repair category is invalid")
        if not isinstance(self.message, str) or not self.message or len(self.message) > 256:
            raise GraphContractError("finding.message", "finding message must be a short redacted string")
        if any(ch in self.message for ch in "\n\r\t"):
            raise GraphContractError("finding.message", "finding message must be a short redacted string")


@dataclass(frozen=True, slots=True)
class CorrectionAttempt:
    attempt_number: int
    finding_id: NodeId
    target_decision_id: NodeId
    reason_code: ReasonCode
    resulting_decision_id: NodeId | None = None

    def __post_init__(self) -> None:
        require_nonneg_int(self.attempt_number, code="correction.number", label="attempt_number")
        if self.attempt_number < 1:
            raise GraphContractError("correction.number", "attempt_number must start at 1")
        if not isinstance(self.reason_code, ReasonCode):
            raise GraphContractError("correction.reason", "reason code is invalid")


@dataclass(frozen=True, slots=True)
class HumanReviewDecision:
    reviewer_id: ReviewerId
    target_decision_id: NodeId
    outcome: ReviewOutcome
    replacement_decision_id: NodeId | None = None
    note_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ReviewOutcome):
            raise GraphContractError("review.outcome", "review outcome is invalid")
        if self.outcome is ReviewOutcome.OVERRIDE and self.replacement_decision_id is None:
            raise GraphContractError("review.override", "override must retain a replacement decision reference")
        if self.note_ref is not None:
            require_logical_uri(self.note_ref, label="note_ref")


Payload = Union[
    MediaArtifact,
    AudioArtifact,
    ProcessingStep,
    ModelInvocation,
    OutputArtifact,
    AudioSegment,
    DiarizationTurn,
    TranscriptUtterance,
    TranscriptToken,
    SpeakerCluster,
    CandidateIdentity,
    AudioEvidence,
    VisualEvidence,
    DialogueEvidence,
    AttributionDecision,
    ValidationFinding,
    CorrectionAttempt,
    HumanReviewDecision,
]

_PAYLOAD_TYPE: dict[NodeType, type[Payload]] = {
    NodeType.MEDIA_ARTIFACT: MediaArtifact,
    NodeType.AUDIO_ARTIFACT: AudioArtifact,
    NodeType.PROCESSING_STEP: ProcessingStep,
    NodeType.MODEL_INVOCATION: ModelInvocation,
    NodeType.OUTPUT_ARTIFACT: OutputArtifact,
    NodeType.AUDIO_SEGMENT: AudioSegment,
    NodeType.DIARIZATION_TURN: DiarizationTurn,
    NodeType.TRANSCRIPT_UTTERANCE: TranscriptUtterance,
    NodeType.TRANSCRIPT_TOKEN: TranscriptToken,
    NodeType.SPEAKER_CLUSTER: SpeakerCluster,
    NodeType.CANDIDATE_IDENTITY: CandidateIdentity,
    NodeType.AUDIO_EVIDENCE: AudioEvidence,
    NodeType.VISUAL_EVIDENCE: VisualEvidence,
    NodeType.DIALOGUE_EVIDENCE: DialogueEvidence,
    NodeType.ATTRIBUTION_DECISION: AttributionDecision,
    NodeType.VALIDATION_FINDING: ValidationFinding,
    NodeType.CORRECTION_ATTEMPT: CorrectionAttempt,
    NodeType.HUMAN_REVIEW_DECISION: HumanReviewDecision,
}

_TYPE_BY_PAYLOAD = {cls: node_type for node_type, cls in _PAYLOAD_TYPE.items()}


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: NodeId
    node_type: NodeType
    schema_version: str
    namespace_id: NamespaceId
    job_id: JobId
    created_at: datetime
    producer: Producer
    metadata: JsonObject
    sensitivity: Sensitivity
    provenance_refs: tuple[str, ...]
    payload: Payload

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_NODE_SCHEMA_VERSIONS:
            raise GraphContractError("node.schema", "unsupported node schema version")
        expected = _TYPE_BY_PAYLOAD.get(type(self.payload))
        if expected is None or expected is not self.node_type:
            raise GraphContractError("node.type", "node_type does not match payload")
        require_utc(self.created_at)
        as_json_object(self.metadata)
        if not isinstance(self.sensitivity, Sensitivity):
            raise GraphContractError("node.sensitivity", "sensitivity is invalid")
        for ref in self.provenance_refs:
            if not isinstance(ref, str) or not ref.startswith("g1.id.v1/"):
                raise GraphContractError("node.provenance", "provenance ref is malformed")
        _enforce_default_sensitivity(self)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "created_at": format_utc(self.created_at),
            "id": self.id.value,
            "job_id": self.job_id.value,
            "metadata": dict(sorted(self.metadata.items())),
            "namespace_id": self.namespace_id.value,
            "node_type": self.node_type.value,
            "payload": _payload_to_dict(self.payload),
            "producer": self.producer.to_dict(),
            "provenance_refs": list(self.provenance_refs),
            "schema_version": self.schema_version,
            "sensitivity": self.sensitivity.value,
        }
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GraphNode:
        node_type = parse_enum(NodeType, data.get("node_type"), code="node.type")
        payload_cls = _PAYLOAD_TYPE[node_type]  # type: ignore[index]
        payload = _payload_from_dict(payload_cls, data.get("payload"))
        created = data.get("created_at")
        if not isinstance(created, str):
            raise GraphContractError("node.created_at", "created_at is required")
        refs = data.get("provenance_refs") or []
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            raise GraphContractError("node.provenance", "provenance refs are invalid")
        return cls(
            id=NodeId(str(data.get("id"))),
            node_type=node_type,  # type: ignore[arg-type]
            schema_version=str(data.get("schema_version")),
            namespace_id=NamespaceId(str(data.get("namespace_id"))),
            job_id=JobId(str(data.get("job_id"))),
            created_at=parse_utc(created),
            producer=Producer.from_dict(_as_map(data.get("producer"))),
            metadata=as_json_object(_as_map(data.get("metadata") or {})),
            sensitivity=parse_enum(Sensitivity, data.get("sensitivity"), code="node.sensitivity"),  # type: ignore[arg-type]
            provenance_refs=tuple(refs),
            payload=payload,
        )


def make_node(
    *,
    namespace: NamespaceId,
    job: JobId,
    payload: Payload,
    producer: Producer,
    created_at: datetime,
    identity_parts: Mapping[str, object],
    metadata: Mapping[str, object] | None = None,
    sensitivity: Sensitivity | None = None,
    provenance_refs: tuple[str, ...] = (),
) -> GraphNode:
    node_type = _TYPE_BY_PAYLOAD[type(payload)]
    node_id = NodeId.derive(namespace, job, node_type.value, identity_parts)
    default_sens = sensitivity or _default_sensitivity(node_type)
    return GraphNode(
        id=node_id,
        node_type=node_type,
        schema_version=NODE_SCHEMA_VERSION,
        namespace_id=namespace,
        job_id=job,
        created_at=require_utc(created_at),
        producer=producer,
        metadata=as_json_object(metadata),
        sensitivity=default_sens,
        provenance_refs=provenance_refs,
        payload=payload,
    )


def _default_sensitivity(node_type: NodeType) -> Sensitivity:
    if node_type in (
        NodeType.TRANSCRIPT_UTTERANCE,
        NodeType.TRANSCRIPT_TOKEN,
        NodeType.DIALOGUE_EVIDENCE,
    ):
        return Sensitivity.SENSITIVE
    if node_type is NodeType.OUTPUT_ARTIFACT:
        return Sensitivity.INTERNAL
    return Sensitivity.INTERNAL


def _enforce_default_sensitivity(node: GraphNode) -> None:
    if node.node_type in (
        NodeType.TRANSCRIPT_UTTERANCE,
        NodeType.TRANSCRIPT_TOKEN,
        NodeType.DIALOGUE_EVIDENCE,
    ) and node.sensitivity not in (Sensitivity.SENSITIVE, Sensitivity.RESTRICTED):
        raise GraphContractError("node.sensitivity", "transcript-bearing nodes must be sensitive")


def _as_map(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise GraphContractError("node.object", "expected object")
    return value


def _nid(value: object) -> NodeId:
    if not isinstance(value, str):
        raise GraphContractError("node.ref", "node reference must be a string")
    return NodeId(value)


def _payload_to_dict(payload: Payload) -> dict[str, Any]:
    if isinstance(payload, MediaArtifact):
        return _omit_none(
            {
                "byte_size": payload.byte_size,
                "container": payload.container,
                "content_hash": payload.content_hash,
                "display_name": payload.display_name,
                "duration_us": payload.duration_us,
                "media_id": payload.media_id.value,
                "mime_type": payload.mime_type,
                "uri": payload.uri,
            }
        )
    if isinstance(payload, AudioArtifact):
        return _omit_none(
            {
                "channels": payload.channels,
                "content_hash": payload.content_hash,
                "display_name": payload.display_name,
                "duration_us": payload.duration_us,
                "mime_type": payload.mime_type,
                "parent_media_id": payload.parent_media_id.value if payload.parent_media_id else None,
                "sample_rate_hz": payload.sample_rate_hz,
                "uri": payload.uri,
            }
        )
    if isinstance(payload, ProcessingStep):
        return _omit_none(
            {
                "parameters": payload.parameters,
                "sequence_index": payload.sequence_index,
                "step_name": payload.step_name,
            }
        )
    if isinstance(payload, ModelInvocation):
        return _omit_none(
            {
                "invocation_id": payload.invocation_id.value,
                "logical_name": payload.logical_name,
                "parameter_digest": payload.parameter_digest,
                "role": payload.role.value,
            }
        )
    if isinstance(payload, OutputArtifact):
        return _omit_none(
            {
                "artifact_kind": payload.artifact_kind,
                "content_hash": payload.content_hash,
                "display_name": payload.display_name,
                "media_type": payload.media_type,
                "uri": payload.uri,
            }
        )
    if isinstance(payload, AudioSegment):
        return _omit_none(
            {
                "channel_index": payload.channel_index,
                "source_node_id": payload.source_node_id.value,
                "span": payload.span.to_dict(),
            }
        )
    if isinstance(payload, DiarizationTurn):
        return _omit_none(
            {
                "cluster_key": payload.cluster_key,
                "confidence_bp": payload.confidence_bp,
                "span": payload.span.to_dict(),
            }
        )
    if isinstance(payload, TranscriptUtterance):
        return _omit_none(
            {
                "confidence_bp": payload.confidence_bp,
                "language_tag": payload.language_tag,
                "span": payload.span.to_dict(),
                "text": payload.text.to_dict(),
            }
        )
    if isinstance(payload, TranscriptToken):
        return _omit_none(
            {
                "confidence_bp": payload.confidence_bp,
                "span": payload.span.to_dict(),
                "text": payload.text.to_dict(),
                "utterance_id": payload.utterance_id.value,
            }
        )
    if isinstance(payload, SpeakerCluster):
        return _omit_none({"cluster_key": payload.cluster_key, "display_label": payload.display_label})
    if isinstance(payload, CandidateIdentity):
        return {"candidate_key": payload.candidate_key, "display_label": payload.display_label}
    if isinstance(payload, AudioEvidence):
        return _omit_none(
            {
                "score_bp": payload.score_bp,
                "span": payload.span.to_dict() if payload.span else None,
                "summary": payload.summary.value,
            }
        )
    if isinstance(payload, VisualEvidence):
        return _omit_none(
            {
                "score_bp": payload.score_bp,
                "span": payload.span.to_dict() if payload.span else None,
                "summary": payload.summary.value,
            }
        )
    if isinstance(payload, DialogueEvidence):
        return _omit_none(
            {
                "kind": payload.kind.value,
                "span": payload.span.to_dict() if payload.span else None,
                "text": payload.text.to_dict() if payload.text else None,
            }
        )
    if isinstance(payload, AttributionDecision):
        return _omit_none(
            {
                "confidence_bp": payload.confidence_bp,
                "reason_code": payload.reason_code.value,
                "review_reason_code": payload.review_reason_code.value if payload.review_reason_code else None,
                "selected_candidate_id": payload.selected_candidate_id.value if payload.selected_candidate_id else None,
                "state": payload.state.value,
                "subject_id": payload.subject_id.value,
            }
        )
    if isinstance(payload, ValidationFinding):
        return {
            "code": payload.code,
            "message": payload.message,
            "repair_category": payload.repair_category.value,
            "severity": payload.severity.value,
            "subject_id": payload.subject_id.value,
        }
    if isinstance(payload, CorrectionAttempt):
        return _omit_none(
            {
                "attempt_number": payload.attempt_number,
                "finding_id": payload.finding_id.value,
                "reason_code": payload.reason_code.value,
                "resulting_decision_id": payload.resulting_decision_id.value if payload.resulting_decision_id else None,
                "target_decision_id": payload.target_decision_id.value,
            }
        )
    if isinstance(payload, HumanReviewDecision):
        return _omit_none(
            {
                "note_ref": payload.note_ref,
                "outcome": payload.outcome.value,
                "replacement_decision_id": payload.replacement_decision_id.value
                if payload.replacement_decision_id
                else None,
                "reviewer_id": payload.reviewer_id.value,
                "target_decision_id": payload.target_decision_id.value,
            }
        )
    raise GraphContractError("node.payload", "unsupported payload")


def _payload_from_dict(cls: type[Payload], data: object) -> Payload:
    mapping = _as_map(data)
    builder: dict[type[Payload], Callable[[Mapping[str, object]], Payload]] = {
        MediaArtifact: lambda d: MediaArtifact(
            content_hash=str(d["content_hash"]),
            mime_type=str(d["mime_type"]),
            uri=str(d["uri"]),
            display_name=str(d["display_name"]),
            media_id=MediaId(str(d["media_id"])),
            duration_us=_opt_int(d.get("duration_us")),
            container=_opt_str(d.get("container")),
            byte_size=_opt_int(d.get("byte_size")),
        ),
        AudioArtifact: lambda d: AudioArtifact(
            content_hash=str(d["content_hash"]),
            uri=str(d["uri"]),
            display_name=str(d["display_name"]),
            duration_us=_opt_int(d.get("duration_us")),
            sample_rate_hz=_opt_int(d.get("sample_rate_hz")),
            channels=_opt_int(d.get("channels")),
            mime_type=_opt_str(d.get("mime_type")),
            parent_media_id=MediaId(str(d["parent_media_id"])) if d.get("parent_media_id") else None,
        ),
        ProcessingStep: lambda d: ProcessingStep(
            step_name=str(d["step_name"]),
            sequence_index=int(d["sequence_index"]),  # type: ignore[arg-type]
            parameters=as_json_object(_as_map(d["parameters"])) if d.get("parameters") is not None else None,
        ),
        ModelInvocation: lambda d: ModelInvocation(
            invocation_id=ModelInvocationId(str(d["invocation_id"])),
            role=parse_enum(ModelRole, d.get("role"), code="model.role"),  # type: ignore[arg-type]
            parameter_digest=str(d["parameter_digest"]),
            logical_name=_opt_str(d.get("logical_name")),
        ),
        OutputArtifact: lambda d: OutputArtifact(
            artifact_kind=str(d["artifact_kind"]),
            uri=str(d["uri"]),
            display_name=str(d["display_name"]),
            content_hash=_opt_str(d.get("content_hash")),
            media_type=_opt_str(d.get("media_type")),
        ),
        AudioSegment: lambda d: AudioSegment(
            source_node_id=_nid(d.get("source_node_id")),
            span=TimeSpan.from_dict(_as_map(d.get("span"))),
            channel_index=_opt_int(d.get("channel_index")),
        ),
        DiarizationTurn: lambda d: DiarizationTurn(
            span=TimeSpan.from_dict(_as_map(d.get("span"))),
            cluster_key=str(d["cluster_key"]),
            confidence_bp=_opt_int(d.get("confidence_bp")),
        ),
        TranscriptUtterance: lambda d: TranscriptUtterance(
            span=TimeSpan.from_dict(_as_map(d.get("span"))),
            text=SensitiveText.from_dict(_as_map(d.get("text"))),
            language_tag=_opt_str(d.get("language_tag")),
            confidence_bp=_opt_int(d.get("confidence_bp")),
        ),
        TranscriptToken: lambda d: TranscriptToken(
            utterance_id=_nid(d.get("utterance_id")),
            span=TimeSpan.from_dict(_as_map(d.get("span"))),
            text=SensitiveText.from_dict(_as_map(d.get("text"))),
            confidence_bp=_opt_int(d.get("confidence_bp")),
        ),
        SpeakerCluster: lambda d: SpeakerCluster(
            cluster_key=str(d["cluster_key"]),
            display_label=_opt_str(d.get("display_label")),
        ),
        CandidateIdentity: lambda d: CandidateIdentity(
            candidate_key=str(d["candidate_key"]),
            display_label=str(d["display_label"]),
        ),
        AudioEvidence: lambda d: AudioEvidence(
            summary=parse_enum(EvidenceSummary, d.get("summary"), code="evidence.summary"),  # type: ignore[arg-type]
            score_bp=_opt_int(d.get("score_bp")),
            span=TimeSpan.from_dict(_as_map(d["span"])) if d.get("span") else None,
        ),
        VisualEvidence: lambda d: VisualEvidence(
            summary=parse_enum(EvidenceSummary, d.get("summary"), code="evidence.summary"),  # type: ignore[arg-type]
            score_bp=_opt_int(d.get("score_bp")),
            span=TimeSpan.from_dict(_as_map(d["span"])) if d.get("span") else None,
        ),
        DialogueEvidence: lambda d: DialogueEvidence(
            kind=parse_enum(DialogueKind, d.get("kind"), code="dialogue.kind"),  # type: ignore[arg-type]
            span=TimeSpan.from_dict(_as_map(d["span"])) if d.get("span") else None,
            text=SensitiveText.from_dict(_as_map(d["text"])) if d.get("text") else None,
        ),
        AttributionDecision: lambda d: AttributionDecision(
            state=parse_enum(DecisionState, d.get("state"), code="decision.state"),  # type: ignore[arg-type]
            subject_id=_nid(d.get("subject_id")),
            reason_code=parse_enum(ReasonCode, d.get("reason_code"), code="decision.reason"),  # type: ignore[arg-type]
            selected_candidate_id=_nid(d["selected_candidate_id"]) if d.get("selected_candidate_id") else None,
            confidence_bp=_opt_int(d.get("confidence_bp")),
            review_reason_code=parse_enum(ReasonCode, d.get("review_reason_code"), code="decision.review_reason")
            if d.get("review_reason_code")
            else None,  # type: ignore[arg-type]
        ),
        ValidationFinding: lambda d: ValidationFinding(
            code=str(d["code"]),
            severity=parse_enum(FindingSeverity, d.get("severity"), code="finding.severity"),  # type: ignore[arg-type]
            subject_id=_nid(d.get("subject_id")),
            repair_category=parse_enum(RepairCategory, d.get("repair_category"), code="finding.repair"),  # type: ignore[arg-type]
            message=str(d["message"]),
        ),
        CorrectionAttempt: lambda d: CorrectionAttempt(
            attempt_number=int(d["attempt_number"]),  # type: ignore[arg-type]
            finding_id=_nid(d.get("finding_id")),
            target_decision_id=_nid(d.get("target_decision_id")),
            reason_code=parse_enum(ReasonCode, d.get("reason_code"), code="correction.reason"),  # type: ignore[arg-type]
            resulting_decision_id=_nid(d["resulting_decision_id"]) if d.get("resulting_decision_id") else None,
        ),
        HumanReviewDecision: lambda d: HumanReviewDecision(
            reviewer_id=ReviewerId(str(d["reviewer_id"])),
            target_decision_id=_nid(d.get("target_decision_id")),
            outcome=parse_enum(ReviewOutcome, d.get("outcome"), code="review.outcome"),  # type: ignore[arg-type]
            replacement_decision_id=_nid(d["replacement_decision_id"]) if d.get("replacement_decision_id") else None,
            note_ref=_opt_str(d.get("note_ref")),
        ),
    }
    try:
        fn = builder[cls]
    except KeyError as exc:
        raise GraphContractError("node.payload", "unsupported payload") from exc
    try:
        return fn(mapping)
    except KeyError as exc:
        raise GraphContractError("node.field", "required node field is missing") from exc


def _omit_none(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None}


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise GraphContractError("node.field", "expected string")


def _opt_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise GraphContractError("node.field", "expected integer")
