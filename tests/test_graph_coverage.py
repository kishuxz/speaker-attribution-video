"""Focused unit tests for previously unexecuted G1 branches.

These tests exercise real contract code. They do not omit production modules
to inflate coverage numbers. Coverage remains evidence of execution only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from speaker_attribution_video.graph.attribution import (
    admit_attribution,
    require_admitted,
    view_attribution,
)
from speaker_attribution_video.graph.document import HARD_MAX_CORRECTIONS, EvidenceGraphDocument
from speaker_attribution_video.graph.edges import EdgeType, GraphEdge, make_edge, matrix_allows
from speaker_attribution_video.graph.enums import (
    DecisionState,
    DialogueKind,
    EvidenceSummary,
    FindingSeverity,
    ModelRole,
    NodeType,
    ProducerKind,
    ReasonCode,
    RepairCategory,
    ReviewOutcome,
    Sensitivity,
    TextMode,
    parse_enum,
)
from speaker_attribution_video.graph.errors import GraphContractError, redact_for_error
from speaker_attribution_video.graph.ids import (
    EdgeId,
    JobId,
    MediaId,
    ModelInvocationId,
    NamespaceId,
    NodeId,
    ReviewerId,
    parse_id,
    require_hex64,
    require_slug,
)
from speaker_attribution_video.graph.jsonutil import (
    as_json_object,
    canonical_dumps,
    require_json_object,
    require_json_value,
)
from speaker_attribution_video.graph.nodes import (
    AttributionDecision,
    AudioArtifact,
    AudioEvidence,
    AudioSegment,
    CandidateIdentity,
    CorrectionAttempt,
    DialogueEvidence,
    DiarizationTurn,
    GraphNode,
    HumanReviewDecision,
    MediaArtifact,
    ModelInvocation,
    OutputArtifact,
    ProcessingStep,
    SpeakerCluster,
    TranscriptToken,
    TranscriptUtterance,
    ValidationFinding,
    VisualEvidence,
    make_node,
    require_confidence_bp,
    require_int,
    require_mime,
)
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.serialize import (
    assert_schema_drift_free,
    canonical_dumps_document,
    load_json_schema,
    loads_document,
    python_enums_for_schema,
)
from speaker_attribution_video.graph.text import (
    SensitiveText,
    require_logical_uri,
    sha256_normalized_text,
)
from speaker_attribution_video.graph.time import (
    TimeSpan,
    format_utc,
    parse_utc,
    require_nonneg_int,
    require_utc,
    utc_now_for_tests,
)
from speaker_attribution_video.graph.validate import (
    GraphValidationError,
    load_graph,
    validate_graph,
)
from speaker_attribution_video.graph.versions import (
    EDGE_SCHEMA_VERSION,
    GRAPH_SCHEMA_VERSION,
    NODE_SCHEMA_VERSION,
)

FIXED = datetime(2026, 8, 24, 19, 0, 0, tzinfo=UTC)
HASH = "a" * 64
NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")
PRODUCER = Producer(ProducerKind.TEST, "coverage.builder")


def _media_audio():
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
            container="wav",
            byte_size=32,
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
            sample_rate_hz=16000,
            channels=1,
            mime_type="audio/wav",
            parent_media_id=MediaId.derive(NS, JOB, HASH, uri),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": "artifact://synth.example/audio/track"},
    )
    step = make_node(
        namespace=NS,
        job=JOB,
        payload=ProcessingStep(step_name="ingest", sequence_index=0, parameters={"mode": "synth"}),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"step": "ingest"},
    )
    return media, audio, step


def test_identifier_and_time_contract_errors() -> None:
    with pytest.raises(GraphContractError):
        require_slug(None, label="x")  # type: ignore[arg-type]
    with pytest.raises(GraphContractError):
        require_hex64("zz", label="h")
    with pytest.raises(GraphContractError):
        parse_id("g1.id.v1/only-two", expected_kind="namespace")
    with pytest.raises(GraphContractError):
        parse_id("g1.id.v1/job/not-a-hex", expected_kind="namespace")
    with pytest.raises(GraphContractError):
        MediaId.derive(NS, JOB, "nothex", "artifact://synth.example/x")
    inv = ModelInvocationId.derive(NS, JOB, "diarization", HASH)
    assert inv.value.startswith("g1.id.v1/model_invocation/")
    with pytest.raises(GraphContractError):
        require_utc(datetime(2026, 1, 1))
    assert utc_now_for_tests(FIXED) == FIXED.replace(tzinfo=UTC)
    assert utc_now_for_tests().tzinfo is UTC
    offset = timezone(timedelta(hours=1))
    converted = require_utc(datetime(2026, 8, 24, 20, 0, 0, tzinfo=offset))
    assert converted.tzinfo is UTC
    with pytest.raises(GraphContractError):
        parse_utc("not-a-timestamp")
    with pytest.raises(GraphContractError):
        parse_utc("2026-08-24T19:00:00.000000")
    with pytest.raises(GraphContractError):
        require_nonneg_int(True, code="x", label="n")  # type: ignore[arg-type]
    span = TimeSpan(0, 10)
    span.within_duration(None)
    assert (span == object()) is False
    assert hash(span) == hash((0, 10))
    with pytest.raises(GraphContractError):
        TimeSpan.from_dict({"start_us": 0.5, "end_us": 1})  # type: ignore[dict-item]
    assert redact_for_error("secret") == "<redacted>"


def test_json_and_text_contract_errors() -> None:
    with pytest.raises(GraphContractError):
        require_json_value({"a": {"b": {"c": {"d": {"e": 1}}}}}, max_depth=3)
    with pytest.raises(GraphContractError):
        require_json_value(10**19)
    with pytest.raises(GraphContractError):
        require_json_value(1.5)
    with pytest.raises(GraphContractError):
        require_json_value("x" * 3000)
    with pytest.raises(GraphContractError):
        require_json_value(list(range(65)))
    with pytest.raises(GraphContractError):
        require_json_value(object())
    with pytest.raises(GraphContractError):
        require_json_object(["nope"])
    with pytest.raises(GraphContractError):
        require_json_object({f"k{i:02d}": i for i in range(33)})
    with pytest.raises(GraphContractError):
        require_json_object({f"k{i:03d}": 1 for i in range(257)}, label="document")
    assert require_json_value(True) is True
    assert require_json_value(None) is None
    with pytest.raises(GraphContractError):
        require_json_object({"1bad": 1})
    with pytest.raises(GraphContractError):
        require_json_object({"": 1})
    assert as_json_object(None) == {}
    assert canonical_dumps({"b": 1, "a": 2}) == '{"a":2,"b":1}'
    with pytest.raises(GraphContractError):
        require_logical_uri("not a uri", label="u")
    hashed = SensitiveText(mode=TextMode.HASH, sensitivity=Sensitivity.SENSITIVE, sha256=HASH)
    assert hashed.safe_preview().startswith("sha256:")
    with pytest.raises(GraphContractError):
        SensitiveText(mode=TextMode.HASH, sensitivity=Sensitivity.SENSITIVE)
    with pytest.raises(GraphContractError):
        SensitiveText(
            mode=TextMode.HASH, sensitivity=Sensitivity.SENSITIVE, sha256=HASH, embedded="nope"
        )
    ref = SensitiveText(
        mode=TextMode.EXTERNAL_REF,
        sensitivity=Sensitivity.SENSITIVE,
        external_ref="artifact://synth.example/text/ref",
    )
    assert ref.safe_preview() == "external_ref"
    with pytest.raises(GraphContractError):
        SensitiveText(mode=TextMode.EXTERNAL_REF, sensitivity=Sensitivity.SENSITIVE)
    with pytest.raises(GraphContractError):
        SensitiveText(
            mode=TextMode.EXTERNAL_REF,
            sensitivity=Sensitivity.SENSITIVE,
            external_ref="artifact://x",
            embedded="nope",
        )
    with pytest.raises(GraphContractError):
        SensitiveText(mode=TextMode.REDACTED, sensitivity=Sensitivity.SENSITIVE, redacted="raw")
    with pytest.raises(GraphContractError):
        SensitiveText(
            mode=TextMode.REDACTED,
            sensitivity=Sensitivity.SENSITIVE,
            redacted="[redacted]",
            embedded="nope",
        )
    with pytest.raises(GraphContractError):
        SensitiveText(mode=TextMode.EMBEDDED, sensitivity=Sensitivity.SENSITIVE, embedded="  ")
    with pytest.raises(GraphContractError):
        SensitiveText(mode=TextMode.EMBEDDED, sensitivity=Sensitivity.PUBLIC, embedded="hi")
    with pytest.raises(GraphContractError):
        SensitiveText(
            mode=TextMode.EMBEDDED, sensitivity=Sensitivity.SENSITIVE, embedded="x" * 4097
        )
    embedded = SensitiveText(
        mode=TextMode.EMBEDDED, sensitivity=Sensitivity.SENSITIVE, embedded="ok"
    )
    assert embedded.sha256 == sha256_normalized_text("ok")
    assert embedded.safe_preview() == "<redacted>"
    assert (
        "[redacted]"
        in SensitiveText(
            mode=TextMode.REDACTED, sensitivity=Sensitivity.SENSITIVE, redacted="[redacted]note"
        ).safe_preview()
    )
    with pytest.raises(GraphContractError):
        SensitiveText.from_dict({"mode": "redacted", "sensitivity": "sensitive", "redacted": 1})


def test_payload_constructors_and_round_trips() -> None:
    with pytest.raises(GraphContractError):
        require_confidence_bp(None, required=True)
    with pytest.raises(GraphContractError):
        require_mime("bad")
    with pytest.raises(GraphContractError):
        AudioArtifact(content_hash=HASH, uri="artifact://x/a", display_name="n", sample_rate_hz=0)
    with pytest.raises(GraphContractError):
        AudioArtifact(content_hash=HASH, uri="artifact://x/a", display_name="n", channels=0)
    with pytest.raises(GraphContractError):
        AudioEvidence(summary="nope")  # type: ignore[arg-type]
    with pytest.raises(GraphContractError):
        VisualEvidence(summary=EvidenceSummary.VOICE_SIMILARITY)
    visual = VisualEvidence(
        summary=EvidenceSummary.FACE_COPRESENCE, score_bp=10, span=TimeSpan(0, 1)
    )
    dialogue = DialogueEvidence(
        kind=DialogueKind.MENTION,
        span=TimeSpan(0, 1),
        text=SensitiveText(mode=TextMode.HASH, sensitivity=Sensitivity.SENSITIVE, sha256=HASH),
    )
    with pytest.raises(GraphContractError):
        DialogueEvidence(kind="nope")  # type: ignore[arg-type]
    with pytest.raises(GraphContractError):
        DialogueEvidence(
            kind=DialogueKind.OTHER,
            text=SensitiveText(
                mode=TextMode.REDACTED, sensitivity=Sensitivity.PUBLIC, redacted="[redacted]"
            ),
        )
    with pytest.raises(GraphContractError):
        AttributionDecision(
            state="nope",  # type: ignore[arg-type]
            subject_id=NodeId.derive(NS, JOB, "SpeakerCluster", {"k": "s"}),
            reason_code=ReasonCode.OK,
        )
    with pytest.raises(GraphContractError):
        AttributionDecision(
            state=DecisionState.UNRESOLVED,
            subject_id=NodeId.derive(NS, JOB, "SpeakerCluster", {"k": "s"}),
            reason_code="nope",  # type: ignore[arg-type]
        )
    with pytest.raises(GraphContractError):
        AttributionDecision(
            state=DecisionState.REQUIRES_REVIEW,
            subject_id=NodeId.derive(NS, JOB, "SpeakerCluster", {"k": "s"}),
            reason_code=ReasonCode.HUMAN_REQUIRED,
        )
    with pytest.raises(GraphContractError):
        ValidationFinding(
            code="x",
            severity="nope",  # type: ignore[arg-type]
            subject_id=NodeId.derive(NS, JOB, "SpeakerCluster", {"k": "s"}),
            repair_category=RepairCategory.ATTRIBUTION,
            message="ok",
        )
    with pytest.raises(GraphContractError):
        ValidationFinding(
            code="x",
            severity=FindingSeverity.ERROR,
            subject_id=NodeId.derive(NS, JOB, "SpeakerCluster", {"k": "s"}),
            repair_category="nope",  # type: ignore[arg-type]
            message="ok",
        )
    with pytest.raises(GraphContractError):
        ValidationFinding(
            code="x",
            severity=FindingSeverity.ERROR,
            subject_id=NodeId.derive(NS, JOB, "SpeakerCluster", {"k": "s"}),
            repair_category=RepairCategory.ATTRIBUTION,
            message="too\nlong",
        )
    with pytest.raises(GraphContractError):
        CorrectionAttempt(
            attempt_number=0,
            finding_id=NodeId.derive(NS, JOB, "ValidationFinding", {"k": "f"}),
            target_decision_id=NodeId.derive(NS, JOB, "AttributionDecision", {"k": "d"}),
            reason_code=ReasonCode.VALIDATION_FAILED,
        )
    with pytest.raises(GraphContractError):
        CorrectionAttempt(
            attempt_number=1,
            finding_id=NodeId.derive(NS, JOB, "ValidationFinding", {"k": "f"}),
            target_decision_id=NodeId.derive(NS, JOB, "AttributionDecision", {"k": "d"}),
            reason_code="nope",  # type: ignore[arg-type]
        )
    with pytest.raises(GraphContractError):
        HumanReviewDecision(
            reviewer_id=ReviewerId.from_slug("reviewer.desk"),
            target_decision_id=NodeId.derive(NS, JOB, "AttributionDecision", {"k": "d"}),
            outcome="nope",  # type: ignore[arg-type]
        )
    with pytest.raises(GraphContractError):
        HumanReviewDecision(
            reviewer_id=ReviewerId.from_slug("reviewer.desk"),
            target_decision_id=NodeId.derive(NS, JOB, "AttributionDecision", {"k": "d"}),
            outcome=ReviewOutcome.OVERRIDE,
        )
    review = HumanReviewDecision(
        reviewer_id=ReviewerId.from_slug("reviewer.desk"),
        target_decision_id=NodeId.derive(NS, JOB, "AttributionDecision", {"k": "d"}),
        outcome=ReviewOutcome.UPHOLD,
        note_ref="artifact://synth.example/review/note",
    )
    inv = ModelInvocation(
        invocation_id=ModelInvocationId.derive(NS, JOB, "diarization", HASH),
        role=ModelRole.DIARIZATION,
        parameter_digest=HASH,
        logical_name="fake-diarizer",
    )
    output = OutputArtifact(
        artifact_kind="graph_json",
        uri="artifact://synth.example/out/g",
        display_name="synthetic-output-01",
        content_hash=HASH,
        media_type="application/json",
    )
    segment = AudioSegment(
        source_node_id=NodeId.derive(NS, JOB, "AudioArtifact", {"k": "a"}),
        span=TimeSpan(0, 1),
        channel_index=0,
    )
    utt = TranscriptUtterance(
        span=TimeSpan(0, 10),
        text=SensitiveText(mode=TextMode.HASH, sensitivity=Sensitivity.SENSITIVE, sha256=HASH),
        language_tag="en",
        confidence_bp=1,
    )
    with pytest.raises(GraphContractError):
        TranscriptUtterance(
            span=TimeSpan(0, 10),
            text=SensitiveText(
                mode=TextMode.REDACTED, sensitivity=Sensitivity.PUBLIC, redacted="[redacted]"
            ),
        )
    token = TranscriptToken(
        utterance_id=NodeId.derive(NS, JOB, "TranscriptUtterance", {"k": "u"}),
        span=TimeSpan(0, 1),
        text=SensitiveText(mode=TextMode.HASH, sensitivity=Sensitivity.SENSITIVE, sha256=HASH),
    )
    with pytest.raises(GraphContractError):
        TranscriptToken(
            utterance_id=token.utterance_id,
            span=TimeSpan(0, 1),
            text=SensitiveText(
                mode=TextMode.REDACTED, sensitivity=Sensitivity.PUBLIC, redacted="[redacted]"
            ),
        )
    nodes = [
        make_node(
            namespace=NS,
            job=JOB,
            payload=inv,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"role": "diarization"},
        ),
        make_node(
            namespace=NS,
            job=JOB,
            payload=output,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"kind": "graph_json"},
        ),
        make_node(
            namespace=NS,
            job=JOB,
            payload=visual,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"vis": "1"},
        ),
        make_node(
            namespace=NS,
            job=JOB,
            payload=dialogue,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"dlg": "1"},
            sensitivity=Sensitivity.SENSITIVE,
        ),
        make_node(
            namespace=NS,
            job=JOB,
            payload=segment,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"seg": "1"},
        ),
        make_node(
            namespace=NS,
            job=JOB,
            payload=utt,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"utt": "1"},
            sensitivity=Sensitivity.SENSITIVE,
        ),
        make_node(
            namespace=NS,
            job=JOB,
            payload=token,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"tok": "1"},
            sensitivity=Sensitivity.SENSITIVE,
        ),
        make_node(
            namespace=NS,
            job=JOB,
            payload=review,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"rev": "1"},
        ),
    ]
    for node in nodes:
        restored = GraphNode.from_dict(node.to_dict())
        assert restored.payload == node.payload
    with pytest.raises(GraphContractError):
        GraphNode.from_dict(
            {
                **nodes[0].to_dict(),
                "payload": {"logical_name": "missing-required-fields"},
            }
        )
    with pytest.raises(GraphContractError):
        GraphNode.from_dict({**nodes[0].to_dict(), "created_at": 1})
    with pytest.raises(GraphContractError):
        GraphNode.from_dict({**nodes[0].to_dict(), "provenance_refs": [1]})
    with pytest.raises(GraphContractError):
        GraphNode.from_dict({**nodes[0].to_dict(), "producer": "nope"})
    with pytest.raises(GraphContractError):
        require_int("x", label="n")
    parse_enum(DecisionState, DecisionState.UNRESOLVED, code="decision.state")
    with pytest.raises(GraphContractError):
        parse_enum(DecisionState, "NOPE", code="decision.state")
    with pytest.raises(GraphContractError):
        Producer(kind="nope", name="x")  # type: ignore[arg-type]
    with pytest.raises(GraphContractError):
        Producer.from_dict({"kind": "test"})


def test_node_post_init_and_edge_schema_errors() -> None:
    media, audio, step = _media_audio()
    with pytest.raises(GraphContractError):
        GraphNode(
            id=media.id,
            node_type=NodeType.MEDIA_ARTIFACT,
            schema_version="g1.node.v0",
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            provenance_refs=(),
            payload=media.payload,
        )
    with pytest.raises(GraphContractError):
        GraphNode(
            id=media.id,
            node_type=NodeType.AUDIO_ARTIFACT,
            schema_version=NODE_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            provenance_refs=(),
            payload=media.payload,
        )
    with pytest.raises(GraphContractError):
        GraphNode(
            id=media.id,
            node_type=NodeType.MEDIA_ARTIFACT,
            schema_version=NODE_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity="internal",  # type: ignore[arg-type]
            provenance_refs=(),
            payload=media.payload,
        )
    with pytest.raises(GraphContractError):
        GraphNode(
            id=media.id,
            node_type=NodeType.MEDIA_ARTIFACT,
            schema_version=NODE_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            provenance_refs=("not-an-id",),
            payload=media.payload,
        )
    utt_payload = TranscriptUtterance(
        span=TimeSpan(0, 10),
        text=SensitiveText(mode=TextMode.HASH, sensitivity=Sensitivity.SENSITIVE, sha256=HASH),
    )
    with pytest.raises(GraphContractError):
        make_node(
            namespace=NS,
            job=JOB,
            payload=utt_payload,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"utt": "sens"},
            sensitivity=Sensitivity.INTERNAL,
        )
    with pytest.raises(GraphContractError):
        GraphEdge(
            id=EdgeId.derive(NS, JOB, "EXTRACTED_FROM", audio.id, media.id),
            edge_type=EdgeType.EXTRACTED_FROM,
            schema_version="g1.edge.v0",
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            provenance_refs=(),
            source_id=audio.id,
            target_id=media.id,
        )
    with pytest.raises(GraphContractError):
        GraphEdge(
            id=EdgeId.derive(NS, JOB, "EXTRACTED_FROM", audio.id, media.id),
            edge_type="EXTRACTED_FROM",  # type: ignore[arg-type]
            schema_version=EDGE_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            provenance_refs=(),
            source_id=audio.id,
            target_id=media.id,
        )
    with pytest.raises(GraphContractError):
        GraphEdge(
            id=EdgeId.derive(NS, JOB, "EXTRACTED_FROM", audio.id, audio.id),
            edge_type=EdgeType.EXTRACTED_FROM,
            schema_version=EDGE_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            provenance_refs=(),
            source_id=audio.id,
            target_id=audio.id,
        )
    with pytest.raises(GraphContractError):
        GraphEdge(
            id=EdgeId.derive(NS, JOB, "EXTRACTED_FROM", audio.id, media.id),
            edge_type=EdgeType.EXTRACTED_FROM,
            schema_version=EDGE_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity="internal",  # type: ignore[arg-type]
            provenance_refs=(),
            source_id=audio.id,
            target_id=media.id,
        )
    edge = make_edge(
        edge_type=EdgeType.EXTRACTED_FROM,
        source=audio,
        target=media,
        producer=PRODUCER,
        created_at=FIXED,
    )
    with pytest.raises(GraphContractError):
        GraphEdge.from_dict({**edge.to_dict(), "created_at": 1})
    with pytest.raises(GraphContractError):
        GraphEdge.from_dict({**edge.to_dict(), "provenance_refs": [1]})
    assert (
        matrix_allows(EdgeType.EXTRACTED_FROM, NodeType.MEDIA_ARTIFACT, NodeType.AUDIO_ARTIFACT)
        is False
    )
    other_ns = NamespaceId.from_slug("other.example")
    other_job = JobId.derive(other_ns, "job99")
    foreign = make_node(
        namespace=other_ns,
        job=other_job,
        payload=media.payload,
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"foreign": "1", "job": other_job.value},
    )
    with pytest.raises(GraphContractError) as ns_err:
        make_edge(
            edge_type=EdgeType.EXTRACTED_FROM,
            source=audio,
            target=foreign,
            producer=PRODUCER,
            created_at=FIXED,
        )
    assert ns_err.value.code == "edge.namespace"
    del step


def test_document_parse_errors_and_validator_branches() -> None:
    media, audio, step = _media_audio()
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
        payload=AudioEvidence(summary=EvidenceSummary.CLUSTER_SUPPORT, score_bp=1),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"ev": "1"},
    )
    decision = make_node(
        namespace=NS,
        job=JOB,
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
    edges = (
        make_edge(
            edge_type=EdgeType.EXTRACTED_FROM,
            source=audio,
            target=media,
            producer=PRODUCER,
            created_at=FIXED,
        ),
        make_edge(
            edge_type=EdgeType.PRODUCED_BY,
            source=audio,
            target=step,
            producer=PRODUCER,
            created_at=FIXED,
        ),
        make_edge(
            edge_type=EdgeType.CANDIDATE_FOR,
            source=cand,
            target=cluster,
            producer=PRODUCER,
            created_at=FIXED,
        ),
        make_edge(
            edge_type=EdgeType.SUPPORTS,
            source=evidence,
            target=decision,
            producer=PRODUCER,
            created_at=FIXED,
        ),
        make_edge(
            edge_type=EdgeType.DERIVED_FROM,
            source=decision,
            target=cluster,
            producer=PRODUCER,
            created_at=FIXED,
        ),
    )
    doc = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, cluster, cand, evidence, decision),
        edges=edges,
    )
    assert doc.node_map()[media.id.value] is media
    assert validate_graph(doc) == ()
    require_admitted(view_attribution(decision, nodes=doc.nodes, edges=doc.edges))
    with pytest.raises(GraphContractError):
        view_attribution(media, nodes=doc.nodes, edges=doc.edges)
    with pytest.raises(GraphContractError):
        EvidenceGraphDocument(
            schema_version=GRAPH_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            nodes=(),
            edges=(),
            max_correction_attempts=True,  # type: ignore[arg-type]
        )
    with pytest.raises(GraphContractError):
        EvidenceGraphDocument(
            schema_version=GRAPH_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            nodes=(),
            edges=(),
            max_correction_attempts=HARD_MAX_CORRECTIONS + 1,
        )
    with pytest.raises(GraphContractError):
        EvidenceGraphDocument.from_dict_unvalidated({"schema_version": GRAPH_SCHEMA_VERSION})
    with pytest.raises(GraphContractError):
        EvidenceGraphDocument.from_dict_unvalidated(
            {**doc.to_dict(), "nodes": "nope", "edges": [], "created_at": format_utc(FIXED)}
        )
    with pytest.raises(GraphContractError):
        EvidenceGraphDocument.from_dict_unvalidated({**doc.to_dict(), "nodes": ["nope"]})
    with pytest.raises(GraphContractError):
        EvidenceGraphDocument.from_dict_unvalidated({**doc.to_dict(), "edges": ["nope"]})
    with pytest.raises(GraphContractError):
        EvidenceGraphDocument.from_dict_unvalidated(
            {**doc.to_dict(), "max_correction_attempts": "1"}
        )
    object.__setattr__(doc, "schema_version", "g1.graph.v0")
    assert any(f.code == "graph.schema" for f in validate_graph(doc))
    object.__setattr__(doc, "schema_version", GRAPH_SCHEMA_VERSION)

    other = make_node(
        namespace=NamespaceId.from_slug("other.example"),
        job=JobId.derive(NamespaceId.from_slug("other.example"), "job99"),
        payload=SpeakerCluster(cluster_key="speaker_99"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_99"},
    )
    isolated = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, cluster, cand, evidence, decision, other),
        edges=edges,
    )
    assert "graph.isolation" in {f.code for f in validate_graph(isolated)}
    dup_nodes = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, cluster, cand, evidence, decision, media),
        edges=edges,
    )
    assert "graph.duplicate_node" in {f.code for f in validate_graph(dup_nodes)}
    dup_edges = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=doc.nodes,
        edges=(*edges, edges[0]),
    )
    assert "graph.duplicate_edge" in {f.code for f in validate_graph(dup_edges)}
    ghost_edge = GraphEdge(
        id=EdgeId.derive(NS, JOB, "SUPPORTS", evidence.id, cluster.id),
        edge_type=EdgeType.SUPPORTS,
        schema_version=EDGE_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        provenance_refs=(),
        source_id=evidence.id,
        target_id=cluster.id,
    )
    matrix_doc = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=doc.nodes,
        edges=(*edges, ghost_edge),
    )
    codes = {f.code for f in validate_graph(matrix_doc)}
    assert "graph.matrix" in codes
    assert "graph.evidence_target" in codes


def test_timeline_attribution_correction_and_review_failures() -> None:
    media, audio, step = _media_audio()
    cluster = make_node(
        namespace=NS,
        job=JOB,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    base_edges = (
        make_edge(
            edge_type=EdgeType.EXTRACTED_FROM,
            source=audio,
            target=media,
            producer=PRODUCER,
            created_at=FIXED,
        ),
        make_edge(
            edge_type=EdgeType.PRODUCED_BY,
            source=audio,
            target=step,
            producer=PRODUCER,
            created_at=FIXED,
        ),
    )
    missing_src = make_node(
        namespace=NS,
        job=JOB,
        payload=AudioSegment(
            source_node_id=NodeId.derive(NS, JOB, "AudioArtifact", {"ghost": "1"}),
            span=TimeSpan(0, 1),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"seg": "missing"},
    )
    doc_missing = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, cluster, missing_src),
        edges=base_edges,
    )
    assert "graph.timeline_ref" in {f.code for f in validate_graph(doc_missing)}
    token = make_node(
        namespace=NS,
        job=JOB,
        payload=TranscriptToken(
            utterance_id=NodeId.derive(NS, JOB, "TranscriptUtterance", {"ghost": "u"}),
            span=TimeSpan(0, 1),
            text=SensitiveText(mode=TextMode.HASH, sensitivity=Sensitivity.SENSITIVE, sha256=HASH),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"tok": "missing"},
        sensitivity=Sensitivity.SENSITIVE,
    )
    doc_tok = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, cluster, token),
        edges=base_edges,
    )
    assert "graph.token_utterance" in {f.code for f in validate_graph(doc_tok)}
    segment = make_node(
        namespace=NS,
        job=JOB,
        payload=AudioSegment(source_node_id=audio.id, span=TimeSpan(0, 100_000)),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"seg": "ok"},
    )
    turn = make_node(
        namespace=NS,
        job=JOB,
        payload=DiarizationTurn(span=TimeSpan(0, 500_000), cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"turn": "wide"},
    )
    seg_edge = make_edge(
        edge_type=EdgeType.SEGMENTED_FROM,
        source=segment,
        target=audio,
        producer=PRODUCER,
        created_at=FIXED,
    )
    turn_edge = make_edge(
        edge_type=EdgeType.DIARIZED_AS,
        source=turn,
        target=segment,
        producer=PRODUCER,
        created_at=FIXED,
    )
    assigned = make_edge(
        edge_type=EdgeType.ASSIGNED_TO,
        source=turn,
        target=cluster,
        producer=PRODUCER,
        created_at=FIXED,
    )
    doc_turn = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, cluster, segment, turn),
        edges=(*base_edges, seg_edge, turn_edge, assigned),
    )
    assert "graph.turn_bounds" in {f.code for f in validate_graph(doc_turn)}
    long_turn = make_node(
        namespace=NS,
        job=JOB,
        payload=DiarizationTurn(span=TimeSpan(0, 9_000_000), cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"turn": "toolong"},
    )
    long_edge = make_edge(
        edge_type=EdgeType.DIARIZED_AS,
        source=long_turn,
        target=audio,
        producer=PRODUCER,
        created_at=FIXED,
    )
    doc_long = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, cluster, long_turn),
        edges=(*base_edges, long_edge),
    )
    assert "graph.turn_bounds" in {f.code for f in validate_graph(doc_long)}

    rejected = make_node(
        namespace=NS,
        job=JOB,
        payload=AttributionDecision(
            state=DecisionState.REJECTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.OK,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "REJECTED"},
    )
    contradicted = make_node(
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
    attributed_no_ev = make_node(
        namespace=NS,
        job=JOB,
        payload=AttributionDecision(
            state=DecisionState.ATTRIBUTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.OK,
            selected_candidate_id=NodeId.derive(NS, JOB, "CandidateIdentity", {"missing": "1"}),
            confidence_bp=9900,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "ATTR2"},
    )
    for node in (rejected, contradicted, attributed_no_ev):
        issues = admit_attribution(
            view_attribution(node, nodes=(media, audio, step, cluster, node), edges=base_edges)
        )
        assert issues
        with pytest.raises(GraphContractError):
            require_admitted(view_attribution(node, nodes=(cluster, node), edges=()))
    ghost_cand = NodeId.derive(NS, JOB, "CandidateIdentity", {"missing": "sel"})
    selected_unapproved = make_node(
        namespace=NS,
        job=JOB,
        payload=AttributionDecision(
            state=DecisionState.CONTRADICTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.CONFLICTING_EVIDENCE,
            selected_candidate_id=ghost_cand,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "CONTRA2"},
    )
    contra_ev = make_node(
        namespace=NS,
        job=JOB,
        payload=AudioEvidence(summary=EvidenceSummary.VOICE_SIMILARITY, score_bp=1),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"ev": "contra"},
    )
    contra_edge = make_edge(
        edge_type=EdgeType.CONTRADICTS,
        source=contra_ev,
        target=selected_unapproved,
        producer=PRODUCER,
        created_at=FIXED,
    )
    issues = admit_attribution(
        view_attribution(
            selected_unapproved,
            nodes=(cluster, contra_ev, selected_unapproved),
            edges=(contra_edge,),
        )
    )
    assert any(i.code == "attribution.candidate_set" for i in issues)

    finding = make_node(
        namespace=NS,
        job=JOB,
        payload=ValidationFinding(
            code="insufficient_evidence",
            severity=FindingSeverity.ERROR,
            subject_id=rejected.id,
            repair_category=RepairCategory.ATTRIBUTION,
            message="decision lacks supporting evidence",
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"code": "x"},
    )
    bad_target = make_node(
        namespace=NS,
        job=JOB,
        payload=CorrectionAttempt(
            attempt_number=1,
            finding_id=finding.id,
            target_decision_id=cluster.id,
            reason_code=ReasonCode.VALIDATION_FAILED,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"attempt": "bad-target"},
    )
    missing_finding = make_node(
        namespace=NS,
        job=JOB,
        payload=CorrectionAttempt(
            attempt_number=1,
            finding_id=NodeId.derive(NS, JOB, "ValidationFinding", {"ghost": "1"}),
            target_decision_id=rejected.id,
            reason_code=ReasonCode.VALIDATION_FAILED,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"attempt": "missing-finding"},
    )
    overwrite = make_node(
        namespace=NS,
        job=JOB,
        payload=CorrectionAttempt(
            attempt_number=1,
            finding_id=finding.id,
            target_decision_id=rejected.id,
            reason_code=ReasonCode.VALIDATION_FAILED,
            resulting_decision_id=rejected.id,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"attempt": "overwrite"},
    )
    missing_result = make_node(
        namespace=NS,
        job=JOB,
        payload=CorrectionAttempt(
            attempt_number=1,
            finding_id=finding.id,
            target_decision_id=rejected.id,
            reason_code=ReasonCode.VALIDATION_FAILED,
            resulting_decision_id=NodeId.derive(NS, JOB, "AttributionDecision", {"ghost": "r"}),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"attempt": "missing-result"},
    )
    for attempt in (bad_target, missing_finding, overwrite, missing_result):
        extra = (
            make_edge(
                edge_type=EdgeType.DERIVED_FROM,
                source=attempt,
                target=finding,
                producer=PRODUCER,
                created_at=FIXED,
            )
            if attempt is not missing_finding
            else make_edge(
                edge_type=EdgeType.CORRECTED_BY,
                source=rejected,
                target=attempt,
                producer=PRODUCER,
                created_at=FIXED,
            )
        )
        nodes = (media, audio, step, cluster, rejected, finding, attempt)
        if attempt is missing_finding:
            extra = make_edge(
                edge_type=EdgeType.CORRECTED_BY,
                source=rejected,
                target=attempt,
                producer=PRODUCER,
                created_at=FIXED,
            )
            nodes = (media, audio, step, cluster, rejected, attempt)
        doc = EvidenceGraphDocument(
            schema_version=GRAPH_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            nodes=nodes,
            edges=(*base_edges, extra),
        )
        assert any(f.code.startswith("graph.correction") for f in validate_graph(doc))

    other_job = JobId.derive(NS, "job02")
    foreign_decision = make_node(
        namespace=NS,
        job=other_job,
        payload=AttributionDecision(
            state=DecisionState.UNRESOLVED,
            subject_id=cluster.id,
            reason_code=ReasonCode.NO_CANDIDATE,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"subject": cluster.id.value, "state": "UNRESOLVED", "job": other_job.value},
    )
    # Correction targeting a missing decision id (other job node not in document).
    cross = make_node(
        namespace=NS,
        job=JOB,
        payload=CorrectionAttempt(
            attempt_number=1,
            finding_id=finding.id,
            target_decision_id=foreign_decision.id,
            reason_code=ReasonCode.VALIDATION_FAILED,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"attempt": "cross"},
    )
    doc_cross = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, cluster, rejected, finding, cross),
        edges=(
            *base_edges,
            make_edge(
                edge_type=EdgeType.DERIVED_FROM,
                source=cross,
                target=finding,
                producer=PRODUCER,
                created_at=FIXED,
            ),
        ),
    )
    assert "graph.correction_job" in {f.code for f in validate_graph(doc_cross)}

    review_missing = make_node(
        namespace=NS,
        job=JOB,
        payload=HumanReviewDecision(
            reviewer_id=ReviewerId.from_slug("reviewer.desk"),
            target_decision_id=NodeId.derive(NS, JOB, "AttributionDecision", {"ghost": "d"}),
            outcome=ReviewOutcome.UPHOLD,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"rev": "missing"},
    )
    review_over = make_node(
        namespace=NS,
        job=JOB,
        payload=HumanReviewDecision(
            reviewer_id=ReviewerId.from_slug("reviewer.desk"),
            target_decision_id=rejected.id,
            outcome=ReviewOutcome.OVERRIDE,
            replacement_decision_id=rejected.id,
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"rev": "over"},
    )
    review_gone = make_node(
        namespace=NS,
        job=JOB,
        payload=HumanReviewDecision(
            reviewer_id=ReviewerId.from_slug("reviewer.desk"),
            target_decision_id=rejected.id,
            outcome=ReviewOutcome.OVERRIDE,
            replacement_decision_id=NodeId.derive(NS, JOB, "AttributionDecision", {"ghost": "r"}),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"rev": "gone"},
    )
    for review in (review_missing, review_over, review_gone):
        extra = (
            make_edge(
                edge_type=EdgeType.REVIEWED_BY,
                source=rejected,
                target=review,
                producer=PRODUCER,
                created_at=FIXED,
            )
            if review is not review_missing
            else None
        )
        nodes = (media, audio, step, cluster, rejected, review)
        edges = base_edges if extra is None else (*base_edges, extra)
        doc = EvidenceGraphDocument(
            schema_version=GRAPH_SCHEMA_VERSION,
            namespace_id=NS,
            job_id=JOB,
            created_at=FIXED,
            producer=PRODUCER,
            metadata={},
            sensitivity=Sensitivity.INTERNAL,
            nodes=nodes,
            edges=edges,
        )
        assert any(f.code.startswith("graph.review") for f in validate_graph(doc))


def test_serialize_error_paths() -> None:
    with pytest.raises(GraphContractError):
        loads_document("{")
    with pytest.raises(GraphContractError):
        loads_document("[]")
    schema = load_json_schema()
    assert isinstance(schema, dict)
    enums = python_enums_for_schema()
    assert enums["schema_version"] == GRAPH_SCHEMA_VERSION
    assert_schema_drift_free()
    media, audio, step = _media_audio()
    doc = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step),
        edges=(
            make_edge(
                edge_type=EdgeType.EXTRACTED_FROM,
                source=audio,
                target=media,
                producer=PRODUCER,
                created_at=FIXED,
            ),
            make_edge(
                edge_type=EdgeType.PRODUCED_BY,
                source=audio,
                target=step,
                producer=PRODUCER,
                created_at=FIXED,
            ),
        ),
    )
    canonical_dumps_document(doc)
    with pytest.raises(GraphContractError):
        load_graph({"schema_version": GRAPH_SCHEMA_VERSION, "nodes": [], "edges": []})
    isolated = EvidenceGraphDocument(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace_id=NS,
        job_id=JOB,
        created_at=FIXED,
        producer=PRODUCER,
        metadata={},
        sensitivity=Sensitivity.INTERNAL,
        nodes=(media, audio, step, media),
        edges=(),
    )
    with pytest.raises(GraphValidationError):
        canonical_dumps_document(isolated)


def test_serialize_schema_guards(monkeypatch, tmp_path) -> None:
    from speaker_attribution_video.graph import serialize as ser

    path = tmp_path / "schema.json"
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(ser, "SCHEMA_PATH", path)
    with pytest.raises(GraphContractError):
        ser.load_json_schema()
    path.write_text('{"$defs": "nope"}', encoding="utf-8")
    with pytest.raises(GraphContractError) as missing_defs:
        ser.assert_schema_drift_free()
    assert missing_defs.value.code == "schema.defs"
    path.write_text(
        '{"$defs": {"NodeType": {"enum": []},'
        ' "EdgeType": {"enum": []}, "DecisionState": {"enum": []}}}',
        encoding="utf-8",
    )
    with pytest.raises(GraphContractError) as drift:
        ser.assert_schema_drift_free()
    assert drift.value.code == "schema.drift"
    path.write_text(
        '{"$defs": {"NodeType": {"enum": '
        + str(python_enums_for_schema()["node_types"]).replace("'", '"')
        + '}, "EdgeType": {"enum": '
        + str(python_enums_for_schema()["edge_types"]).replace("'", '"')
        + '}, "DecisionState": {"enum": '
        + str(python_enums_for_schema()["decision_states"]).replace("'", '"')
        + "}}}",
        encoding="utf-8",
    )
    with pytest.raises(GraphContractError) as props:
        ser.assert_schema_drift_free()
    assert props.value.code == "schema.drift"
