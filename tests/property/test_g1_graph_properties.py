"""Hypothesis properties for G1. Synthetic data only; failing examples are printed."""

from __future__ import annotations

import json
import random
from dataclasses import replace

import pytest
from hypothesis import assume, given, note, settings
from hypothesis import strategies as st

from graph_factory import VALID_BUILDERS
from speaker_attribution_video.graph.document import HARD_MAX_CORRECTIONS, EvidenceGraphDocument
from speaker_attribution_video.graph.edges import EdgeType, GraphEdge, make_edge
from speaker_attribution_video.graph.enums import (
    DecisionState,
    FindingSeverity,
    ProducerKind,
    ReasonCode,
    RepairCategory,
    Sensitivity,
)
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import EdgeId, JobId, NamespaceId, NodeId
from speaker_attribution_video.graph.nodes import (
    AttributionDecision,
    CorrectionAttempt,
    ValidationFinding,
    make_node,
)
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.serialize import canonical_dumps_document, loads_document
from speaker_attribution_video.graph.time import TimeSpan
from speaker_attribution_video.graph.validate import (
    GraphValidationError,
    load_graph,
    validate_graph,
)
from speaker_attribution_video.graph.versions import EDGE_SCHEMA_VERSION, GRAPH_SCHEMA_VERSION

pytestmark = pytest.mark.property

_BUILDER_NAMES = tuple(sorted(VALID_BUILDERS))
_SLUG = st.from_regex(r"^[a-z][a-z0-9]{1,8}$", fullmatch=True)
_US = st.integers(min_value=0, max_value=5_000_000)
_SECRET = "private-dialogue-must-never-appear"
FIXED_PRODUCER = Producer(ProducerKind.TEST, "property.builder")


def _doc(name: str) -> EvidenceGraphDocument:
    return VALID_BUILDERS[name]()


@given(name=st.sampled_from(_BUILDER_NAMES), seed=st.integers(min_value=0, max_value=50_000))
@settings(max_examples=25)
def test_valid_generated_graphs_pass_and_round_trip(name: str, seed: int) -> None:
    doc = _doc(name)
    findings = validate_graph(doc)
    assert findings == ()
    blob = canonical_dumps_document(doc)
    restored = loads_document(blob)
    assert restored.namespace_id == doc.namespace_id
    assert restored.job_id == doc.job_id
    assert {n.id.value for n in restored.nodes} == {n.id.value for n in doc.nodes}
    assert {e.id.value for e in restored.edges} == {e.id.value for e in doc.edges}
    rng = random.Random(seed)
    nodes = list(doc.nodes)
    edges = list(doc.edges)
    rng.shuffle(nodes)
    rng.shuffle(edges)
    shuffled = replace(doc, nodes=tuple(nodes), edges=tuple(edges))
    assert canonical_dumps_document(shuffled) == blob
    note(f"builder={name} seed={seed}")


@given(name=st.sampled_from(_BUILDER_NAMES))
@settings(max_examples=20)
def test_invalid_endpoint_references_fail(name: str) -> None:
    doc = _doc(name)
    assume(len(doc.edges) >= 1)
    ghost = NodeId.derive(doc.namespace_id, doc.job_id, "MediaArtifact", {"ghost": "missing"})
    broken_edges = []
    for edge in doc.edges:
        if edge is doc.edges[0]:
            broken_edges.append(
                GraphEdge(
                    id=edge.id,
                    edge_type=edge.edge_type,
                    schema_version=edge.schema_version,
                    namespace_id=edge.namespace_id,
                    job_id=edge.job_id,
                    created_at=edge.created_at,
                    producer=edge.producer,
                    metadata=dict(edge.metadata),
                    sensitivity=edge.sensitivity,
                    provenance_refs=edge.provenance_refs,
                    source_id=edge.source_id,
                    target_id=ghost,
                )
            )
        else:
            broken_edges.append(edge)
    broken = replace(doc, edges=tuple(broken_edges))
    codes = {f.code for f in validate_graph(broken)}
    assert "graph.endpoint" in codes
    blob = " ".join(f.message for f in validate_graph(broken))
    assert _SECRET not in blob


@given(name=st.sampled_from(_BUILDER_NAMES))
@settings(max_examples=15)
def test_cross_job_edges_never_pass(name: str) -> None:
    doc = _doc(name)
    assume(len(doc.nodes) >= 2)
    other_ns = NamespaceId.from_slug("other.example")
    other_job = JobId.derive(other_ns, "job99")
    source = doc.nodes[0]
    target = make_node(
        namespace=other_ns,
        job=other_job,
        payload=source.payload,
        producer=source.producer,
        created_at=source.created_at,
        identity_parts={"cross": "job", "job": other_job.value},
    )
    with pytest.raises(GraphContractError) as exc:
        make_edge(
            edge_type=EdgeType.DERIVED_FROM,
            source=source,
            target=target,
            producer=FIXED_PRODUCER,
            created_at=source.created_at,
        )
    assert exc.value.code in {"edge.job", "edge.namespace", "edge.matrix"}
    assert _SECRET not in str(exc.value)
    foreign = GraphEdge(
        id=EdgeId.derive(doc.namespace_id, doc.job_id, "DERIVED_FROM", source.id, target.id),
        edge_type=EdgeType.DERIVED_FROM,
        schema_version=EDGE_SCHEMA_VERSION,
        namespace_id=doc.namespace_id,
        job_id=doc.job_id,
        created_at=source.created_at,
        producer=FIXED_PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        provenance_refs=(),
        source_id=source.id,
        target_id=target.id,
    )
    mixed = replace(doc, nodes=(*doc.nodes, target), edges=(*doc.edges, foreign))
    codes = {f.code for f in validate_graph(mixed)}
    assert "graph.isolation" in codes


@given(ns_slug=_SLUG, job_key=_SLUG)
def test_namespace_and_job_combinations_are_stable(ns_slug: str, job_key: str) -> None:
    ns = NamespaceId.from_slug(ns_slug)
    job = JobId.derive(ns, job_key)
    assert JobId.derive(ns, job_key) == job
    other = JobId.derive(ns, job_key + "x" if len(job_key) < 8 else "altkey")
    assert other != job


@given(name=st.sampled_from(_BUILDER_NAMES), bogus=st.sampled_from(["g1.graph.v0", "g9.nope", ""]))
@settings(max_examples=15)
def test_unsupported_schema_versions_fail(name: str, bogus: str) -> None:
    doc = _doc(name)
    raw = doc.to_dict()
    raw["schema_version"] = bogus
    with pytest.raises(GraphContractError) as exc:
        load_graph(raw)
    assert exc.value.code in {"graph.schema", "graph.invalid"}
    assert _SECRET not in str(exc.value)
    if bogus != GRAPH_SCHEMA_VERSION:
        with pytest.raises(GraphContractError):
            loads_document(json.dumps(raw))


@given(attempt=st.integers(min_value=2, max_value=HARD_MAX_CORRECTIONS))
def test_correction_bounds_always_hold(attempt: int) -> None:
    doc = VALID_BUILDERS["unresolved_attribution"]()
    decision = next(n for n in doc.nodes if n.node_type.value == "AttributionDecision")
    finding = make_node(
        namespace=doc.namespace_id,
        job=doc.job_id,
        payload=ValidationFinding(
            code="insufficient_evidence",
            severity=FindingSeverity.ERROR,
            subject_id=decision.id,
            repair_category=RepairCategory.ATTRIBUTION,
            message="decision lacks supporting evidence",
        ),
        producer=FIXED_PRODUCER,
        created_at=doc.created_at,
        identity_parts={"code": "insufficient_evidence", "n": str(attempt)},
    )
    corr = make_node(
        namespace=doc.namespace_id,
        job=doc.job_id,
        payload=CorrectionAttempt(
            attempt_number=attempt,
            finding_id=finding.id,
            target_decision_id=decision.id,
            reason_code=ReasonCode.VALIDATION_FAILED,
        ),
        producer=FIXED_PRODUCER,
        created_at=doc.created_at,
        identity_parts={"attempt": str(attempt)},
    )
    extra = make_edge(
        edge_type=EdgeType.DERIVED_FROM,
        source=corr,
        target=finding,
        producer=FIXED_PRODUCER,
        created_at=doc.created_at,
    )
    bounded = replace(doc, nodes=(*doc.nodes, finding, corr), edges=(*doc.edges, extra))
    codes = {f.code for f in validate_graph(bounded)}
    assert "graph.correction_bound" in codes
    blob = " ".join(f.message for f in validate_graph(bounded))
    assert _SECRET not in blob


@given(name=st.sampled_from(_BUILDER_NAMES))
@settings(max_examples=12)
def test_raw_sensitive_input_is_absent_from_validation_messages(name: str) -> None:
    doc = _doc(name)
    raw = doc.to_dict()
    raw["metadata"] = {"note": _SECRET, "transcript": _SECRET}
    # Metadata is JSON-safe and does not become a finding message.
    loaded = EvidenceGraphDocument.from_dict_unvalidated(raw)
    blob = " ".join(f.message for f in validate_graph(loaded))
    assert _SECRET not in blob
    try:
        load_graph(raw)
    except GraphValidationError as exc:
        assert _SECRET not in str(exc)


@given(start=_US, width=st.integers(min_value=1, max_value=250_000))
def test_overlapping_integer_spans_are_explicit(start: int, width: int) -> None:
    left = TimeSpan(start, start + width * 2)
    right = TimeSpan(start + width, start + width * 3)
    assert left.end_us > right.start_us
    assert not left.contains(right)
    assert right.contains(TimeSpan(right.start_us, right.start_us + 1))


@given(state=st.sampled_from(tuple(DecisionState)))
def test_attribution_states_round_trip_on_payload(state: DecisionState) -> None:
    ns = NamespaceId.from_slug("synth.example")
    job = JobId.derive(ns, "job01")
    subject = NodeId.derive(ns, job, "SpeakerCluster", {"k": "s"})
    kwargs: dict[str, object] = {
        "state": state,
        "subject_id": subject,
        "reason_code": ReasonCode.INSUFFICIENT_EVIDENCE,
    }
    if state is DecisionState.ATTRIBUTED:
        kwargs["selected_candidate_id"] = NodeId.derive(ns, job, "CandidateIdentity", {"k": "c"})
        kwargs["reason_code"] = ReasonCode.OK
    if state is DecisionState.REQUIRES_REVIEW:
        kwargs["review_reason_code"] = ReasonCode.HUMAN_REQUIRED
        kwargs["reason_code"] = ReasonCode.HUMAN_REQUIRED
    if state is DecisionState.REJECTED:
        kwargs["reason_code"] = ReasonCode.REJECTED_BY_POLICY
    payload = AttributionDecision(**kwargs)  # type: ignore[arg-type]
    assert payload.state is state
