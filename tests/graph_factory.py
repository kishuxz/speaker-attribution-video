"""Synthetic graph builders. Generic labels only; no show names or real dialogue."""

from __future__ import annotations

from datetime import datetime, timezone

from speaker_attribution_video.graph.document import EvidenceGraphDocument
from speaker_attribution_video.graph.edges import EdgeType, make_edge
from speaker_attribution_video.graph.enums import (
    DecisionState,
    EvidenceSummary,
    FindingSeverity,
    ProducerKind,
    ReasonCode,
    RepairCategory,
    ReviewOutcome,
    Sensitivity,
    TextMode,
)
from speaker_attribution_video.graph.ids import JobId, MediaId, NamespaceId, ReviewerId
from speaker_attribution_video.graph.nodes import (
    AttributionDecision,
    AudioArtifact,
    AudioEvidence,
    CandidateIdentity,
    CorrectionAttempt,
    DiarizationTurn,
    HumanReviewDecision,
    MediaArtifact,
    ProcessingStep,
    SpeakerCluster,
    ValidationFinding,
    make_node,
)
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.text import SensitiveText
from speaker_attribution_video.graph.time import TimeSpan
from speaker_attribution_video.graph.versions import GRAPH_SCHEMA_VERSION

FIXED = datetime(2026, 8, 24, 19, 0, 0, tzinfo=timezone.utc)
HASH = "e" * 64
NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")
PRODUCER = Producer(ProducerKind.TEST, "fixture.builder")


def _media_audio_step(job_key: str = "job01"):
    ns = NS
    job = JobId.derive(ns, job_key)
    uri = "artifact://synth.example/media/primary"
    media = make_node(
        namespace=ns,
        job=job,
        payload=MediaArtifact(
            content_hash=HASH,
            mime_type="audio/wav",
            uri=uri,
            display_name="synthetic-audio-01",
            media_id=MediaId.derive(ns, job, HASH, uri),
            duration_us=3_000_000,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": uri, "job": job.value},
    )
    audio = make_node(
        namespace=ns,
        job=job,
        payload=AudioArtifact(
            content_hash=HASH,
            uri="artifact://synth.example/audio/track",
            display_name="synthetic-track-01",
            duration_us=3_000_000,
            sample_rate_hz=16000,
            channels=1,
            mime_type="audio/wav",
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": "artifact://synth.example/audio/track", "job": job.value},
    )
    step = make_node(
        namespace=ns,
        job=job,
        payload=ProcessingStep(step_name="ingest", sequence_index=0),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"step": "ingest", "job": job.value},
    )
    edges = (
        make_edge(edge_type=EdgeType.EXTRACTED_FROM, source=audio, target=media, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.PRODUCED_BY, source=audio, target=step, producer=PRODUCER, created_at=FIXED),
    )
    return ns, job, media, audio, step, edges


def _document(ns, job, nodes, edges) -> EvidenceGraphDocument:
    return EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=ns,
        job_id=job,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={"fixture": "synthetic"},
        sensitivity=Sensitivity.INTERNAL,
        nodes=tuple(nodes),
        edges=tuple(edges),
    )


def one_speaker() -> EvidenceGraphDocument:
    ns, job, media, audio, step, base = _media_audio_step()
    cluster = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_00", display_label="speaker_a"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    turn = make_node(
        namespace=ns,
        job=job,
        payload=DiarizationTurn(span=TimeSpan(0, 1_500_000), cluster_key="speaker_00", confidence_bp=9000),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00", "span": "0-1500000"},
    )
    cand = make_node(
        namespace=ns,
        job=job,
        payload=CandidateIdentity(candidate_key="candidate_a", display_label="speaker_a"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"candidate_key": "candidate_a"},
    )
    evidence = make_node(
        namespace=ns,
        job=job,
        payload=AudioEvidence(summary=EvidenceSummary.CLUSTER_SUPPORT, score_bp=9000),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"summary": "cluster_support"},
    )
    decision = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.ATTRIBUTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.OK,
            selected_candidate_id=cand.id,
            confidence_bp=9000,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "ATTRIBUTED"},
    )
    extra = (
        make_edge(edge_type=EdgeType.DIARIZED_AS, source=turn, target=audio, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.ASSIGNED_TO, source=turn, target=cluster, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.CANDIDATE_FOR, source=cand, target=cluster, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.SUPPORTS, source=evidence, target=decision, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.DERIVED_FROM, source=decision, target=cluster, producer=PRODUCER, created_at=FIXED),
    )
    return _document(ns, job, (media, audio, step, cluster, turn, cand, evidence, decision), base + extra)


def two_anonymous_speakers() -> EvidenceGraphDocument:
    ns, job, media, audio, step, base = _media_audio_step()
    c0 = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    c1 = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_01"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_01"},
    )
    t0 = make_node(
        namespace=ns,
        job=job,
        payload=DiarizationTurn(span=TimeSpan(0, 1_000_000), cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00", "span": "0-1000000"},
    )
    t1 = make_node(
        namespace=ns,
        job=job,
        payload=DiarizationTurn(span=TimeSpan(1_200_000, 2_200_000), cluster_key="speaker_01"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_01", "span": "1200000-2200000"},
    )
    d0 = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.UNRESOLVED, subject_id=c0.id, reason_code=ReasonCode.INSUFFICIENT_EVIDENCE
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": c0.id.value, "state": "UNRESOLVED"},
    )
    d1 = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.UNRESOLVED, subject_id=c1.id, reason_code=ReasonCode.INSUFFICIENT_EVIDENCE
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": c1.id.value, "state": "UNRESOLVED"},
    )
    extra = (
        make_edge(edge_type=EdgeType.DIARIZED_AS, source=t0, target=audio, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.DIARIZED_AS, source=t1, target=audio, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.ASSIGNED_TO, source=t0, target=c0, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.ASSIGNED_TO, source=t1, target=c1, producer=PRODUCER, created_at=FIXED),
    )
    return _document(ns, job, (media, audio, step, c0, c1, t0, t1, d0, d1), base + extra)


def overlapping_turns() -> EvidenceGraphDocument:
    ns, job, media, audio, step, base = _media_audio_step()
    c0 = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    c1 = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_01"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_01"},
    )
    t0 = make_node(
        namespace=ns,
        job=job,
        payload=DiarizationTurn(span=TimeSpan(0, 2_000_000), cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00", "span": "0-2000000"},
    )
    t1 = make_node(
        namespace=ns,
        job=job,
        payload=DiarizationTurn(span=TimeSpan(1_000_000, 2_500_000), cluster_key="speaker_01"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_01", "span": "1000000-2500000"},
    )
    extra = (
        make_edge(edge_type=EdgeType.DIARIZED_AS, source=t0, target=audio, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.DIARIZED_AS, source=t1, target=audio, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.ASSIGNED_TO, source=t0, target=c0, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.ASSIGNED_TO, source=t1, target=c1, producer=PRODUCER, created_at=FIXED),
    )
    return _document(ns, job, (media, audio, step, c0, c1, t0, t1), base + extra)


def unresolved_attribution() -> EvidenceGraphDocument:
    ns, job, media, audio, step, base = _media_audio_step()
    cluster = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    decision = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.UNRESOLVED, subject_id=cluster.id, reason_code=ReasonCode.NO_CANDIDATE
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "UNRESOLVED"},
    )
    return _document(ns, job, (media, audio, step, cluster, decision), base)


def contradictory_evidence() -> EvidenceGraphDocument:
    ns, job, media, audio, step, base = _media_audio_step()
    cluster = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    e0 = make_node(
        namespace=ns,
        job=job,
        payload=AudioEvidence(summary=EvidenceSummary.CLUSTER_SUPPORT, score_bp=7000),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"summary": "cluster_support"},
    )
    e1 = make_node(
        namespace=ns,
        job=job,
        payload=AudioEvidence(summary=EvidenceSummary.VOICE_SIMILARITY, score_bp=2000),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"summary": "voice_similarity"},
    )
    decision = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.CONTRADICTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.CONFLICTING_EVIDENCE,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "CONTRADICTED"},
    )
    extra = (
        make_edge(edge_type=EdgeType.SUPPORTS, source=e0, target=decision, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.CONTRADICTS, source=e1, target=decision, producer=PRODUCER, created_at=FIXED),
    )
    return _document(ns, job, (media, audio, step, cluster, e0, e1, decision), base + extra)


def human_reviewed() -> EvidenceGraphDocument:
    ns, job, media, audio, step, base = _media_audio_step()
    cluster = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    cand = make_node(
        namespace=ns,
        job=job,
        payload=CandidateIdentity(candidate_key="candidate_a", display_label="speaker_a"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"candidate_key": "candidate_a"},
    )
    original = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.UNRESOLVED, subject_id=cluster.id, reason_code=ReasonCode.HUMAN_REQUIRED
        ),
        producer=Producer(ProducerKind.MODEL, "attribution.proposer"),
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "UNRESOLVED", "rev": "orig"},
    )
    replacement = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.REQUIRES_REVIEW,
            subject_id=cluster.id,
            reason_code=ReasonCode.REVIEW_OVERRIDE,
            review_reason_code=ReasonCode.HUMAN_REQUIRED,
        ),
        producer=Producer(ProducerKind.HUMAN, "reviewer.desk"),
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "REQUIRES_REVIEW", "rev": "new"},
    )
    review = make_node(
        namespace=ns,
        job=job,
        payload=HumanReviewDecision(
            reviewer_id=ReviewerId.from_slug("reviewer.desk"),
            target_decision_id=original.id,
            outcome=ReviewOutcome.OVERRIDE,
            replacement_decision_id=replacement.id,
            note_ref="artifact://synth.example/review/note-01",
        ),
        producer=Producer(ProducerKind.HUMAN, "reviewer.desk"),
        created_at=FIXED,
        identity_parts={"reviewer": "reviewer.desk"},
    )
    extra = (
        make_edge(edge_type=EdgeType.CANDIDATE_FOR, source=cand, target=cluster, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.REVIEWED_BY, source=original, target=review, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.DERIVED_FROM, source=replacement, target=original, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.DERIVED_FROM, source=review, target=original, producer=PRODUCER, created_at=FIXED),
    )
    return _document(ns, job, (media, audio, step, cluster, cand, original, replacement, review), base + extra)


def one_bounded_correction() -> EvidenceGraphDocument:
    ns, job, media, audio, step, base = _media_audio_step()
    cluster = make_node(
        namespace=ns,
        job=job,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    original = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.UNRESOLVED, subject_id=cluster.id, reason_code=ReasonCode.VALIDATION_FAILED
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "UNRESOLVED", "corr": "orig"},
    )
    finding = make_node(
        namespace=ns,
        job=job,
        payload=ValidationFinding(
            code="insufficient_evidence",
            severity=FindingSeverity.ERROR,
            subject_id=original.id,
            repair_category=RepairCategory.ATTRIBUTION,
            message="decision lacks supporting evidence",
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"code": "insufficient_evidence"},
    )
    result = make_node(
        namespace=ns,
        job=job,
        payload=AttributionDecision(
            state=DecisionState.REQUIRES_REVIEW,
            subject_id=cluster.id,
            reason_code=ReasonCode.RETRY_EXHAUSTED,
            review_reason_code=ReasonCode.RETRY_EXHAUSTED,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "REQUIRES_REVIEW", "corr": "new"},
    )
    attempt = make_node(
        namespace=ns,
        job=job,
        payload=CorrectionAttempt(
            attempt_number=1,
            finding_id=finding.id,
            target_decision_id=original.id,
            reason_code=ReasonCode.VALIDATION_FAILED,
            resulting_decision_id=result.id,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"attempt": "1"},
    )
    extra = (
        make_edge(edge_type=EdgeType.VALIDATES, source=finding, target=original, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.CORRECTED_BY, source=original, target=attempt, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.DERIVED_FROM, source=attempt, target=finding, producer=PRODUCER, created_at=FIXED),
        make_edge(edge_type=EdgeType.DERIVED_FROM, source=result, target=original, producer=PRODUCER, created_at=FIXED),
    )
    return _document(ns, job, (media, audio, step, cluster, original, finding, attempt, result), base + extra)


VALID_BUILDERS = {
    "one_speaker": one_speaker,
    "two_anonymous_speakers": two_anonymous_speakers,
    "overlapping_turns": overlapping_turns,
    "unresolved_attribution": unresolved_attribution,
    "contradictory_evidence": contradictory_evidence,
    "human_reviewed": human_reviewed,
    "one_bounded_correction": one_bounded_correction,
}
