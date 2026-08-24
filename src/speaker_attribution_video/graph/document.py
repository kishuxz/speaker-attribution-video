"""Versioned evidence graph document. Invalid graphs are not returned."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from speaker_attribution_video.graph.edges import GraphEdge
from speaker_attribution_video.graph.enums import Sensitivity, parse_enum
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import JobId, NamespaceId
from speaker_attribution_video.graph.jsonutil import JsonObject, as_json_object
from speaker_attribution_video.graph.nodes import GraphNode
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.time import format_utc, parse_utc, require_utc
from speaker_attribution_video.graph.versions import GRAPH_SCHEMA_VERSION, SUPPORTED_GRAPH_SCHEMA_VERSIONS

DEFAULT_MAX_CORRECTIONS = 1
HARD_MAX_CORRECTIONS = 8


@dataclass(frozen=True, slots=True)
class EvidenceGraphDocument:
    schema_version: str
    namespace_id: NamespaceId
    job_id: JobId
    created_at: datetime
    producer: Producer
    metadata: JsonObject
    sensitivity: Sensitivity
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    max_correction_attempts: int = DEFAULT_MAX_CORRECTIONS

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_GRAPH_SCHEMA_VERSIONS:
            raise GraphContractError("graph.schema", "unsupported graph schema version")
        require_utc(self.created_at)
        as_json_object(self.metadata)
        if not isinstance(self.max_correction_attempts, int) or isinstance(self.max_correction_attempts, bool):
            raise GraphContractError("graph.corrections", "max_correction_attempts must be an integer")
        if self.max_correction_attempts < 1 or self.max_correction_attempts > HARD_MAX_CORRECTIONS:
            raise GraphContractError("graph.corrections", "max_correction_attempts is out of bounds")

    def node_map(self) -> dict[str, GraphNode]:
        return {n.id.value: n for n in self.nodes}

    def to_dict(self) -> dict[str, Any]:
        nodes = sorted((n.to_dict() for n in self.nodes), key=lambda item: item["id"])
        edges = sorted((e.to_dict() for e in self.edges), key=lambda item: item["id"])
        return {
            "created_at": format_utc(self.created_at),
            "edges": edges,
            "job_id": self.job_id.value,
            "max_correction_attempts": self.max_correction_attempts,
            "metadata": dict(sorted(self.metadata.items())),
            "namespace_id": self.namespace_id.value,
            "nodes": nodes,
            "producer": self.producer.to_dict(),
            "schema_version": self.schema_version,
            "sensitivity": self.sensitivity.value,
        }

    @classmethod
    def from_dict_unvalidated(cls, data: Mapping[str, Any]) -> EvidenceGraphDocument:
        """Parse fields only. Callers must run the invariant validator before use."""
        created = data.get("created_at")
        if not isinstance(created, str):
            raise GraphContractError("graph.created_at", "created_at is required")
        nodes_raw = data.get("nodes")
        edges_raw = data.get("edges")
        if not isinstance(nodes_raw, list) or not isinstance(edges_raw, list):
            raise GraphContractError("graph.collections", "nodes and edges must be arrays")
        raw_producer = data.get("producer")
        producer_map: Mapping[str, object] = raw_producer if isinstance(raw_producer, dict) else {}
        raw_meta = data.get("metadata")
        meta_map: Mapping[str, object] = raw_meta if isinstance(raw_meta, dict) else {}
        max_corr = data.get("max_correction_attempts", DEFAULT_MAX_CORRECTIONS)
        if not isinstance(max_corr, int) or isinstance(max_corr, bool):
            raise GraphContractError("graph.corrections", "max_correction_attempts must be an integer")
        return cls(
            schema_version=str(data.get("schema_version")),
            namespace_id=NamespaceId(str(data.get("namespace_id"))),
            job_id=JobId(str(data.get("job_id"))),
            created_at=parse_utc(created),
            producer=Producer.from_dict(producer_map),
            metadata=as_json_object(meta_map),
            sensitivity=parse_enum(Sensitivity, data.get("sensitivity"), code="graph.sensitivity"),  # type: ignore[arg-type]
            nodes=tuple(GraphNode.from_dict(item) for item in nodes_raw),
            edges=tuple(GraphEdge.from_dict(item) for item in edges_raw),
            max_correction_attempts=max_corr,
        )
