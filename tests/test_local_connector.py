"""Unit tests for the local-file connector. Does not decode media."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from data_factory import FIXED, JOB, NS
from speaker_attribution_video.backends.contracts import CancellationToken, RequestContext
from speaker_attribution_video.data.connector import (
    ConnectorError,
    ConnectorRef,
    IngestRequest,
    InspectRequest,
    ValidateRequest,
)
from speaker_attribution_video.data.connectors import local as local_mod
from speaker_attribution_video.data.connectors.local import LocalFileConnector, safe_logical_name
from speaker_attribution_video.data.connectors.wav import SyntheticKind, render_fixture
from speaker_attribution_video.data.enums import (
    ConnectorCapability,
    ConnectorFailureReason,
    DataSensitivity,
    IngestionState,
    RightsVerification,
)
from speaker_attribution_video.data.rights import RightsRecord
from speaker_attribution_video.data.versions import CONNECTOR_INPUT_SCHEMA_VERSION

pytestmark = pytest.mark.unit

_RIGHTS = RightsRecord(verification=RightsVerification.USER_ATTESTED, license_id="caller-attested")


def _ctx() -> RequestContext:
    return RequestContext(
        namespace_id=NS, job_id=JOB, input_schema_version=CONNECTOR_INPUT_SCHEMA_VERSION
    )


def _connector(root: Path, *, max_bytes: int = 10_000_000) -> LocalFileConnector:
    return LocalFileConnector(allowed_root=root, ingested_at=FIXED, max_bytes=max_bytes)


def _write_wav(path: Path) -> None:
    path.write_bytes(render_fixture(SyntheticKind.TONE, seed=1, duration_ms=100))


def test_local_ingest_hashes_without_copying_or_decoding(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    media = root / "tone.wav"
    _write_wav(media)
    result = _connector(root).ingest(
        IngestRequest(
            context=_ctx(),
            targets=(ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),),
            rights=_RIGHTS,
            sensitivity=DataSensitivity.INTERNAL,
        )
    )
    assert result.state is IngestionState.ACCEPTED
    assert result.manifests[0].duration_us is None
    assert result.manifests[0].media_type_detected == "audio/wav"
    assert str(media) not in str(result.manifests[0].to_dict())
    assert "ffmpeg" not in Path(local_mod.__file__).read_text(encoding="utf-8")
    assert media.exists()


def test_path_traversal_and_absolute_paths_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    connector = _connector(root)
    for ref in ("../secret.wav", "/tmp/secret.wav", "foo/../../secret.wav"):
        with pytest.raises(ConnectorError) as exc:
            connector.inspect(
                InspectRequest(
                    context=_ctx(),
                    target=ConnectorRef(logical_ref=ref, display_name="x"),
                    rights=_RIGHTS,
                    sensitivity=DataSensitivity.INTERNAL,
                )
            )
        assert exc.value.reason is ConnectorFailureReason.PATH_ESCAPE
        assert "secret" not in str(exc.value)
        assert "/tmp" not in str(exc.value)


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.wav"
    _write_wav(outside)
    (root / "escape.wav").symlink_to(outside)
    with pytest.raises(ConnectorError) as exc:
        _connector(root).inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="escape.wav", display_name="escape.wav"),
                rights=_RIGHTS,
                sensitivity=DataSensitivity.INTERNAL,
            )
        )
    assert exc.value.reason is ConnectorFailureReason.PATH_ESCAPE


def test_fifo_and_directory_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    os.mkfifo(root / "pipe.fifo")
    connector = _connector(root)
    with pytest.raises(ConnectorError) as fifo_exc:
        connector.inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="pipe.fifo", display_name="pipe.fifo"),
                rights=_RIGHTS,
                sensitivity=DataSensitivity.INTERNAL,
            )
        )
    assert fifo_exc.value.reason is ConnectorFailureReason.INVALID_INPUT
    with pytest.raises(ConnectorError):
        connector.inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref=".", display_name="root"),
                rights=_RIGHTS,
                sensitivity=DataSensitivity.INTERNAL,
            )
        )


def test_max_size_and_missing_rights(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_wav(root / "tone.wav")
    with pytest.raises(ConnectorError) as limit:
        _connector(root, max_bytes=8).inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),
                rights=_RIGHTS,
                sensitivity=DataSensitivity.INTERNAL,
            )
        )
    assert limit.value.reason is ConnectorFailureReason.RESOURCE_LIMIT
    with pytest.raises(ConnectorError) as rights:
        _connector(root).inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),
            )
        )
    assert rights.value.reason is ConnectorFailureReason.POLICY_REJECTION


def test_change_during_hash_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    media = root / "tone.wav"
    _write_wav(media)
    original_sha = hashlib.sha256

    def touching_sha(*args: object, **kwargs: object):
        os.utime(media, None)
        return original_sha(*args, **kwargs)

    monkeypatch.setattr(hashlib, "sha256", touching_sha)
    with pytest.raises(ConnectorError) as exc:
        _connector(root).inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),
                rights=_RIGHTS,
                sensitivity=DataSensitivity.INTERNAL,
            )
        )
    assert exc.value.reason is ConnectorFailureReason.CHANGED_DURING_READ


def test_unicode_names_and_hard_links(tmp_path: Path) -> None:
    assert "файл" not in safe_logical_name("файл.WAV")
    root = tmp_path / "root"
    root.mkdir()
    media = root / "tone.wav"
    _write_wav(media)
    os.link(media, root / "alias.wav")
    result = _connector(root).inspect(
        InspectRequest(
            context=_ctx(),
            target=ConnectorRef(logical_ref="alias.wav", display_name="alias.wav"),
            rights=_RIGHTS,
            sensitivity=DataSensitivity.INTERNAL,
        )
    )
    assert result.manifests[0].warnings == ("hard-link-shared-inode",)


def test_unsupported_capability_and_extension_is_not_authoritative(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "notes.txt").write_bytes(b"not-a-media-container")
    connector = _connector(root)
    with pytest.raises(ConnectorError) as cap:
        connector.inspect(
            InspectRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="notes.txt", display_name="notes.txt"),
                requested_capabilities=frozenset({ConnectorCapability.SYNTHETIC_GENERATION}),
                rights=_RIGHTS,
                sensitivity=DataSensitivity.INTERNAL,
            )
        )
    assert cap.value.reason is ConnectorFailureReason.UNSUPPORTED_CAPABILITY
    result = connector.inspect(
        InspectRequest(
            context=_ctx(),
            target=ConnectorRef(logical_ref="notes.txt", display_name="notes.txt"),
            rights=_RIGHTS,
            sensitivity=DataSensitivity.INTERNAL,
            declared_media_type="audio/wav",
        )
    )
    assert result.manifests[0].media_type_detected is None
    assert result.manifests[0].to_dict()["media_type_status"] == "declared"


def test_mixed_ingest_is_partial_and_keeps_failed_entries(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_wav(root / "tone.wav")
    connector = _connector(root)
    result = connector.ingest(
        IngestRequest(
            context=_ctx(),
            targets=(
                ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),
                ConnectorRef(logical_ref="missing.wav", display_name="missing.wav"),
            ),
            rights=_RIGHTS,
            sensitivity=DataSensitivity.INTERNAL,
        )
    )
    assert result.state is IngestionState.PARTIAL
    assert any(entry.state is IngestionState.ACCEPTED for entry in result.snapshot.entries)
    assert any(entry.state is IngestionState.REJECTED for entry in result.snapshot.entries)
    token = CancellationToken()
    token.cancel()
    with pytest.raises(ConnectorError) as cancelled:
        connector.validate(
            ValidateRequest(
                context=_ctx(),
                target=ConnectorRef(logical_ref="tone.wav", display_name="tone.wav"),
                rights=_RIGHTS,
                sensitivity=DataSensitivity.INTERNAL,
            ),
            cancel=token,
        )
    assert cancelled.value.reason is ConnectorFailureReason.CANCELLATION
    connector.close()
