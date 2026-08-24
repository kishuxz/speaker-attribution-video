from __future__ import annotations

import json
from pathlib import Path

import pytest

from graph_factory import VALID_BUILDERS, one_speaker
from speaker_attribution_video.graph.document import EvidenceGraphDocument
from speaker_attribution_video.graph.edges import EdgeType, make_edge
from speaker_attribution_video.graph.enums import DecisionState, ProducerKind, ReasonCode, Sensitivity, TextMode
from speaker_attribution_video.graph.ids import JobId, NamespaceId
from speaker_attribution_video.graph.nodes import (
    AttributionDecision,
    AudioArtifact,
    CandidateIdentity,
    SpeakerCluster,
    TranscriptUtterance,
    make_node,
)
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.serialize import assert_schema_drift_free, canonical_dumps_document, loads_document
from speaker_attribution_video.graph.text import SensitiveText
from speaker_attribution_video.graph.time import TimeSpan
from speaker_attribution_video.graph.validate import validate_graph
from speaker_attribution_video.graph.versions import GRAPH_SCHEMA_VERSION

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "synthetic" / "graph"


@pytest.mark.parametrize("name", sorted(VALID_BUILDERS))
def test_valid_fixtures_pass_and_serialize(name: str) -> None:
    doc = VALID_BUILDERS[name]()
    findings = validate_graph(doc)
    assert findings == (), {f.code for f in findings}
    text = canonical_dumps_document(doc)
    assert loads_document(text).to_dict()["schema_version"] == GRAPH_SCHEMA_VERSION
    path = FIXTURE_DIR / "valid" / f"{name}.json"
    assert path.is_file()
    loaded = loads_document(path.read_text(encoding="utf-8"))
    assert canonical_dumps_document(loaded) == text


def test_invalid_fixtures_are_rejected() -> None:
    invalid_dir = FIXTURE_DIR / "invalid"
    expected = {
        "unsupported_schema.json": {"graph.schema", "graph.invalid", "id.schema"},
        "duplicate_node.json": {"graph.duplicate_node"},
        "cross_job.json": {"graph.isolation", "edge.job"},
        "attributed_without_evidence.json": {"attribution.evidence_required", "attribution.confidence_not_admission"},
    }
    for path in sorted(invalid_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        codes: set[str] = set()
        try:
            from speaker_attribution_video.graph.validate import load_graph

            load_graph(raw)
            pytest.fail(f"{path.name} unexpectedly validated")
        except Exception as exc:
            code = getattr(exc, "code", "")
            codes.add(code)
            findings = getattr(exc, "findings", ())
            codes.update(f.code for f in findings)
        if path.name in expected:
            assert codes & expected[path.name], (path.name, codes)


def test_mutation_invalid_edge_is_not_silently_dropped() -> None:
    doc = one_speaker()
    audio = next(n for n in doc.nodes if n.node_type.value == "AudioArtifact")
    media = next(n for n in doc.nodes if n.node_type.value == "MediaArtifact")
    # SUPPORTS from audio to media is illegal; adding it must surface matrix, not disappear.
    from speaker_attribution_video.graph.errors import GraphContractError

    with pytest.raises(GraphContractError) as err:
        make_edge(
            edge_type=EdgeType.SUPPORTS,
            source=audio,
            target=media,
            producer=doc.producer,
            created_at=doc.created_at,
        )
    assert err.value.code == "edge.matrix"
    assert len(doc.edges) == len(one_speaker().edges)


def test_mutation_correction_bound_is_enforced() -> None:
    raw = one_speaker().to_dict()
    raw["max_correction_attempts"] = 1
    # If bounds were ignored this field would not matter; validator still requires 1..8.
    from speaker_attribution_video.graph.validate import load_graph

    load_graph(raw)
    raw["max_correction_attempts"] = 99
    with pytest.raises(Exception) as err:
        load_graph(raw)
    assert getattr(err.value, "code", "") == "graph.corrections"


def test_admission_is_not_a_constant_true() -> None:
    ns = NamespaceId.from_slug("synth.example")
    job = JobId.derive(ns, "job01")
    producer = Producer(ProducerKind.TEST, "fixture.builder")
    from datetime import datetime, timezone

    fixed = datetime(2026, 8, 24, 19, 0, 0, tzinfo=timezone.utc)
    cluster = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=producer,
        created_at=fixed,
        identity_parts={"cluster_key": "speaker_00"},
    )
    cand = make_node(
        namespace=ns,
        job=job,
        payload=CandidateIdentity(candidate_key="candidate_a", display_label="speaker_a"),
        producer=producer,
        created_at=fixed,
        identity_parts={"candidate_key": "candidate_a"},
    )
    decision = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.ATTRIBUTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.OK,
            selected_candidate_id=cand.id,
            confidence_bp=10000,
        ),
        producer=producer,
        created_at=fixed,
        identity_parts={"subject": cluster.id.value, "state": "ATTRIBUTED"},
    )
    from speaker_attribution_video.graph.attribution import admit_attribution, view_attribution

    view = view_attribution(decision, nodes=(cluster, cand, decision), edges=())
    codes = {i.code for i in admit_attribution(view)}
    assert "attribution.evidence_required" in codes
    assert codes != {"ok"}
    assert len(codes) >= 2


def test_model_invocation_count_is_not_admission() -> None:
    doc = one_speaker()
    attributed = [n for n in doc.nodes if n.node_type.value == "AttributionDecision"]
    assert attributed
    # Presence of any number of processing steps does not replace SUPPORTS.
    steps = [n for n in doc.nodes if n.node_type.value == "ProcessingStep"]
    assert steps
    from speaker_attribution_video.graph.attribution import admit_attribution, view_attribution

    view = view_attribution(attributed[0], nodes=doc.nodes, edges=())
    codes = {i.code for i in admit_attribution(view)}
    assert "attribution.evidence_required" in codes


def test_embedded_text_not_in_invalid_error() -> None:
    ns = NamespaceId.from_slug("synth.example")
    job = JobId.derive(ns, "job01")
    producer = Producer(ProducerKind.TEST, "fixture.builder")
    from datetime import datetime, timezone

    fixed = datetime(2026, 8, 24, 19, 0, 0, tzinfo=timezone.utc)
    secret = "copyrighted-dialogue-must-not-appear"
    with pytest.raises(Exception) as err:
        make_node(
            namespace=ns,
            job=job,
            payload=TranscriptUtterance(
                span=TimeSpan(0, 10),
                text=SensitiveText(mode=TextMode.EMBEDDED, sensitivity=Sensitivity.PUBLIC, embedded=secret),
            ),
            producer=producer,
            created_at=fixed,
            identity_parts={"x": "1"},
        )
    assert secret not in str(err.value)


def test_schema_drift_and_valid_json_enum_membership() -> None:
    assert_schema_drift_free()
    schema = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "src/speaker_attribution_video/graph/schemas/evidence_graph.g1.v1.json"
        ).read_text(encoding="utf-8")
    )
    doc = json.loads(canonical_dumps_document(one_speaker()))
    for node in doc["nodes"]:
        assert node["node_type"] in schema["$defs"]["NodeType"]["enum"]
    for edge in doc["edges"]:
        assert edge["edge_type"] in schema["$defs"]["EdgeType"]["enum"]
