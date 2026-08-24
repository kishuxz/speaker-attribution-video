from __future__ import annotations

from datetime import datetime, timezone

import pytest

from speaker_attribution_video.graph.document import EvidenceGraphDocument
from speaker_attribution_video.graph.edges import EdgeType, make_edge
from speaker_attribution_video.graph.enums import DecisionState, ProducerKind, ReasonCode, Sensitivity
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import JobId, MediaId, NamespaceId
from speaker_attribution_video.graph.nodes import (
    AttributionDecision,
    AudioArtifact,
    MediaArtifact,
    ProcessingStep,
    SpeakerCluster,
    make_node,
)
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.serialize import (
    assert_schema_drift_free,
    canonical_bytes,
    canonical_dumps_document,
    load_json_schema,
    loads_document,
)
from speaker_attribution_video.graph.versions import GRAPH_SCHEMA_VERSION

FIXED = datetime(2026, 8, 24, 19, 0, 0, tzinfo=timezone.utc)
HASH = "d" * 64
NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")
PRODUCER = Producer(ProducerKind.TEST, "fixture.builder")


def _valid_doc() -> EvidenceGraphDocument:
    uri = "artifact://synth.example/media/primary"
    media = make_node(
        namespace=NS,
        job=JOB,
        payload=MediaArtifact(
            content_hash=HASH,
            mime_type="audio/wav",
            uri=uri,
            display_name="synthetic-audio-01",
            media_id=MediaId.derive(NS, JOB, HASH, uri),
            duration_us=1_000_000,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": uri},
    )
    audio = make_node(
        namespace=NS,
        job=JOB,
        payload=AudioArtifact(
            content_hash=HASH,
            uri="artifact://synth.example/audio/track",
            display_name="synthetic-track-01",
            duration_us=1_000_000,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": "artifact://synth.example/audio/track"},
    )
    step = make_node(
        namespace=NS,
        job=JOB,
        payload=ProcessingStep(step_name="ingest", sequence_index=0),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"step": "ingest"},
    )
    cluster = make_node(
        namespace=NS,
        job=JOB,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    decision = make_node(
        namespace=NS,
        job=JOB,
        payload=AttributionDecision(
            state=DecisionState.UNRESOLVED,
            subject_id=cluster.id,
            reason_code=ReasonCode.INSUFFICIENT_EVIDENCE,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "UNRESOLVED"},
    )
    return EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, cluster, decision),
        edges=(
            make_edge(edge_type=EdgeType.EXTRACTED_FROM, source=audio, target=media, producer=PRODUCER, created_at=FIXED),
            make_edge(edge_type=EdgeType.PRODUCED_BY, source=audio, target=step, producer=PRODUCER, created_at=FIXED),
        ),
    )


def _assert_instance_fits_schema(data: dict) -> None:
    schema = load_json_schema()
    required = schema["required"]
    for key in required:
        assert key in data
    assert data["schema_version"] == schema["properties"]["schema_version"]["const"]
    node_enum = schema["$defs"]["NodeType"]["enum"]
    edge_enum = schema["$defs"]["EdgeType"]["enum"]
    for node in data["nodes"]:
        assert node["node_type"] in node_enum
    for edge in data["edges"]:
        assert edge["edge_type"] in edge_enum


def test_equivalent_graphs_are_byte_identical() -> None:
    a = canonical_bytes(_valid_doc())
    b = canonical_bytes(_valid_doc())
    assert a == b
    assert b"NaN" not in a
    assert b"Infinity" not in a


def test_roundtrip_is_stable() -> None:
    original = canonical_dumps_document(_valid_doc())
    loaded = loads_document(original)
    again = canonical_dumps_document(loaded)
    assert original == again
    _assert_instance_fits_schema(loaded.to_dict())


def test_schema_drift_check() -> None:
    assert_schema_drift_free()


def test_invalid_document_fails_before_return() -> None:
    raw = _valid_doc().to_dict()
    raw["nodes"] = []
    raw["edges"] = [{"not": "an-edge"}]
    with pytest.raises(GraphContractError):
        loads_document(canonical_dumps_document(_valid_doc()).replace(GRAPH_SCHEMA_VERSION, "g1.graph.v0", 1))
