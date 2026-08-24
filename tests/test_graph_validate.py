from __future__ import annotations

from datetime import UTC, datetime

import pytest

from speaker_attribution_video.graph.document import DEFAULT_MAX_CORRECTIONS, EvidenceGraphDocument
from speaker_attribution_video.graph.edges import EdgeType, make_edge
from speaker_attribution_video.graph.enums import (
    DecisionState,
    FindingSeverity,
    ProducerKind,
    ReasonCode,
    RepairCategory,
    Sensitivity,
    TextMode,
)
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import JobId, MediaId, NamespaceId, NodeId
from speaker_attribution_video.graph.nodes import (
    AttributionDecision,
    AudioArtifact,
    AudioSegment,
    CorrectionAttempt,
    MediaArtifact,
    OutputArtifact,
    ProcessingStep,
    SpeakerCluster,
    TranscriptToken,
    TranscriptUtterance,
    ValidationFinding,
    make_node,
)
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.text import SensitiveText
from speaker_attribution_video.graph.time import TimeSpan
from speaker_attribution_video.graph.validate import (
    GraphValidationError,
    load_graph,
    validate_graph,
)
from speaker_attribution_video.graph.versions import GRAPH_SCHEMA_VERSION

FIXED = datetime(2026, 8, 24, 19, 0, 0, tzinfo=UTC)
HASH = "c" * 64
NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")
PRODUCER = Producer(ProducerKind.TEST, "fixture.builder")


def _doc(
    nodes, edges, *, max_correction_attempts: int = DEFAULT_MAX_CORRECTIONS
) -> EvidenceGraphDocument:
    return EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=tuple(nodes),
        edges=tuple(edges),
        max_correction_attempts=max_correction_attempts,
    )


def _base_nodes():
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
            duration_us=2_000_000,
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
            duration_us=2_000_000,
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
    extracted = make_edge(
        edge_type=EdgeType.EXTRACTED_FROM,
        source=audio,
        target=media,
        producer=PRODUCER,
        created_at=FIXED,
    )
    produced = make_edge(
        edge_type=EdgeType.PRODUCED_BY,
        source=audio,
        target=step,
        producer=PRODUCER,
        created_at=FIXED,
    )
    return media, audio, step, cluster, decision, extracted, produced


def test_valid_unresolved_graph() -> None:
    media, audio, step, cluster, decision, extracted, produced = _base_nodes()
    doc = _doc((media, audio, step, cluster, decision), (extracted, produced))
    assert validate_graph(doc) == ()
    loaded = load_graph(doc.to_dict())
    assert loaded.job_id == JOB


def test_missing_endpoint() -> None:
    media, audio, step, cluster, decision, extracted, produced = _base_nodes()
    ghost = NodeId.derive(NS, JOB, "MediaArtifact", {"ghost": "1"})
    bad = make_edge(
        edge_type=EdgeType.EXTRACTED_FROM,
        source=audio,
        target=media,
        producer=PRODUCER,
        created_at=FIXED,
    )
    object.__setattr__(bad, "target_id", ghost)
    doc = _doc((media, audio, step, cluster, decision), (extracted, produced, bad))
    codes = {f.code for f in validate_graph(doc)}
    assert "graph.endpoint" in codes


def test_derivation_cycle() -> None:
    media, audio, step, cluster, decision, extracted, produced = _base_nodes()
    # extracted is audio → media EXTRACTED_FROM.
    # matrix: Audio DERIVED_FROM Media only.
    # Cycle using NORMALIZED_FROM requires two audio nodes.
    audio2 = make_node(
        namespace=NS,
        job=JOB,
        payload=AudioArtifact(
            content_hash=HASH,
            uri="artifact://synth.example/audio/track-b",
            display_name="synthetic-track-02",
            duration_us=2_000_000,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": "artifact://synth.example/audio/track-b"},
    )
    e1 = make_edge(
        edge_type=EdgeType.NORMALIZED_FROM,
        source=audio,
        target=audio2,
        producer=PRODUCER,
        created_at=FIXED,
    )
    e2 = make_edge(
        edge_type=EdgeType.NORMALIZED_FROM,
        source=audio2,
        target=audio,
        producer=PRODUCER,
        created_at=FIXED,
    )
    doc = _doc((media, audio, audio2, step, cluster, decision), (extracted, produced, e1, e2))
    codes = {f.code for f in validate_graph(doc)}
    assert "graph.cycle" in codes


def test_token_outside_utterance() -> None:
    media, audio, step, cluster, decision, extracted, produced = _base_nodes()
    utt = make_node(
        namespace=NS,
        job=JOB,
        payload=TranscriptUtterance(
            span=TimeSpan(0, 100_000),
            text=SensitiveText(
                mode=TextMode.REDACTED, sensitivity=Sensitivity.SENSITIVE, redacted="[redacted]"
            ),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"span": "0-100000"},
    )
    token = make_node(
        namespace=NS,
        job=JOB,
        payload=TranscriptToken(
            utterance_id=utt.id,
            span=TimeSpan(0, 500_000),
            text=SensitiveText(
                mode=TextMode.REDACTED, sensitivity=Sensitivity.SENSITIVE, redacted="[redacted]"
            ),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"utt": utt.id.value, "span": "0-500000"},
    )
    aligned = make_edge(
        edge_type=EdgeType.ALIGNED_TO, source=token, target=utt, producer=PRODUCER, created_at=FIXED
    )
    doc = _doc((media, audio, step, cluster, decision, utt, token), (extracted, produced, aligned))
    codes = {f.code for f in validate_graph(doc)}
    assert "graph.token_bounds" in codes


def test_output_without_producer() -> None:
    media, audio, step, cluster, decision, extracted, produced = _base_nodes()
    output = make_node(
        namespace=NS,
        job=JOB,
        payload=OutputArtifact(
            artifact_kind="graph_json",
            uri="artifact://synth.example/output/graph",
            display_name="synthetic-output-01",
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"kind": "graph_json"},
    )
    doc = _doc((media, audio, step, cluster, decision, output), (extracted, produced))
    codes = {f.code for f in validate_graph(doc)}
    assert "graph.output_producer" in codes


def test_correction_beyond_limit_and_non_sequential() -> None:
    media, audio, step, cluster, decision, extracted, produced = _base_nodes()
    finding = make_node(
        namespace=NS,
        job=JOB,
        payload=ValidationFinding(
            code="insufficient_evidence",
            severity=FindingSeverity.ERROR,
            subject_id=decision.id,
            repair_category=RepairCategory.ATTRIBUTION,
            message="decision lacks supporting evidence",
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"code": "insufficient_evidence"},
    )
    attempt = make_node(
        namespace=NS,
        job=JOB,
        payload=CorrectionAttempt(
            attempt_number=2,
            finding_id=finding.id,
            target_decision_id=decision.id,
            reason_code=ReasonCode.VALIDATION_FAILED,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"attempt": "2"},
    )
    derived = make_edge(
        edge_type=EdgeType.DERIVED_FROM,
        source=attempt,
        target=finding,
        producer=PRODUCER,
        created_at=FIXED,
    )
    doc = _doc(
        (media, audio, step, cluster, decision, finding, attempt), (extracted, produced, derived)
    )
    codes = {f.code for f in validate_graph(doc)}
    assert "graph.correction_bound" in codes
    assert "graph.correction_sequence" in codes


def test_unsupported_schema_rejected_before_use() -> None:
    media, audio, step, cluster, decision, extracted, produced = _base_nodes()
    doc = _doc((media, audio, step, cluster, decision), (extracted, produced))
    raw = doc.to_dict()
    raw["schema_version"] = "g1.graph.v0"
    with pytest.raises(GraphContractError) as err:
        load_graph(raw)
    assert err.value.code in {"graph.schema", "graph.invalid"}


def test_validation_message_omits_embedded_text() -> None:
    media, audio, step, cluster, decision, extracted, produced = _base_nodes()
    secret = "secret-dialogue-must-not-leak"
    utt = make_node(
        namespace=NS,
        job=JOB,
        payload=TranscriptUtterance(
            span=TimeSpan(0, 100_000),
            text=SensitiveText(
                mode=TextMode.EMBEDDED,
                sensitivity=Sensitivity.SENSITIVE,
                embedded=secret,
            ),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"span": "0-100000", "mode": "embedded"},
    )
    token = make_node(
        namespace=NS,
        job=JOB,
        payload=TranscriptToken(
            utterance_id=utt.id,
            span=TimeSpan(0, 500_000),
            text=SensitiveText(
                mode=TextMode.EMBEDDED,
                sensitivity=Sensitivity.SENSITIVE,
                embedded=secret,
            ),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"utt": utt.id.value, "span": "wide"},
    )
    aligned = make_edge(
        edge_type=EdgeType.ALIGNED_TO, source=token, target=utt, producer=PRODUCER, created_at=FIXED
    )
    doc = _doc((media, audio, step, cluster, decision, utt, token), (extracted, produced, aligned))
    findings = validate_graph(doc)
    blob = " ".join(f.message for f in findings)
    assert secret not in blob
    with pytest.raises(GraphValidationError) as err:
        load_graph(doc.to_dict())
    assert secret not in str(err.value)


def test_segment_exceeds_duration() -> None:
    media, audio, step, cluster, decision, extracted, produced = _base_nodes()
    segment = make_node(
        namespace=NS,
        job=JOB,
        payload=AudioSegment(source_node_id=audio.id, span=TimeSpan(0, 9_000_000)),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"span": "too-long"},
    )
    seg_edge = make_edge(
        edge_type=EdgeType.SEGMENTED_FROM,
        source=segment,
        target=audio,
        producer=PRODUCER,
        created_at=FIXED,
    )
    doc = _doc((media, audio, step, cluster, decision, segment), (extracted, produced, seg_edge))
    codes = {f.code for f in validate_graph(doc)}
    assert "graph.timeline_bounds" in codes
