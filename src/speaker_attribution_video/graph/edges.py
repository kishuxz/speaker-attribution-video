"""Typed edges and the allowed source/target matrix. No generic relationship type."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from speaker_attribution_video.graph.enums import NodeType, Sensitivity, parse_enum
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import EdgeId, JobId, NamespaceId, NodeId
from speaker_attribution_video.graph.jsonutil import JsonObject, as_json_object
from speaker_attribution_video.graph.nodes import GraphNode
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.time import format_utc, parse_utc, require_utc
from speaker_attribution_video.graph.versions import EDGE_SCHEMA_VERSION, SUPPORTED_EDGE_SCHEMA_VERSIONS


class EdgeType(str, Enum):
    EXTRACTED_FROM = "EXTRACTED_FROM"
    NORMALIZED_FROM = "NORMALIZED_FROM"
    SEGMENTED_FROM = "SEGMENTED_FROM"
    DIARIZED_AS = "DIARIZED_AS"
    TRANSCRIBED_FROM = "TRANSCRIBED_FROM"
    ALIGNED_TO = "ALIGNED_TO"
    ASSIGNED_TO = "ASSIGNED_TO"
    CANDIDATE_FOR = "CANDIDATE_FOR"
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    DERIVED_FROM = "DERIVED_FROM"
    PRODUCED_BY = "PRODUCED_BY"
    VALIDATES = "VALIDATES"
    REJECTS = "REJECTS"
    CORRECTED_BY = "CORRECTED_BY"
    REVIEWED_BY = "REVIEWED_BY"
    EMITTED_AS = "EMITTED_AS"


def _pairs(*pairs: tuple[NodeType, NodeType]) -> frozenset[tuple[NodeType, NodeType]]:
    return frozenset(pairs)


# source → target
ALLOWED_MATRIX: dict[EdgeType, frozenset[tuple[NodeType, NodeType]]] = {
    EdgeType.EXTRACTED_FROM: _pairs((NodeType.AUDIO_ARTIFACT, NodeType.MEDIA_ARTIFACT)),
    EdgeType.NORMALIZED_FROM: _pairs((NodeType.AUDIO_ARTIFACT, NodeType.AUDIO_ARTIFACT)),
    EdgeType.SEGMENTED_FROM: _pairs((NodeType.AUDIO_SEGMENT, NodeType.AUDIO_ARTIFACT)),
    EdgeType.DIARIZED_AS: _pairs(
        (NodeType.DIARIZATION_TURN, NodeType.AUDIO_SEGMENT),
        (NodeType.DIARIZATION_TURN, NodeType.AUDIO_ARTIFACT),
    ),
    EdgeType.TRANSCRIBED_FROM: _pairs(
        (NodeType.TRANSCRIPT_UTTERANCE, NodeType.AUDIO_SEGMENT),
        (NodeType.TRANSCRIPT_UTTERANCE, NodeType.DIARIZATION_TURN),
    ),
    EdgeType.ALIGNED_TO: _pairs(
        (NodeType.TRANSCRIPT_TOKEN, NodeType.TRANSCRIPT_UTTERANCE),
        (NodeType.TRANSCRIPT_UTTERANCE, NodeType.DIARIZATION_TURN),
    ),
    EdgeType.ASSIGNED_TO: _pairs(
        (NodeType.DIARIZATION_TURN, NodeType.SPEAKER_CLUSTER),
        (NodeType.TRANSCRIPT_UTTERANCE, NodeType.SPEAKER_CLUSTER),
    ),
    EdgeType.CANDIDATE_FOR: _pairs(
        (NodeType.CANDIDATE_IDENTITY, NodeType.SPEAKER_CLUSTER),
        (NodeType.CANDIDATE_IDENTITY, NodeType.ATTRIBUTION_DECISION),
    ),
    EdgeType.SUPPORTS: _pairs(
        (NodeType.AUDIO_EVIDENCE, NodeType.ATTRIBUTION_DECISION),
        (NodeType.VISUAL_EVIDENCE, NodeType.ATTRIBUTION_DECISION),
        (NodeType.DIALOGUE_EVIDENCE, NodeType.ATTRIBUTION_DECISION),
    ),
    EdgeType.CONTRADICTS: _pairs(
        (NodeType.AUDIO_EVIDENCE, NodeType.ATTRIBUTION_DECISION),
        (NodeType.VISUAL_EVIDENCE, NodeType.ATTRIBUTION_DECISION),
        (NodeType.DIALOGUE_EVIDENCE, NodeType.ATTRIBUTION_DECISION),
    ),
    EdgeType.DERIVED_FROM: _pairs(
        (NodeType.AUDIO_ARTIFACT, NodeType.MEDIA_ARTIFACT),
        (NodeType.AUDIO_SEGMENT, NodeType.AUDIO_ARTIFACT),
        (NodeType.DIARIZATION_TURN, NodeType.AUDIO_SEGMENT),
        (NodeType.TRANSCRIPT_UTTERANCE, NodeType.DIARIZATION_TURN),
        (NodeType.TRANSCRIPT_TOKEN, NodeType.TRANSCRIPT_UTTERANCE),
        (NodeType.AUDIO_EVIDENCE, NodeType.AUDIO_SEGMENT),
        (NodeType.AUDIO_EVIDENCE, NodeType.DIARIZATION_TURN),
        (NodeType.AUDIO_EVIDENCE, NodeType.SPEAKER_CLUSTER),
        (NodeType.VISUAL_EVIDENCE, NodeType.MEDIA_ARTIFACT),
        (NodeType.DIALOGUE_EVIDENCE, NodeType.TRANSCRIPT_UTTERANCE),
        (NodeType.ATTRIBUTION_DECISION, NodeType.ATTRIBUTION_DECISION),
        (NodeType.ATTRIBUTION_DECISION, NodeType.SPEAKER_CLUSTER),
        (NodeType.CORRECTION_ATTEMPT, NodeType.VALIDATION_FINDING),
        (NodeType.CORRECTION_ATTEMPT, NodeType.ATTRIBUTION_DECISION),
        (NodeType.HUMAN_REVIEW_DECISION, NodeType.ATTRIBUTION_DECISION),
        (NodeType.OUTPUT_ARTIFACT, NodeType.ATTRIBUTION_DECISION),
        (NodeType.VALIDATION_FINDING, NodeType.ATTRIBUTION_DECISION),
    ),
    EdgeType.PRODUCED_BY: _pairs(
        *((src, tgt) for src in NodeType for tgt in (NodeType.PROCESSING_STEP, NodeType.MODEL_INVOCATION) if src is not tgt)
    ),
    EdgeType.VALIDATES: _pairs((NodeType.VALIDATION_FINDING, NodeType.ATTRIBUTION_DECISION)),
    EdgeType.REJECTS: _pairs((NodeType.VALIDATION_FINDING, NodeType.ATTRIBUTION_DECISION)),
    EdgeType.CORRECTED_BY: _pairs((NodeType.ATTRIBUTION_DECISION, NodeType.CORRECTION_ATTEMPT)),
    EdgeType.REVIEWED_BY: _pairs((NodeType.ATTRIBUTION_DECISION, NodeType.HUMAN_REVIEW_DECISION)),
    EdgeType.EMITTED_AS: _pairs(
        (NodeType.PROCESSING_STEP, NodeType.OUTPUT_ARTIFACT),
        (NodeType.MODEL_INVOCATION, NodeType.OUTPUT_ARTIFACT),
        (NodeType.ATTRIBUTION_DECISION, NodeType.OUTPUT_ARTIFACT),
    ),
}

# PRODUCED_BY generated pairs include ProcessingStep → ProcessingStep. Remove self-type if present.
ALLOWED_MATRIX[EdgeType.PRODUCED_BY] = frozenset(
    (src, tgt)
    for src, tgt in ALLOWED_MATRIX[EdgeType.PRODUCED_BY]
    if src is not tgt
)

ACYCLIC_EDGE_TYPES = frozenset(
    {
        EdgeType.DERIVED_FROM,
        EdgeType.EXTRACTED_FROM,
        EdgeType.NORMALIZED_FROM,
        EdgeType.SEGMENTED_FROM,
        EdgeType.CORRECTED_BY,
        EdgeType.PRODUCED_BY,
    }
)

EVIDENCE_EDGE_TYPES = frozenset({EdgeType.SUPPORTS, EdgeType.CONTRADICTS})


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: EdgeId
    edge_type: EdgeType
    schema_version: str
    namespace_id: NamespaceId
    job_id: JobId
    created_at: datetime
    producer: Producer
    metadata: JsonObject
    sensitivity: Sensitivity
    provenance_refs: tuple[str, ...]
    source_id: NodeId
    target_id: NodeId

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_EDGE_SCHEMA_VERSIONS:
            raise GraphContractError("edge.schema", "unsupported edge schema version")
        if not isinstance(self.edge_type, EdgeType):
            raise GraphContractError("edge.type", "unsupported edge type")
        require_utc(self.created_at)
        as_json_object(self.metadata)
        if self.source_id == self.target_id:
            raise GraphContractError("edge.self", "self-edges are not permitted")
        if not isinstance(self.sensitivity, Sensitivity):
            raise GraphContractError("edge.sensitivity", "sensitivity is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": format_utc(self.created_at),
            "edge_type": self.edge_type.value,
            "id": self.id.value,
            "job_id": self.job_id.value,
            "metadata": dict(sorted(self.metadata.items())),
            "namespace_id": self.namespace_id.value,
            "producer": self.producer.to_dict(),
            "provenance_refs": list(self.provenance_refs),
            "schema_version": self.schema_version,
            "sensitivity": self.sensitivity.value,
            "source_id": self.source_id.value,
            "target_id": self.target_id.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GraphEdge:
        created = data.get("created_at")
        if not isinstance(created, str):
            raise GraphContractError("edge.created_at", "created_at is required")
        refs = data.get("provenance_refs") or []
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            raise GraphContractError("edge.provenance", "provenance refs are invalid")
        return cls(
            id=EdgeId(str(data.get("id"))),
            edge_type=parse_enum(EdgeType, data.get("edge_type"), code="edge.type"),  # type: ignore[arg-type]
            schema_version=str(data.get("schema_version")),
            namespace_id=NamespaceId(str(data.get("namespace_id"))),
            job_id=JobId(str(data.get("job_id"))),
            created_at=parse_utc(created),
            producer=Producer.from_dict(data.get("producer") if isinstance(data.get("producer"), dict) else {}),
            metadata=as_json_object(data.get("metadata") if isinstance(data.get("metadata"), dict) else {}),
            sensitivity=parse_enum(Sensitivity, data.get("sensitivity"), code="edge.sensitivity"),  # type: ignore[arg-type]
            provenance_refs=tuple(refs),
            source_id=NodeId(str(data.get("source_id"))),
            target_id=NodeId(str(data.get("target_id"))),
        )


def matrix_allows(edge_type: EdgeType, source_type: NodeType, target_type: NodeType) -> bool:
    allowed = ALLOWED_MATRIX.get(edge_type)
    if allowed is None:
        return False
    return (source_type, target_type) in allowed


def make_edge(
    *,
    edge_type: EdgeType,
    source: GraphNode,
    target: GraphNode,
    producer: Producer,
    created_at: datetime,
    metadata: Mapping[str, object] | None = None,
    sensitivity: Sensitivity = Sensitivity.INTERNAL,
    provenance_refs: tuple[str, ...] = (),
) -> GraphEdge:
    if source.namespace_id != target.namespace_id:
        raise GraphContractError("edge.namespace", "cross-namespace edges are not permitted")
    if source.job_id != target.job_id:
        raise GraphContractError("edge.job", "cross-job edges are not permitted")
    if source.id == target.id:
        raise GraphContractError("edge.self", "self-edges are not permitted")
    if not matrix_allows(edge_type, source.node_type, target.node_type):
        raise GraphContractError("edge.matrix", "source and target types are not allowed for this edge")
    edge_id = EdgeId.derive(source.namespace_id, source.job_id, edge_type.value, source.id, target.id)
    return GraphEdge(
        id=edge_id,
        edge_type=edge_type,
        schema_version=EDGE_SCHEMA_VERSION,
        namespace_id=source.namespace_id,
        job_id=source.job_id,
        created_at=require_utc(created_at),
        producer=producer,
        metadata=as_json_object(metadata),
        sensitivity=sensitivity,
        provenance_refs=provenance_refs,
        source_id=source.id,
        target_id=target.id,
    )
