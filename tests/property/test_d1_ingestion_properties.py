"""Hypothesis properties for D1 ingestion. Synthetic data only."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from data_factory import (
    FIXED,
    JOB,
    NS,
    synthetic_entry,
    synthetic_manifest,
    synthetic_snapshot_entry,
    synthetic_source,
)
from speaker_attribution_video.backends.contracts import RequestContext
from speaker_attribution_video.data.connector import ConnectorError, ConnectorRef, InspectRequest
from speaker_attribution_video.data.connectors.local import LocalFileConnector, safe_logical_name
from speaker_attribution_video.data.connectors.paths import require_relative_request
from speaker_attribution_video.data.connectors.wav import SyntheticKind, render_fixture
from speaker_attribution_video.data.dataset import make_dataset_manifest
from speaker_attribution_video.data.enums import (
    AcquisitionMethod,
    ConnectorFailureReason,
    DataSensitivity,
    DatasetSplit,
    IntendedUse,
    PolicyDecision,
    PolicyOperation,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.policy import evaluate_policy
from speaker_attribution_video.data.rights import RightsRecord, project_fixture_rights
from speaker_attribution_video.data.serialize import (
    canonical_dumps_manifest,
    canonical_dumps_snapshot,
)
from speaker_attribution_video.data.snapshot import make_ingestion_snapshot
from speaker_attribution_video.data.source import make_source
from speaker_attribution_video.data.store import ManifestSnapshotStore
from speaker_attribution_video.data.versions import CONNECTOR_INPUT_SCHEMA_VERSION

pytestmark = pytest.mark.property

_TRAVERSAL = st.sampled_from(("../secret", "..\\secret", "/tmp/secret", "foo/../../secret"))
_UNICODE = st.sampled_from(("файл.wav", "naïve.wav", "tone\u0000.wav", "ok.wav"))
_OPS = st.sampled_from(tuple(PolicyOperation))
_SENS = st.sampled_from(tuple(DataSensitivity))
_VERIFY = st.sampled_from(tuple(RightsVerification))


def _ctx() -> RequestContext:
    return RequestContext(
        namespace_id=NS, job_id=JOB, input_schema_version=CONNECTOR_INPUT_SCHEMA_VERSION
    )


@given(ref=_TRAVERSAL)
@settings(max_examples=20)
def test_path_traversal_variants_are_rejected(ref: str) -> None:
    with pytest.raises(ConnectorError) as exc:
        require_relative_request(ref)
    assert exc.value.reason in {
        ConnectorFailureReason.PATH_ESCAPE,
        ConnectorFailureReason.INVALID_INPUT,
    }
    assert "/Users/" not in str(exc.value)
    assert "/home/" not in str(exc.value)


@given(name=_UNICODE)
@settings(max_examples=20)
def test_unicode_names_do_not_preserve_raw_glyphs(name: str) -> None:
    logical = safe_logical_name(name)
    assert "/" not in logical
    assert "\\" not in logical
    if any(ord(ch) > 127 for ch in name):
        assert name.split(".")[0] not in logical or logical == "user-file"


@given(size=st.integers(min_value=1, max_value=64))
@settings(max_examples=15)
def test_file_size_boundary_is_enforced(size: int) -> None:
    payload = render_fixture(SyntheticKind.TONE, seed=1, duration_ms=100)
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "tone.wav").write_bytes(payload)
        connector = LocalFileConnector(
            allowed_root=root, ingested_at=FIXED, max_bytes=size, require_rights=False
        )
        with pytest.raises(ConnectorError) as exc:
            connector.inspect(
                InspectRequest(
                    context=_ctx(),
                    target=ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),
                )
            )
        assert exc.value.reason is ConnectorFailureReason.RESOURCE_LIMIT


@given(seed=st.integers(min_value=0, max_value=50))
@settings(max_examples=15)
def test_canonical_manifest_and_snapshot_are_stable(seed: int) -> None:
    del seed
    manifest = synthetic_manifest()
    assert canonical_dumps_manifest(manifest) == canonical_dumps_manifest(manifest)
    snapshot = make_ingestion_snapshot(
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
        created_at=FIXED,
    )
    assert snapshot.snapshot_id == later.snapshot_id
    assert canonical_dumps_snapshot(snapshot) == canonical_dumps_snapshot(later)


@given(name=st.from_regex(r"^[a-z][a-z0-9]{2,8}$", fullmatch=True))
@settings(max_examples=15)
def test_duplicate_dataset_entries_are_detected(name: str) -> None:
    with pytest.raises(DataContractError) as exc:
        make_dataset_manifest(
            name=name,
            version="v1",
            source=synthetic_source(),
            rights=project_fixture_rights(),
            sensitivity=DataSensitivity.SYNTHETIC,
            entries=(synthetic_entry(), synthetic_entry(logical_filename="synthetic-tone-02.wav")),
            split=DatasetSplit.DEMO,
            intended_use=IntendedUse.FIXTURE,
            created_at=FIXED,
            producer="test-builder",
        )
    assert exc.value.code == "dataset.duplicate_hash"


@given(operation=_OPS, sensitivity=_SENS)
@settings(max_examples=30)
def test_unknown_never_defaults_to_allow(
    operation: PolicyOperation, sensitivity: DataSensitivity
) -> None:
    result = evaluate_policy(
        source=make_source(
            source_type=SourceType.UNKNOWN,
            provider="caller",
            logical_ref="artifact://synth.example/sources/unknown",
            acquisition_method=AcquisitionMethod.UNKNOWN,
            acquired_at=FIXED,
        ),
        rights=RightsRecord(verification=RightsVerification.UNVERIFIED),
        sensitivity=sensitivity,
        operation=operation,
        now=FIXED,
    )
    assert result.decision is not PolicyDecision.ALLOW


@given(payload=st.binary(min_size=8, max_size=32))
@settings(max_examples=10)
def test_snapshot_put_is_idempotent(payload: bytes) -> None:
    del payload
    with tempfile.TemporaryDirectory() as raw:
        store = ManifestSnapshotStore(Path(raw) / "store")
        snapshot = make_ingestion_snapshot(
            namespace_id=NS,
            job_id=JOB,
            entries=(synthetic_snapshot_entry(),),
            connector_name="synthetic-fixture",
            connector_version="0.1.0",
            created_at=FIXED,
        )
        store.put_snapshot(snapshot)
        store.put_snapshot(snapshot)
        assert store.get_snapshot(snapshot.snapshot_id) == snapshot


def test_special_files_are_rejected_where_supported(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    connector = LocalFileConnector(allowed_root=root, ingested_at=FIXED, require_rights=False)
    if hasattr(os, "mkfifo"):
        os.mkfifo(root / "pipe.fifo")
        with pytest.raises(ConnectorError) as exc:
            connector.inspect(
                InspectRequest(
                    context=_ctx(),
                    target=ConnectorRef(logical_ref="pipe.fifo", display_name="pipe.fifo"),
                )
            )
        assert exc.value.reason is ConnectorFailureReason.INVALID_INPUT
    else:
        assert not hasattr(os, "mkfifo")
