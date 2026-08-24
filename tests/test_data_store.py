"""Unit tests for the manifest-only snapshot store. Does not store media."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from data_factory import FIXED, JOB, NS, synthetic_manifest, synthetic_snapshot_entry
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.serialize import canonical_dumps_snapshot
from speaker_attribution_video.data.snapshot import make_ingestion_snapshot
from speaker_attribution_video.data.store import ManifestSnapshotStore, _relative

pytestmark = pytest.mark.unit


def _snapshot(*, filename: str = "synthetic-tone-01.wav"):
    return make_ingestion_snapshot(
        namespace_id=NS,
        job_id=JOB,
        entries=(synthetic_snapshot_entry(logical_filename=filename),),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED,
    )


def test_put_get_is_idempotent_and_does_not_store_media(tmp_path: Path) -> None:
    store = ManifestSnapshotStore(tmp_path / "store")
    snapshot = _snapshot()
    manifest = synthetic_manifest()
    first = store.put_snapshot(snapshot)
    again = store.put_snapshot(snapshot)
    store.put_manifest(manifest)
    assert first == again == snapshot.snapshot_id
    restored = store.get_snapshot(snapshot.snapshot_id)
    assert restored == snapshot
    assert store.get_manifest(manifest.manifest_id) == manifest
    stored = (tmp_path / "store").rglob("*.json")
    bodies = [path.read_bytes() for path in stored]
    assert bodies
    assert all(b"RIFF" not in body for body in bodies)
    assert all(b"/Users/" not in body for body in bodies)


def test_conflicting_payload_under_the_same_identity_fails_closed(tmp_path: Path) -> None:
    store = ManifestSnapshotStore(tmp_path / "store")
    snapshot = _snapshot()
    store.put_snapshot(snapshot)
    digest = snapshot.snapshot_id.digest
    target = tmp_path / "store" / "snapshots" / digest[:2] / f"{digest}.json"
    target.write_bytes(b'{"conflict":true}')
    with pytest.raises(DataContractError) as exc:
        store.put_snapshot(snapshot)
    assert exc.value.code == "store.conflict"
    assert str(tmp_path) not in str(exc.value)


def test_unfinalized_and_corrupt_reads_fail_closed(tmp_path: Path) -> None:
    store = ManifestSnapshotStore(tmp_path / "store")
    partial = make_ingestion_snapshot(
        namespace_id=NS,
        job_id=JOB,
        entries=(synthetic_snapshot_entry(),),
        connector_name="synthetic-fixture",
        connector_version="0.1.0",
        created_at=FIXED,
        finalized=False,
    )
    with pytest.raises(DataContractError) as partial_exc:
        store.put_snapshot(partial)
    assert partial_exc.value.code == "store.partial"
    snapshot = _snapshot()
    store.put_snapshot(snapshot)
    digest = snapshot.snapshot_id.digest
    target = tmp_path / "store" / "snapshots" / digest[:2] / f"{digest}.json"
    target.write_text("{not-json", encoding="utf-8")
    with pytest.raises(DataContractError):
        store.get_snapshot(snapshot.snapshot_id)


def test_paths_are_content_addressed_and_traversal_is_rejected(tmp_path: Path) -> None:
    snapshot = _snapshot()
    relative = _relative("snapshots", snapshot.snapshot_id.digest)
    assert ".." not in relative.parts
    assert str(relative) == (
        f"snapshots/{snapshot.snapshot_id.digest[:2]}/{snapshot.snapshot_id.digest}.json"
    )
    with pytest.raises(DataContractError):
        _relative("snapshots", "../" + "a" * 61)
    with pytest.raises(DataContractError):
        _relative("media", snapshot.snapshot_id.digest)
    store = ManifestSnapshotStore(tmp_path / "store")
    store.put_snapshot(snapshot)
    expected = canonical_dumps_snapshot(snapshot).encode()
    written = (tmp_path / "store" / relative).read_bytes()
    assert written == expected


def test_missing_delete_and_permissions(tmp_path: Path) -> None:
    store = ManifestSnapshotStore(tmp_path / "store")
    snapshot = _snapshot()
    with pytest.raises(DataContractError) as missing:
        store.get_snapshot(snapshot.snapshot_id)
    assert missing.value.code == "store.missing"
    assert not hasattr(ManifestSnapshotStore, "delete")
    assert not hasattr(store, "delete")
    store = ManifestSnapshotStore(tmp_path / "store")
    snapshot = _snapshot()
    store.put_snapshot(snapshot)
    digest = snapshot.snapshot_id.digest
    target = tmp_path / "store" / "snapshots" / digest[:2] / f"{digest}.json"
    mode = target.stat().st_mode & 0o777
    if os.name == "posix":
        assert mode == 0o600
        assert (tmp_path / "store").stat().st_mode & 0o777 == 0o700
    else:
        assert os.name != "posix"
        assert mode == mode
