"""Unit tests for D1 → G1 ingestion graph projection."""

from __future__ import annotations

import pytest

from data_factory import FIXED, JOB, NS, synthetic_manifest, synthetic_snapshot_entry
from speaker_attribution_video.data.enums import DataSensitivity, IngestionState, RightsVerification
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.graph import graph_from_accepted_ingestion
from speaker_attribution_video.data.rights import RightsRecord
from speaker_attribution_video.data.snapshot import make_ingestion_snapshot
from speaker_attribution_video.graph.enums import NodeType, Sensitivity
from speaker_attribution_video.graph.serialize import canonical_dumps_document

pytestmark = pytest.mark.unit


def _accepted_snapshot(manifest=None):
    manifest = manifest if manifest is not None else synthetic_manifest()
    snapshot = make_ingestion_snapshot(
        namespace_id=manifest.namespace_id,
        job_id=manifest.job_id,
        entries=(
            synthetic_snapshot_entry(
                content_sha256=manifest.content_sha256,
                logical_filename=manifest.logical_filename,
            ),
        ),
        connector_name=manifest.connector_name,
        connector_version=manifest.connector_version,
        created_at=FIXED,
    )
    return manifest, snapshot


def test_accepted_ingestion_projects_media_step_and_outputs() -> None:
    manifest, snapshot = _accepted_snapshot()
    graph = graph_from_accepted_ingestion(manifest=manifest, snapshot=snapshot, created_at=FIXED)
    types = {node.node_type for node in graph.nodes}
    assert NodeType.MEDIA_ARTIFACT in types
    assert NodeType.AUDIO_ARTIFACT in types
    assert NodeType.PROCESSING_STEP in types
    assert NodeType.OUTPUT_ARTIFACT in types
    assert NodeType.DIARIZATION_TURN not in types
    assert NodeType.SPEAKER_CLUSTER not in types
    assert NodeType.TRANSCRIPT_UTTERANCE not in types
    media = next(node for node in graph.nodes if node.node_type is NodeType.MEDIA_ARTIFACT)
    assert media.payload.content_hash == manifest.content_sha256
    assert graph.namespace_id == NS
    assert graph.job_id == JOB
    encoded = canonical_dumps_document(graph)
    assert "RIFF" not in encoded
    again = graph_from_accepted_ingestion(manifest=manifest, snapshot=snapshot, created_at=FIXED)
    assert canonical_dumps_document(again) == encoded


def test_partial_ingestion_does_not_project_success() -> None:
    manifest, _ = _accepted_snapshot()
    snapshot = make_ingestion_snapshot(
        namespace_id=NS,
        job_id=JOB,
        entries=(
            synthetic_snapshot_entry(),
            synthetic_snapshot_entry(
                content_sha256="b" * 64,
                logical_filename="synthetic-tone-02.wav",
                state=IngestionState.REJECTED,
            ),
        ),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED,
    )
    with pytest.raises(DataContractError) as exc:
        graph_from_accepted_ingestion(manifest=manifest, snapshot=snapshot, created_at=FIXED)
    assert exc.value.code == "graph.ingestion"


def test_sensitivity_is_preserved_without_downgrade() -> None:
    manifest = synthetic_manifest(
        sensitivity=DataSensitivity.BIOMETRIC_DATA,
        rights=RightsRecord(
            verification=RightsVerification.RESTRICTED,
            license_id="caller-attested",
            redistribution_permitted=False,
        ),
    )
    _, snapshot = _accepted_snapshot(manifest)
    graph = graph_from_accepted_ingestion(manifest=manifest, snapshot=snapshot, created_at=FIXED)
    assert graph.sensitivity is Sensitivity.RESTRICTED
    assert all(node.sensitivity is Sensitivity.RESTRICTED for node in graph.nodes)
    assert graph.sensitivity is not Sensitivity.PUBLIC
    assert "voiceprint" not in canonical_dumps_document(graph)
