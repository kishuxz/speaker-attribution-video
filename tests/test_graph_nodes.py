from __future__ import annotations

from datetime import datetime, timezone

import pytest

from speaker_attribution_video.graph.enums import ProducerKind, Sensitivity, TextMode
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import JobId, NamespaceId, NodeId
from speaker_attribution_video.graph.nodes import (
    AudioArtifact,
    AttributionDecision,
    CandidateIdentity,
    DiarizationTurn,
    GraphNode,
    MediaArtifact,
    ProcessingStep,
    SpeakerCluster,
    TranscriptToken,
    TranscriptUtterance,
    make_node,
)
from speaker_attribution_video.graph.ids import MediaId
from speaker_attribution_video.graph.enums import DecisionState, ReasonCode
from speaker_attribution_video.graph.producer import Producer
from speaker_attribution_video.graph.text import SensitiveText
from speaker_attribution_video.graph.time import TimeSpan
from speaker_attribution_video.graph.versions import ID_SCHEMA_VERSION, NODE_SCHEMA_VERSION

FIXED = datetime(2026, 8, 24, 19, 0, 0, tzinfo=timezone.utc)
HASH = "a" * 64
NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")
PRODUCER = Producer(ProducerKind.TEST, "fixture.builder")


def _media() -> GraphNode:
    media_id = MediaId.derive(NS, JOB, HASH, "artifact://synth.example/media/primary")
    payload = MediaArtifact(
        content_hash=HASH,
        mime_type="audio/wav",
        uri="artifact://synth.example/media/primary",
        display_name="synthetic-audio-01",
        media_id=media_id,
        duration_us=2_000_000,
        container="wav",
    )
    return make_node(
        namespace=NS,
        job=JOB,
        payload=payload,
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": "artifact://synth.example/media/primary"},
    )


def test_namespace_and_job_are_deterministic() -> None:
    assert NamespaceId.from_slug("synth.example") == NS
    assert JobId.derive(NS, "job01") == JOB
    assert JOB.value.startswith(f"{ID_SCHEMA_VERSION}/job/")


def test_distinct_id_types_are_not_equal() -> None:
    node = NodeId.derive(NS, JOB, "MediaArtifact", {"k": "v"})
    assert NS != JOB  # type: ignore[comparison-overlap]
    assert node.value != JOB.value
    assert type(NS) is not type(JOB)


def test_blank_and_unsupported_ids_are_rejected() -> None:
    with pytest.raises(GraphContractError) as blank:
        NamespaceId("")
    assert blank.value.code == "id.blank"
    with pytest.raises(GraphContractError) as ver:
        NamespaceId("g1.id.v0/namespace/synth.example")
    assert ver.value.code == "id.schema"


def test_media_node_roundtrip_dict() -> None:
    node = _media()
    assert node.schema_version == NODE_SCHEMA_VERSION
    clone = GraphNode.from_dict(node.to_dict())
    assert clone.id == node.id
    assert clone.to_dict() == node.to_dict()


def test_ids_do_not_use_raw_transcript_text() -> None:
    text = SensitiveText(mode=TextMode.HASH, sensitivity=Sensitivity.SENSITIVE, sha256=HASH)
    utterance = TranscriptUtterance(span=TimeSpan(0, 500_000), text=text)
    node = make_node(
        namespace=NS,
        job=JOB,
        payload=utterance,
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"span": "0-500000", "text_sha256": HASH},
    )
    assert "hello" not in node.id.value
    assert HASH in str(node.to_dict())


def test_embedded_text_not_in_contract_error() -> None:
    secret = "private-dialogue-must-not-leak"
    with pytest.raises(GraphContractError) as err:
        SensitiveText(
            mode=TextMode.EMBEDDED,
            sensitivity=Sensitivity.PUBLIC,
            embedded=secret,
        )
    assert secret not in str(err.value)
    assert err.value.code == "text.sensitivity"


def test_timespan_rejects_float_and_order() -> None:
    with pytest.raises(GraphContractError):
        TimeSpan(-1, 10)
    with pytest.raises(GraphContractError):
        TimeSpan(10, 10)


def test_overlapping_turns_are_representable() -> None:
    a = DiarizationTurn(span=TimeSpan(0, 1_000_000), cluster_key="speaker_00")
    b = DiarizationTurn(span=TimeSpan(500_000, 1_500_000), cluster_key="speaker_01")
    assert a.span.end_us > b.span.start_us


def test_confidence_range() -> None:
    with pytest.raises(GraphContractError) as err:
        DiarizationTurn(span=TimeSpan(0, 10), cluster_key="speaker_00", confidence_bp=10001)
    assert err.value.code == "confidence.range"


def test_metadata_rejects_float_and_objects() -> None:
    payload = ProcessingStep(step_name="ingest", sequence_index=0)
    with pytest.raises(GraphContractError) as err:
        make_node(
            namespace=NS,
            job=JOB,
            payload=payload,
            producer=PRODUCER,
            created_at=FIXED,
            identity_parts={"step": "ingest"},
            metadata={"score": 1.5},  # type: ignore[dict-item]
        )
    assert err.value.code == "json.float_forbidden"


def test_unresolved_cannot_hold_identity() -> None:
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
    with pytest.raises(GraphContractError) as err:
        AttributionDecision(
            state=DecisionState.UNRESOLVED,
            subject_id=cluster.id,
            reason_code=ReasonCode.INSUFFICIENT_EVIDENCE,
            selected_candidate_id=cand.id,
        )
    assert err.value.code == "decision.unresolved"


def test_attributed_requires_candidate() -> None:
    cluster = make_node(
        namespace=NS,
        job=JOB,
        payload=SpeakerCluster(cluster_key="speaker_00"),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"cluster_key": "speaker_00"},
    )
    with pytest.raises(GraphContractError) as err:
        AttributionDecision(
            state=DecisionState.ATTRIBUTED,
            subject_id=cluster.id,
            reason_code=ReasonCode.OK,
        )
    assert err.value.code == "decision.attributed"


def test_token_identity_uses_utterance_id_not_raw_text() -> None:
    utt = make_node(
        namespace=NS,
        job=JOB,
        payload=TranscriptUtterance(
            span=TimeSpan(0, 200_000),
            text=SensitiveText(mode=TextMode.REDACTED, sensitivity=Sensitivity.SENSITIVE, redacted="[redacted]"),
        ),
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"span": "0-200000", "text_mode": "redacted"},
    )
    token = TranscriptToken(
        utterance_id=utt.id,
        span=TimeSpan(0, 100_000),
        text=SensitiveText(mode=TextMode.REDACTED, sensitivity=Sensitivity.SENSITIVE, redacted="[redacted]"),
    )
    node = make_node(
        namespace=NS,
        job=JOB,
        payload=token,
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"utterance_id": utt.id.value, "span": "0-100000"},
    )
    assert node.payload.utterance_id == utt.id  # type: ignore[union-attr]


def test_audio_artifact_does_not_require_bytes() -> None:
    payload = AudioArtifact(
        content_hash=HASH,
        uri="artifact://synth.example/audio/track",
        display_name="synthetic-track-01",
        duration_us=2_000_000,
        sample_rate_hz=16000,
        channels=1,
        mime_type="audio/wav",
    )
    node = make_node(
        namespace=NS,
        job=JOB,
        payload=payload,
        producer=PRODUCER,
        created_at=FIXED,
        identity_parts={"content_hash": HASH, "uri": payload.uri},
    )
    assert "bytes" not in node.to_dict()["payload"]
