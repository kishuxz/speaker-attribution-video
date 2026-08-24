"""Unit tests for the immutable MediaManifest contract."""

from __future__ import annotations

from datetime import timedelta

import pytest

from data_factory import (
    FIXED,
    HASH,
    JOB,
    NS,
    synthetic_manifest,
    synthetic_source,
    unverified_rights,
)
from speaker_attribution_video.data.enums import (
    AcquisitionMethod,
    DataSensitivity,
    MediaTypeStatus,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.manifest import (
    MediaManifest,
    StreamMetadata,
    make_media_manifest,
)
from speaker_attribution_video.data.rights import RightsRecord, project_fixture_rights
from speaker_attribution_video.data.serialize import (
    assert_manifest_schema_drift_free,
    canonical_bytes,
    canonical_dumps_manifest,
    load_json_schema,
    loads_manifest,
)
from speaker_attribution_video.graph.errors import GraphContractError

pytestmark = pytest.mark.unit


def test_equivalent_manifests_serialize_byte_identically() -> None:
    first = synthetic_manifest()
    second = synthetic_manifest()
    assert canonical_bytes(first) == canonical_bytes(second)
    restored = loads_manifest(canonical_dumps_manifest(first))
    assert restored == first
    assert restored.to_dict() == first.to_dict()


def test_content_identity_changes_with_bytes_not_display_label() -> None:
    base = synthetic_manifest()
    relabeled = synthetic_manifest(logical_filename="synthetic-tone-relabel.wav")
    other_bytes = synthetic_manifest(content_sha256="b" * 64)
    assert base.artifact_id == relabeled.artifact_id
    assert base.manifest_id != relabeled.manifest_id
    assert other_bytes.artifact_id != base.artifact_id
    assert other_bytes.manifest_id != base.manifest_id


def test_observation_time_does_not_change_manifest_identity() -> None:
    first = synthetic_manifest(ingested_at=FIXED)
    later = synthetic_manifest(ingested_at=FIXED + timedelta(minutes=1))
    assert first.manifest_id == later.manifest_id
    assert first.artifact_id == later.artifact_id
    assert first.ingestion_event_id != later.ingestion_event_id
    assert first.identity_dict() == later.identity_dict()
    assert canonical_dumps_manifest(first) != canonical_dumps_manifest(later)


def test_warnings_are_not_identity_and_must_not_include_paths() -> None:
    quiet = synthetic_manifest()
    warned = synthetic_manifest(warnings=("checksum-mismatch-retry",))
    assert quiet.manifest_id == warned.manifest_id
    with pytest.raises(DataContractError) as exc:
        synthetic_manifest(warnings=("/Users/example/secret.wav",))
    assert "secret.wav" not in str(exc.value)
    assert "/Users" not in str(exc.value)


def test_absolute_paths_and_file_bytes_are_not_serialized() -> None:
    payload = synthetic_manifest().to_dict()
    encoded = canonical_dumps_manifest(synthetic_manifest())
    assert "file://" not in encoded
    assert "/Users/" not in encoded
    assert "/home/" not in encoded
    assert b"RIFF" not in encoded.encode("utf-8")
    assert "content_sha256" in payload
    assert payload["redaction"] == "contents_excluded"


def test_negative_size_and_duration_are_rejected() -> None:
    with pytest.raises(GraphContractError) as size:
        synthetic_manifest(byte_size=-1)
    assert size.value.code == "manifest.size"
    with pytest.raises(GraphContractError) as duration:
        synthetic_manifest(duration_us=-5)
    assert duration.value.code == "manifest.duration"


def test_malformed_hash_and_unsupported_schema_are_rejected() -> None:
    with pytest.raises(GraphContractError) as digest:
        synthetic_manifest(content_sha256="zz")
    assert digest.value.code == "hash.sha256"
    with pytest.raises(DataContractError) as schema:
        synthetic_manifest(schema_version="d1.manifest.v0")
    assert schema.value.code == "manifest.schema"
    with pytest.raises(DataContractError):
        loads_manifest('{"schema_version":"d1.manifest.v0"}')


def test_declared_and_detected_media_types_are_labeled() -> None:
    declared = synthetic_manifest(
        media_type_status=MediaTypeStatus.DECLARED,
        media_type_declared="audio/wav",
    )
    detected = synthetic_manifest(
        media_type_status=MediaTypeStatus.DETECTED,
        media_type_declared=None,
        media_type_detected="audio/wav",
    )
    unknown = synthetic_manifest(
        media_type_status=MediaTypeStatus.UNKNOWN,
        media_type_declared=None,
    )
    assert declared.to_dict()["media_type_status"] == "declared"
    assert detected.to_dict()["media_type_status"] == "detected"
    assert unknown.to_dict()["media_type_status"] == "unknown"
    with pytest.raises(DataContractError):
        synthetic_manifest(media_type_status=MediaTypeStatus.DECLARED, media_type_declared=None)


def test_prohibited_and_unknown_redistribution_fail_closed() -> None:
    with pytest.raises(DataContractError) as prohibited:
        synthetic_manifest(rights=RightsRecord(verification=RightsVerification.PROHIBITED))
    assert prohibited.value.code == "manifest.prohibited"
    with pytest.raises(DataContractError) as unknown:
        synthetic_manifest(
            rights=RightsRecord(
                verification=RightsVerification.VERIFIED,
                license_id="apache-2.0",
                redistribution_permitted=True,
            ),
            sensitivity=DataSensitivity.UNKNOWN,
        )
    assert unknown.value.code == "sensitivity.ambiguous"


def test_research_restricted_cannot_be_public_or_synthetic() -> None:
    restricted = synthetic_source(
        source_type=SourceType.RESEARCH_RESTRICTED,
        logical_ref="artifact://restricted.example/sources/item-01",
        provider="research-archive",
    )
    with pytest.raises(DataContractError):
        synthetic_manifest(
            source=restricted,
            sensitivity=DataSensitivity.PUBLIC,
            rights=unverified_rights(),
        )
    with pytest.raises(DataContractError):
        synthetic_manifest(
            source=restricted,
            sensitivity=DataSensitivity.SYNTHETIC,
            rights=unverified_rights(),
        )
    allowed = synthetic_manifest(
        source=restricted,
        sensitivity=DataSensitivity.RESTRICTED,
        rights=RightsRecord(verification=RightsVerification.RESTRICTED, research_only=True),
        media_type_status=MediaTypeStatus.UNKNOWN,
        media_type_declared=None,
        duration_us=None,
    )
    assert allowed.sensitivity is DataSensitivity.RESTRICTED


def test_mismatched_serialized_ids_are_rejected() -> None:
    payload = synthetic_manifest().to_dict()
    payload["manifest_id"] = payload["manifest_id"][:-1] + (
        "0" if payload["manifest_id"][-1] != "0" else "1"
    )
    with pytest.raises(DataContractError) as exc:
        MediaManifest.from_dict(payload)
    assert exc.value.code == "manifest.id"


def test_stream_metadata_and_direct_constructor_id_mismatch() -> None:
    stream = StreamMetadata.from_dict({"sample_rate_hz": 8000, "channels": 1, "codec": "pcm-s16le"})
    assert stream.to_dict()["sample_rate_hz"] == 8000
    with pytest.raises(DataContractError):
        StreamMetadata(sample_rate_hz=0)
    base = synthetic_manifest()
    with pytest.raises(DataContractError) as exc:
        MediaManifest(
            namespace_id=NS,
            job_id=JOB,
            artifact_id=base.artifact_id,
            manifest_id=base.manifest_id,
            ingestion_event_id=base.ingestion_event_id,
            source=base.source,
            rights=base.rights,
            sensitivity=base.sensitivity,
            logical_filename="other-name.wav",
            media_type_status=base.media_type_status,
            byte_size=base.byte_size,
            content_sha256=base.content_sha256,
            ingested_at=base.ingested_at,
            connector_name=base.connector_name,
            connector_version=base.connector_version,
            configuration_fingerprint=HASH,
            media_type_declared=base.media_type_declared,
        )
    assert exc.value.code == "manifest.id"


def test_public_dataset_reference_does_not_imply_retrieval() -> None:
    referenced = synthetic_manifest(
        source=synthetic_source(
            source_type=SourceType.PUBLIC_DATASET_REFERENCE,
            acquisition_method=AcquisitionMethod.DECLARED_REFERENCE,
            logical_ref="catalog://public.example/datasets/demo-ref",
        ),
        sensitivity=DataSensitivity.PUBLIC,
        rights=project_fixture_rights(),
    )
    assert referenced.source.source_type is SourceType.PUBLIC_DATASET_REFERENCE
    encoded = canonical_dumps_manifest(referenced)
    assert "http://" not in encoded
    assert "huggingface" not in encoded


def test_manifest_schema_is_drift_free() -> None:
    assert_manifest_schema_drift_free()


def test_make_media_manifest_preserves_namespace_and_job() -> None:
    manifest = make_media_manifest(
        namespace_id=NS,
        job_id=JOB,
        source=synthetic_source(),
        rights=project_fixture_rights(),
        sensitivity=DataSensitivity.SYNTHETIC,
        logical_filename="synthetic-tone-01.wav",
        media_type_status=MediaTypeStatus.UNKNOWN,
        byte_size=0,
        content_sha256=HASH,
        ingested_at=FIXED,
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        configuration_fingerprint=HASH,
    )
    assert manifest.namespace_id == NS
    assert manifest.job_id == JOB
    assert manifest.byte_size == 0


def test_loads_manifest_rejects_invalid_json_and_non_objects() -> None:
    with pytest.raises(DataContractError) as invalid:
        loads_manifest("{")
    assert invalid.value.code == "manifest.json"
    with pytest.raises(DataContractError) as array:
        loads_manifest("[]")
    assert array.value.code == "manifest.json"


def test_from_dict_rejects_missing_fields_and_mismatched_event_ids() -> None:
    with pytest.raises(DataContractError) as ingested:
        MediaManifest.from_dict({"schema_version": "d1.manifest.v1"})
    assert ingested.value.code == "manifest.ingested_at"
    payload = synthetic_manifest().to_dict()
    payload["warnings"] = [1]
    with pytest.raises(DataContractError):
        MediaManifest.from_dict(payload)
    payload = synthetic_manifest().to_dict()
    payload["ingestion_event_id"] = payload["ingestion_event_id"][:-1] + (
        "0" if payload["ingestion_event_id"][-1] != "0" else "1"
    )
    with pytest.raises(DataContractError) as event:
        MediaManifest.from_dict(payload)
    assert event.value.code == "manifest.event"


def test_connector_version_warnings_and_stream_fields_are_validated() -> None:
    with pytest.raises(DataContractError):
        synthetic_manifest(connector_version="bad/version")
    with pytest.raises(DataContractError):
        synthetic_manifest(warnings=("x" * 300,))
    with pytest.raises(DataContractError):
        synthetic_manifest(warnings=tuple(f"warn-{index:02d}" for index in range(17)))
    with pytest.raises(DataContractError):
        StreamMetadata.from_dict({"codec": 1})
    video = StreamMetadata(width=2, height=2)
    assert video.to_dict() == {"width": 2, "height": 2}
    with pytest.raises(DataContractError):
        StreamMetadata(width=0)


def test_research_only_cannot_be_synthetic_and_schema_drift_is_detected() -> None:
    with pytest.raises(DataContractError) as research:
        synthetic_manifest(
            rights=RightsRecord(
                verification=RightsVerification.RESTRICTED,
                research_only=True,
            ),
            sensitivity=DataSensitivity.SYNTHETIC,
        )
    assert research.value.code == "manifest.research_only"
    schema = load_json_schema()
    defs = schema["$defs"]
    assert isinstance(defs, dict)
    source_type = defs["SourceType"]
    assert isinstance(source_type, dict)
    source_type["enum"] = ["NOPE"]
    from speaker_attribution_video.data import serialize as serialize_mod

    serialize_mod.load_json_schema = lambda: schema  # type: ignore[method-assign]
    try:
        with pytest.raises(DataContractError) as drift:
            assert_manifest_schema_drift_free()
        assert drift.value.code == "schema.drift"
    finally:
        serialize_mod.load_json_schema = load_json_schema
