"""Unit tests for dataset and ingestion-snapshot contracts."""

from __future__ import annotations

from datetime import timedelta

import pytest

from data_factory import (
    FIXED,
    JOB,
    NS,
    synthetic_entry,
    synthetic_snapshot_entry,
    synthetic_source,
)
from speaker_attribution_video.data.dataset import make_dataset_manifest
from speaker_attribution_video.data.enums import (
    DataSensitivity,
    DatasetSplit,
    IngestionFindingSeverity,
    IngestionState,
    IntendedUse,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.rights import RightsRecord, project_fixture_rights
from speaker_attribution_video.data.serialize import (
    assert_data_schema_drift_free,
    canonical_dumps_dataset,
    canonical_dumps_snapshot,
    loads_dataset,
    loads_snapshot,
)
from speaker_attribution_video.data.snapshot import (
    IngestionFinding,
    IngestionSnapshot,
    make_ingestion_snapshot,
)

pytestmark = pytest.mark.unit


def test_dataset_round_trip_and_external_reference() -> None:
    manifest = make_dataset_manifest(
        name="synth-demo",
        version="v1",
        source=synthetic_source(),
        rights=project_fixture_rights(),
        sensitivity=DataSensitivity.SYNTHETIC,
        entries=(synthetic_entry(),),
        split=DatasetSplit.DEMO,
        intended_use=IntendedUse.FIXTURE,
        created_at=FIXED,
        producer="test-builder",
        prohibited_uses=("training",),
    )
    restored = loads_dataset(canonical_dumps_dataset(manifest))
    assert restored == manifest
    assert restored.entries[0].logical_ref is not None
    encoded = canonical_dumps_dataset(manifest)
    assert "RIFF" not in encoded
    assert "/Users/" not in encoded


def test_duplicate_hashes_and_split_contamination_are_detected() -> None:
    with pytest.raises(DataContractError) as duplicate:
        make_dataset_manifest(
            name="synth-demo",
            version="v1",
            source=synthetic_source(),
            rights=project_fixture_rights(),
            sensitivity=DataSensitivity.SYNTHETIC,
            entries=(
                synthetic_entry(),
                synthetic_entry(logical_filename="synthetic-tone-02.wav"),
            ),
            split=DatasetSplit.DEMO,
            intended_use=IntendedUse.FIXTURE,
            created_at=FIXED,
            producer="test-builder",
        )
    assert duplicate.value.code == "dataset.duplicate_hash"
    with pytest.raises(DataContractError) as mixed:
        make_dataset_manifest(
            name="synth-train",
            version="v1",
            source=synthetic_source(),
            rights=project_fixture_rights(),
            sensitivity=DataSensitivity.SYNTHETIC,
            entries=(
                synthetic_entry(split=DatasetSplit.TRAIN),
                synthetic_entry(
                    content_sha256="b" * 64,
                    logical_filename="synthetic-tone-eval.wav",
                    split=DatasetSplit.TEST,
                ),
            ),
            split=DatasetSplit.UNASSIGNED,
            intended_use=IntendedUse.TRAINING,
            created_at=FIXED,
            producer="test-builder",
        )
    assert mixed.value.code == "dataset.split_contamination"
    with pytest.raises(DataContractError) as same_bytes:
        make_dataset_manifest(
            name="synth-mixed",
            version="v1",
            source=synthetic_source(),
            rights=project_fixture_rights(),
            sensitivity=DataSensitivity.SYNTHETIC,
            entries=(
                synthetic_entry(split=DatasetSplit.TRAIN, logical_filename="train-name.wav"),
                synthetic_entry(split=DatasetSplit.TEST, logical_filename="test-name.wav"),
            ),
            split=DatasetSplit.UNASSIGNED,
            intended_use=IntendedUse.UNSPECIFIED,
            created_at=FIXED,
            producer="test-builder",
        )
    assert same_bytes.value.code == "dataset.split_contamination"


def test_restricted_data_cannot_enter_public_or_synthetic_datasets() -> None:
    restricted = synthetic_source(
        source_type=SourceType.RESEARCH_RESTRICTED,
        logical_ref="artifact://restricted.example/sources/item-01",
        provider="research-archive",
    )
    with pytest.raises(DataContractError) as research:
        make_dataset_manifest(
            name="public-copy",
            version="v1",
            source=restricted,
            rights=RightsRecord(verification=RightsVerification.RESTRICTED, research_only=True),
            sensitivity=DataSensitivity.PUBLIC,
            entries=(synthetic_entry(sensitivity=DataSensitivity.RESTRICTED),),
            split=DatasetSplit.UNASSIGNED,
            intended_use=IntendedUse.UNSPECIFIED,
            created_at=FIXED,
            producer="test-builder",
        )
    assert research.value.code in {
        "dataset.research",
        "dataset.restricted",
        "dataset.research_only",
    }
    with pytest.raises(DataContractError) as copied:
        make_dataset_manifest(
            name="synth-demo",
            version="v1",
            source=synthetic_source(),
            rights=project_fixture_rights(),
            sensitivity=DataSensitivity.SYNTHETIC,
            entries=(synthetic_entry(sensitivity=DataSensitivity.RESTRICTED),),
            split=DatasetSplit.DEMO,
            intended_use=IntendedUse.FIXTURE,
            created_at=FIXED,
            producer="test-builder",
        )
    assert copied.value.code == "dataset.restricted"


def test_snapshot_partial_is_never_complete_success() -> None:
    accepted = make_ingestion_snapshot(
        namespace_id=NS,
        job_id=JOB,
        entries=(synthetic_snapshot_entry(),),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED,
    )
    assert accepted.state is IngestionState.ACCEPTED
    mixed = make_ingestion_snapshot(
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
        findings=(
            IngestionFinding(
                code="ingest-rejected",
                severity=IngestionFindingSeverity.ERROR,
                message="entry-failed-validation",
            ),
        ),
    )
    assert mixed.state is IngestionState.PARTIAL
    assert any(entry.state is IngestionState.REJECTED for entry in mixed.entries)
    with pytest.raises(DataContractError):
        IngestionSnapshot(
            snapshot_id=accepted.snapshot_id,
            namespace_id=NS,
            job_id=JOB,
            entries=mixed.entries,
            state=IngestionState.ACCEPTED,
            connector_name="synthetic-fixture",
            connector_version="0.1.0",
            created_at=FIXED,
        )


def test_snapshot_identity_is_stable_and_ignores_observation_time() -> None:
    first = make_ingestion_snapshot(
        namespace_id=NS,
        job_id=JOB,
        entries=(synthetic_snapshot_entry(),),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED,
    )
    later = make_ingestion_snapshot(
        namespace_id=NS,
        job_id=JOB,
        entries=(synthetic_snapshot_entry(),),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED + timedelta(minutes=1),
    )
    assert first.snapshot_id == later.snapshot_id
    assert first.identity_dict() == later.identity_dict()
    restored = loads_snapshot(canonical_dumps_snapshot(first))
    assert restored == first
    assert "file://" not in canonical_dumps_snapshot(first)


def test_failed_entries_remain_visible_and_schema_is_drift_free() -> None:
    snapshot = make_ingestion_snapshot(
        namespace_id=NS,
        job_id=JOB,
        entries=(synthetic_snapshot_entry(state=IngestionState.FAILED_POLICY),),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED,
    )
    assert snapshot.state is IngestionState.FAILED_POLICY
    assert snapshot.entries[0].state is IngestionState.FAILED_POLICY
    assert_data_schema_drift_free()
    with pytest.raises(DataContractError):
        IngestionFinding(
            code="path-escape",
            severity=IngestionFindingSeverity.ERROR,
            message="/Users/secret",
        )
