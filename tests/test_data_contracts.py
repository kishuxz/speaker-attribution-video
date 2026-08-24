"""Unit tests for D1 source, rights, sensitivity, and identifier contracts."""

from __future__ import annotations

from datetime import timedelta

import pytest

from data_factory import FIXED, HASH, synthetic_source
from speaker_attribution_video.data.enums import (
    AcquisitionMethod,
    DataSensitivity,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.ids import (
    ArtifactId,
    IngestionEventId,
    ManifestId,
    SourceId,
    parse_data_id,
)
from speaker_attribution_video.data.rights import RightsRecord, project_fixture_rights
from speaker_attribution_video.data.sensitivity import (
    can_transition,
    require_transition,
    require_unambiguous,
    to_graph_sensitivity,
)
from speaker_attribution_video.data.source import (
    SourceDescriptor,
    make_source,
    reject_filesystem_path,
)
from speaker_attribution_video.graph.enums import Sensitivity as GraphSensitivity
from speaker_attribution_video.graph.errors import GraphContractError

pytestmark = pytest.mark.unit


def test_source_id_ignores_acquisition_timestamp() -> None:
    first = synthetic_source(acquired_at=FIXED)
    later = synthetic_source(acquired_at=FIXED + timedelta(seconds=30))
    assert first.source_id == later.source_id
    assert first.to_dict()["acquired_at"] != later.to_dict()["acquired_at"]
    assert first.identity_dict() == later.identity_dict()


def test_source_round_trip_and_supported_types() -> None:
    for source_type in SourceType:
        if source_type is SourceType.RESEARCH_RESTRICTED:
            source = synthetic_source(
                source_type=source_type,
                logical_ref="artifact://restricted.example/sources/item-01",
                provider="research-archive",
            )
        else:
            source = synthetic_source(source_type=source_type)
        restored = SourceDescriptor.from_dict(source.to_dict())
        assert restored == source


def test_filesystem_paths_are_rejected_without_leaking_the_path() -> None:
    with pytest.raises(DataContractError) as exc:
        reject_filesystem_path("/Users/example/secret.wav", label="logical_ref")
    assert exc.value.code == "source.path"
    assert "/Users" not in str(exc.value)
    assert "secret.wav" not in str(exc.value)
    with pytest.raises(DataContractError):
        make_source(
            source_type=SourceType.LOCAL_USER_FILE,
            provider="caller",
            logical_ref="file:///tmp/media.wav",
            acquisition_method=AcquisitionMethod.USER_COPY,
            acquired_at=FIXED,
        )


def test_malformed_source_checksum_and_schema_are_rejected() -> None:
    with pytest.raises(GraphContractError) as digest:
        synthetic_source(source_checksum="not-a-hash")
    assert digest.value.code == "hash.sha256"
    payload = synthetic_source().to_dict()
    payload["schema_version"] = "d1.source.v0"
    with pytest.raises(DataContractError) as schema:
        SourceDescriptor.from_dict(payload)
    assert schema.value.code == "source.schema"


def test_unknown_rights_cannot_be_marked_redistributable() -> None:
    with pytest.raises(DataContractError) as missing:
        RightsRecord(
            verification=RightsVerification.UNVERIFIED,
            redistribution_permitted=True,
        )
    assert missing.value.code == "rights.redistribution"
    with pytest.raises(DataContractError) as license_missing:
        RightsRecord(
            verification=RightsVerification.USER_ATTESTED,
            redistribution_permitted=True,
        )
    assert license_missing.value.code == "rights.license"


def test_user_attestation_is_not_independent_verification() -> None:
    attested = RightsRecord(
        verification=RightsVerification.USER_ATTESTED,
        license_id="caller-attested",
        redistribution_permitted=True,
    )
    verified = project_fixture_rights()
    assert attested.verification is not verified.verification
    assert attested.independently_verified_redistributable() is False
    assert verified.independently_verified_redistributable() is True


def test_prohibited_and_research_only_fail_closed() -> None:
    with pytest.raises(DataContractError) as prohibited:
        RightsRecord(
            verification=RightsVerification.PROHIBITED,
            redistribution_permitted=True,
            license_id="none",
        )
    assert prohibited.value.code == "rights.prohibited"
    with pytest.raises(DataContractError) as research:
        RightsRecord(
            verification=RightsVerification.VERIFIED,
            license_id="internal-research",
            redistribution_permitted=True,
            research_only=True,
        )
    assert research.value.code == "rights.research_only"


def test_terms_acceptance_is_never_automated() -> None:
    with pytest.raises(DataContractError) as exc:
        RightsRecord(
            verification=RightsVerification.USER_ATTESTED,
            terms_accepted_at=FIXED,
        )
    assert exc.value.code == "rights.terms"
    accepted = RightsRecord(
        verification=RightsVerification.USER_ATTESTED,
        terms_accepted_by="caller",
        terms_accepted_at=FIXED,
    )
    assert accepted.terms_accepted_by == "caller"


def test_rights_round_trip_and_unsupported_schema() -> None:
    rights = project_fixture_rights()
    assert RightsRecord.from_dict(rights.to_dict()) == rights
    payload = rights.to_dict()
    payload["schema_version"] = "d1.rights.v0"
    with pytest.raises(DataContractError) as schema:
        RightsRecord.from_dict(payload)
    assert schema.value.code == "rights.schema"


def test_sensitivity_cannot_be_silently_downgraded() -> None:
    assert can_transition(DataSensitivity.INTERNAL, DataSensitivity.RESTRICTED)
    require_transition(DataSensitivity.PUBLIC, DataSensitivity.SYNTHETIC)
    with pytest.raises(DataContractError) as exc:
        require_transition(DataSensitivity.BIOMETRIC_DATA, DataSensitivity.PUBLIC)
    assert exc.value.code == "sensitivity.downgrade"
    with pytest.raises(DataContractError):
        require_transition(DataSensitivity.UNKNOWN, DataSensitivity.PUBLIC)


def test_biometric_and_personal_data_map_without_downgrade() -> None:
    assert to_graph_sensitivity(DataSensitivity.PUBLIC) is GraphSensitivity.PUBLIC
    assert to_graph_sensitivity(DataSensitivity.SYNTHETIC) is GraphSensitivity.INTERNAL
    assert to_graph_sensitivity(DataSensitivity.BIOMETRIC_DATA) is GraphSensitivity.RESTRICTED
    assert to_graph_sensitivity(DataSensitivity.PERSONAL_DATA) is GraphSensitivity.SENSITIVE
    assert to_graph_sensitivity(DataSensitivity.UNKNOWN) is GraphSensitivity.RESTRICTED
    assert DataSensitivity.BIOMETRIC_DATA.value == "BIOMETRIC_DATA"


def test_artifact_id_is_content_addressed() -> None:
    first = ArtifactId.from_digest(HASH)
    other = ArtifactId.from_digest("b" * 64)
    assert first.digest == HASH
    assert first != other
    with pytest.raises(GraphContractError):
        ArtifactId.from_digest("abc")


def test_manifest_and_event_ids_are_distinct_kinds() -> None:
    manifest = ManifestId.derive({"kind": "manifest", "label": "one"})
    later = IngestionEventId.derive(
        manifest_id=manifest,
        ingested_at="2026-08-24T19:00:00.000000Z",
        connector="synthetic-fixture",
    )
    assert manifest.value.startswith("d1.id.v1/manifest/")
    assert later.value.startswith("d1.id.v1/ingestion_event/")
    assert type(manifest) is not type(later)


def test_source_id_rejects_wrong_kind() -> None:
    artifact = ArtifactId.from_digest(HASH)
    with pytest.raises(DataContractError) as exc:
        SourceId(artifact.value)
    assert exc.value.code == "id.kind"
    with pytest.raises(DataContractError):
        SourceId("d1.id.v0/source/" + HASH)


def test_parse_data_id_rejects_blank_malformed_and_empty_payload() -> None:
    with pytest.raises(DataContractError) as blank:
        parse_data_id("", expected_kind="source")
    assert blank.value.code == "id.blank"
    with pytest.raises(DataContractError) as malformed:
        parse_data_id("d1.id.v1/source", expected_kind="source")
    assert malformed.value.code == "id.malformed"
    with pytest.raises(DataContractError) as payload:
        parse_data_id("d1.id.v1/source/", expected_kind="source")
    assert payload.value.code == "id.malformed"


def test_source_notes_and_optional_identity_fields() -> None:
    noted = synthetic_source(provenance_notes="generated-in-test-suite", source_checksum=None)
    assert "generated-in-test-suite" in noted.to_dict()["provenance_notes"]
    assert "source_checksum" not in noted.identity_dict()
    with pytest.raises(DataContractError):
        synthetic_source(provenance_notes="note\nwith-newline")
    with pytest.raises(DataContractError):
        SourceDescriptor.from_dict({"source_type": "SYNTHETIC"})


def test_rights_notes_and_non_boolean_flags_are_rejected() -> None:
    with pytest.raises(DataContractError) as note:
        RightsRecord(verification=RightsVerification.UNVERIFIED, reviewer_note="path/secret")
    assert note.value.code == "rights.note"
    with pytest.raises(DataContractError) as flag:
        RightsRecord.from_dict({"verification": "UNVERIFIED", "redistribution_permitted": "yes"})
    assert flag.value.code == "rights.bool"
    recorded = RightsRecord(
        verification=RightsVerification.UNVERIFIED,
        reviewer_note="attested-by-caller",
        derivative_use_permitted=False,
        expires_at=FIXED,
    )
    restored = RightsRecord.from_dict(recorded.to_dict())
    assert restored.reviewer_note == "attested-by-caller"
    assert restored.expires_at == FIXED


def test_personal_biometric_and_restricted_cannot_be_redistributable() -> None:
    with pytest.raises(DataContractError) as personal:
        require_unambiguous(sensitivity=DataSensitivity.PERSONAL_DATA, redistribution=True)
    assert personal.value.code == "sensitivity.redistribution"
    with pytest.raises(DataContractError):
        require_unambiguous(sensitivity=DataSensitivity.BIOMETRIC_DATA, redistribution=True)
    with pytest.raises(DataContractError):
        require_unambiguous(sensitivity=DataSensitivity.RESTRICTED, redistribution=True)
    require_unambiguous(sensitivity=DataSensitivity.SYNTHETIC, redistribution=True)
