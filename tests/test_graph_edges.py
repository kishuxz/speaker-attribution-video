from __future__ import annotations

from datetime import datetime, timezone

import pytest

from speaker_attribution_video.graph.attribution import admit_attribution, view_attribution
from speaker_attribution_video.graph.edges import EdgeType, make_edge
from speaker_attribution_video.graph.enums import (
    DecisionState,
    EvidenceSummary,
    ProducerKind,
    ReasonCode,
    Sensitivity,
)
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import JobId, MediaId, NamespaceId
from speaker_attribution_video.graph.nodes import (
    AttributionDecision,
    AudioArtifact,
    AudioEvidence,
    CandidateIdentity,
    MediaArtifact,
    ProcessingStep,
    SpeakerCluster,
    make_node,
)
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.time import TimeSpan

FIXED = datetime(2026, 8, 24, 19, 0, 0, tzinfo=timezone.utc)
HASH = "b" * 64
NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")
JOB2 = JobId.derive(NS, "job02")
PRODUCER = Producer(ProducerKind.TEST, "fixture.builder")


def _media(job: JobId | None = None) -> object:
    job = job or JOB
    uri = "artifact://synth.example/media/primary"
    media_id = MediaId.derive(NS, job, HASH, uri)
    return make_node(
        namespace=NS,
        job=job,
        payload=MediaArtifact(
            content_hash=HASH,
            mime_type="audio/wav",
            uri=uri,
            display_name="synthetic-audio-01",
            media_id=media_id,
            duration_us=2_000_000,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": uri, "job": job.value},
    )


def _audio(job: JobId | None = None) -> object:
    job = job or JOB
    uri = "artifact://synth.example/audio/track"
    return make_node(
        namespace=NS,
        job=job,
        payload=AudioArtifact(
            content_hash=HASH,
            uri=uri,
            display_name="synthetic-track-01",
            duration_us=2_000_000,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": uri, "job": job.value},
    )


def test_extracted_from_is_allowed() -> None:
    edge = make_edge(
        edge_type=EdgeType.EXTRACTED_FROM,
        source=_audio(),
        target=_media(),
        producer=PRODUCER,
        created_at=FIXED,
    )
    assert edge.edge_type is EdgeType.EXTRACTED_FROM
    clone_id = make_edge(
        edge_type=EdgeType.EXTRACTED_FROM,
        source=_audio(),
        target=_media(),
        producer=PRODUCER,
        created_at=FIXED,
    ).id
    assert edge.id == clone_id


def test_invalid_matrix_rejected() -> None:
    with pytest.raises(GraphContractError) as err:
        make_edge(
            edge_type=EdgeType.SUPPORTS,
            source=_audio(),
            target=_media(),
            producer=PRODUCER,
            created_at=FIXED,
        )
    assert err.value.code == "edge.matrix"


def test_self_edge_rejected() -> None:
    media = _media()
    with pytest.raises(GraphContractError) as err:
        make_edge(
            edge_type=EdgeType.DERIVED_FROM,
            source=media,
            target=media,
            producer=PRODUCER,
            created_at=FIXED,
        )
    assert err.value.code == "edge.self"


def test_cross_job_rejected() -> None:
    with pytest.raises(GraphContractError) as err:
        make_edge(
            edge_type=EdgeType.EXTRACTED_FROM,
            source=_audio(JOB2),
            target=_media(JOB),
            producer=PRODUCER,
            created_at=FIXED,
        )
    assert err.value.code == "edge.job"


def test_no_generic_escape_hatch() -> None:
    assert not hasattr(EdgeType, "RELATED_TO")
    assert not hasattr(EdgeType, "GENERIC")


def test_attributed_requires_evidence_not_just_confidence() -> None:
    cluster = make_node(
        namespace=NS,
        job=JOB,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    cand = make_node(
        namespace=NS,
        job=JOB,
        payload=CandidateIdentity(candidate_key="candidate_a", display_label="speaker_a"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"candidate_key": "candidate_a"},
    )
    decision = make_node(
        namespace=NS,
        job=JOB,
        payload=AttributionDecision(
            state=DecisionState.ATTRIBUTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.OK,
            selected_candidate_id=cand.id,
            confidence_bp=10000,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "ATTRIBUTED"},
    )
    view = view_attribution(decision, nodes=(cluster, cand, decision), edges=())
    codes = {i.code for i in admit_attribution(view)}
    assert "attribution.evidence_required" in codes
    assert "attribution.confidence_not_admission" in codes


def test_attributed_with_support_is_admitted() -> None:
    cluster = make_node(
        namespace=NS,
        job=JOB,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    cand = make_node(
        namespace=NS,
        job=JOB,
        payload=CandidateIdentity(candidate_key="candidate_a", display_label="speaker_a"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"candidate_key": "candidate_a"},
    )
    evidence = make_node(
        namespace=NS,
        job=JOB,
        payload=AudioEvidence(summary=EvidenceSummary.CLUSTER_SUPPORT, score_bp=8000),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"summary": "cluster_support"},
    )
    decision = make_node(
        namespace=NS,
        job=JOB,
        payload=AttributionDecision(
            state=DecisionState.ATTRIBUTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.OK,
            selected_candidate_id=cand.id,
            confidence_bp=8000,
        ),
        producer=Producer(ProducerKind.MODEL, "attribution.proposer"),
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "ATTRIBUTED"},
    )
    support = make_edge(
        edge_type=EdgeType.SUPPORTS,
        source=evidence,
        target=decision,
        producer=PRODUCER,
        created_at=FIXED,
    )
    view = view_attribution(decision, nodes=(cluster, cand, evidence, decision), edges=(support,))
    assert admit_attribution(view) == ()


def test_contradicted_requires_contradiction_edge() -> None:
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
            state=DecisionState.CONTRADICTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.CONFLICTING_EVIDENCE,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "CONTRADICTED"},
    )
    view = view_attribution(decision, nodes=(cluster, decision), edges=())
    codes = {i.code for i in admit_attribution(view)}
    assert "attribution.contradiction_required" in codes


def test_candidate_outside_graph_is_rejected() -> None:
    other_ns = NamespaceId.from_slug("synth.other")
    other_job = JobId.derive(other_ns, "job01")
    foreign = make_node(
        namespace=other_ns,
        job=other_job,
        payload=CandidateIdentity(candidate_key="candidate_z", display_label="speaker_z"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"candidate_key": "candidate_z"},
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
            state=DecisionState.ATTRIBUTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.OK,
            selected_candidate_id=foreign.id,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "ATTRIBUTED", "foreign": "1"},
    )
    view = view_attribution(decision, nodes=(cluster, decision), edges=())
    codes = {i.code for i in admit_attribution(view)}
    assert "attribution.candidate_set" in codes


def test_human_review_is_distinct_node_type() -> None:
    assert "HumanReviewDecision" != "AttributionDecision"
    step = make_node(
        namespace=NS,
        job=JOB,
        payload=ProcessingStep(step_name="export", sequence_index=0),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"step": "export"},
    )
    with pytest.raises(GraphContractError) as err:
        make_edge(
            edge_type=EdgeType.REVIEWED_BY,
            source=step,
            target=step,
            producer=PRODUCER,
            created_at=FIXED,
        )
    assert err.value.code in {"edge.self", "edge.matrix"}
