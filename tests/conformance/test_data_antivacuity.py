"""Anti-vacuity: broken D1 connectors fail conform_data_connector with stable findings."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from data_factory import FIXED, synthetic_manifest, synthetic_snapshot_entry
from speaker_attribution_video.data.conformance import ConformanceFailure, conform_data_connector
from speaker_attribution_video.data.connector import ConnectorRef
from speaker_attribution_video.data.connectors.synthetic import fixture_digest
from speaker_attribution_video.data.connectors.wav import SyntheticKind, render_fixture
from speaker_attribution_video.data.enums import (
    DataSensitivity,
    IngestionState,
    RightsVerification,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.graph import graph_from_accepted_ingestion
from speaker_attribution_video.data.rights import RightsRecord
from speaker_attribution_video.data.snapshot import make_ingestion_snapshot
from speaker_attribution_video.data.store import ManifestSnapshotStore
from speaker_attribution_video.data.testing.broken import (
    ConstantHashConnector,
    IgnoreInputConnector,
    MutatingConnector,
    NamespaceRewritingConnector,
    OverwritingSnapshotStore,
    PartialAsSuccessConnector,
    PathLeakingConnector,
    SensitivityDowngradeConnector,
    SymlinkEscapeConnector,
    UnknownRightsRedistributableConnector,
    unsafe_graph_from_rejected,
)

pytestmark = pytest.mark.conformance

_TONE = ConnectorRef(logical_ref="tone", display_name="tone")
_SILENCE = ConnectorRef(logical_ref="silence", display_name="silence")
_RIGHTS = RightsRecord(verification=RightsVerification.USER_ATTESTED, license_id="caller-attested")
_UNVERIFIED = RightsRecord(verification=RightsVerification.UNVERIFIED)
_TONE_DIGEST = fixture_digest(SyntheticKind.TONE, seed=1, duration_ms=100)
_SILENCE_DIGEST = fixture_digest(SyntheticKind.SILENCE, seed=1, duration_ms=100)


def _finding(exc: ConformanceFailure) -> str:
    return exc.finding


def test_constant_hash_fails_checksum() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_data_connector(
            ConstantHashConnector,
            _TONE,
            expected_digest=_TONE_DIGEST,
            created_at=FIXED,
        )
    assert _finding(exc.value) == "checksum_correctness"


def test_ignore_input_fails_checksum() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_data_connector(
            IgnoreInputConnector,
            _SILENCE,
            expected_digest=_SILENCE_DIGEST,
            created_at=FIXED,
        )
    assert _finding(exc.value) == "checksum_correctness"


def test_namespace_rewrite_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_data_connector(NamespaceRewritingConnector, _TONE, created_at=FIXED)
    assert _finding(exc.value) == "namespace_job_preservation"


def test_sensitivity_downgrade_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_data_connector(SensitivityDowngradeConnector, _TONE, created_at=FIXED)
    assert _finding(exc.value) == "sensitivity_preservation"


def test_unknown_rights_redistributable_is_detected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "tone.wav").write_bytes(render_fixture(SyntheticKind.TONE, seed=1, duration_ms=100))

    def factory() -> UnknownRightsRedistributableConnector:
        return UnknownRightsRedistributableConnector(allowed_root=root, ingested_at=FIXED)

    with pytest.raises(ConformanceFailure) as exc:
        conform_data_connector(
            factory,
            ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),
            rights=_UNVERIFIED,
            sensitivity=DataSensitivity.INTERNAL,
            created_at=FIXED,
        )
    assert _finding(exc.value) == "unknown_rights_redistributable"


def test_partial_as_success_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_data_connector(PartialAsSuccessConnector, _TONE, created_at=FIXED)
    assert _finding(exc.value) == "complete_success"


def test_mutation_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_data_connector(MutatingConnector, _TONE, created_at=FIXED)
    assert _finding(exc.value) == "no_input_mutation"


def test_absolute_path_leak_is_detected() -> None:
    with pytest.raises(ConformanceFailure) as exc:
        conform_data_connector(PathLeakingConnector, _TONE, created_at=FIXED)
    assert _finding(exc.value) == "no_sensitive_error_leakage"


def test_symlink_escape_is_detected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    payload = render_fixture(SyntheticKind.TONE, seed=1, duration_ms=100)
    (root / "tone.wav").write_bytes(payload)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(payload)
    (root / "escape.wav").symlink_to(outside)

    def factory() -> SymlinkEscapeConnector:
        return SymlinkEscapeConnector(allowed_root=root, ingested_at=FIXED)

    with pytest.raises(ConformanceFailure) as exc:
        conform_data_connector(
            factory,
            ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),
            rights=_RIGHTS,
            sensitivity=DataSensitivity.INTERNAL,
            created_at=FIXED,
            forbidden_target=ConnectorRef(logical_ref="escape.wav", display_name="escape.wav"),
        )
    assert _finding(exc.value) == "path_escape"


def test_conflicting_snapshot_overwrite_is_detected(tmp_path: Path) -> None:
    manifest = synthetic_manifest()
    first = make_ingestion_snapshot(
        namespace_id=manifest.namespace_id,
        job_id=manifest.job_id,
        entries=(synthetic_snapshot_entry(),),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED,
    )
    later = make_ingestion_snapshot(
        namespace_id=manifest.namespace_id,
        job_id=manifest.job_id,
        entries=(synthetic_snapshot_entry(),),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED + timedelta(minutes=1),
    )
    honest = ManifestSnapshotStore(tmp_path / "honest")
    honest.put_snapshot(first)
    with pytest.raises(DataContractError) as conflict:
        honest.put_snapshot(later)
    assert conflict.value.code == "store.conflict"
    broken = OverwritingSnapshotStore(tmp_path / "broken")
    broken.put_snapshot(first)
    broken.put_snapshot(later)
    restored = broken.get_snapshot(first.snapshot_id)
    assert restored.created_at != first.created_at


def test_graph_after_rejected_is_detected() -> None:
    manifest = synthetic_manifest()
    snapshot = make_ingestion_snapshot(
        namespace_id=manifest.namespace_id,
        job_id=manifest.job_id,
        entries=(synthetic_snapshot_entry(state=IngestionState.REJECTED),),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED,
    )
    with pytest.raises(DataContractError) as honest:
        graph_from_accepted_ingestion(manifest=manifest, snapshot=snapshot, created_at=FIXED)
    assert honest.value.code == "graph.ingestion"
    forged = unsafe_graph_from_rejected(manifest, snapshot, FIXED)
    assert forged.namespace_id == manifest.namespace_id
