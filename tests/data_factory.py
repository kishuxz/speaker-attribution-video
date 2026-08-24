"""Shared synthetic builders for D1 contract tests. Not benchmark data."""

from __future__ import annotations

from datetime import UTC, datetime

from speaker_attribution_video.data.dataset import DatasetEntry
from speaker_attribution_video.data.enums import (
    AcquisitionMethod,
    DataSensitivity,
    DatasetSplit,
    IngestionState,
    MediaTypeStatus,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.ids import ArtifactId
from speaker_attribution_video.data.manifest import (
    MediaManifest,
    StreamMetadata,
    make_media_manifest,
)
from speaker_attribution_video.data.rights import RightsRecord, project_fixture_rights
from speaker_attribution_video.data.snapshot import SnapshotEntry
from speaker_attribution_video.data.source import SourceDescriptor, make_source
from speaker_attribution_video.data.versions import MANIFEST_SCHEMA_VERSION
from speaker_attribution_video.graph.ids import JobId, NamespaceId

FIXED = datetime(2026, 8, 24, 19, 0, 0, tzinfo=UTC)
HASH = "a" * 64
NS = NamespaceId.from_slug("synth.example")
JOB = JobId.derive(NS, "job01")


def synthetic_source(
    *,
    source_type: SourceType = SourceType.SYNTHETIC,
    provider: str = "project-fixtures",
    logical_ref: str = "artifact://synth.example/sources/tone-01",
    acquisition_method: AcquisitionMethod = AcquisitionMethod.GENERATED,
    acquired_at: datetime = FIXED,
    declared_owner: str | None = "project",
    provenance_notes: str | None = None,
    source_revision: str | None = "rev-01",
    source_checksum: str | None = HASH,
) -> SourceDescriptor:
    return make_source(
        source_type=source_type,
        provider=provider,
        logical_ref=logical_ref,
        acquisition_method=acquisition_method,
        acquired_at=acquired_at,
        declared_owner=declared_owner,
        provenance_notes=provenance_notes,
        source_revision=source_revision,
        source_checksum=source_checksum,
    )


def unverified_rights() -> RightsRecord:
    return RightsRecord(verification=RightsVerification.UNVERIFIED)


def synthetic_manifest(
    *,
    source: SourceDescriptor | None = None,
    rights: RightsRecord | None = None,
    sensitivity: DataSensitivity = DataSensitivity.SYNTHETIC,
    logical_filename: str = "synthetic-tone-01.wav",
    content_sha256: str = HASH,
    ingested_at: datetime = FIXED,
    media_type_status: MediaTypeStatus = MediaTypeStatus.DECLARED,
    media_type_declared: str | None = "audio/wav",
    media_type_detected: str | None = None,
    byte_size: int = 64,
    duration_us: int | None = 1_000_000,
    warnings: tuple[str, ...] = (),
    schema_version: str = MANIFEST_SCHEMA_VERSION,
    connector_name: str = "synthetic-fixture",
    connector_version: str = "0.1.0",
) -> MediaManifest:
    return make_media_manifest(
        namespace_id=NS,
        job_id=JOB,
        source=source if source is not None else synthetic_source(),
        rights=rights if rights is not None else project_fixture_rights(),
        sensitivity=sensitivity,
        logical_filename=logical_filename,
        media_type_status=media_type_status,
        media_type_declared=media_type_declared,
        media_type_detected=media_type_detected,
        byte_size=byte_size,
        content_sha256=content_sha256,
        ingested_at=ingested_at,
        connector_name=connector_name,
        connector_version=connector_version,
        configuration_fingerprint=HASH,
        schema_version=schema_version,
        duration_us=duration_us,
        audio_stream=StreamMetadata(sample_rate_hz=8000, channels=1, codec="pcm-s16le"),
        warnings=warnings,
    )


def synthetic_entry(
    *,
    content_sha256: str = HASH,
    logical_filename: str = "synthetic-tone-01.wav",
    split: DatasetSplit = DatasetSplit.DEMO,
    sensitivity: DataSensitivity = DataSensitivity.SYNTHETIC,
) -> DatasetEntry:
    return DatasetEntry(
        artifact_id=ArtifactId.from_digest(content_sha256),
        content_sha256=content_sha256,
        logical_filename=logical_filename,
        split=split,
        sensitivity=sensitivity,
        logical_ref="artifact://synth.example/sources/tone-01",
    )


def synthetic_snapshot_entry(
    *,
    content_sha256: str = HASH,
    logical_filename: str = "synthetic-tone-01.wav",
    state: IngestionState = IngestionState.ACCEPTED,
) -> SnapshotEntry:
    return SnapshotEntry(
        artifact_id=ArtifactId.from_digest(content_sha256),
        content_sha256=content_sha256,
        logical_filename=logical_filename,
        state=state,
    )
