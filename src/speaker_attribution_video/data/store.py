"""Local content-addressed store for manifest documents. Never stores raw media.

Atomicity
---------
On POSIX, the final path is published with ``os.link`` from a same-directory
temporary file after ``fsync``. If the destination already exists, the write is
compared byte-for-byte: identical content is idempotent success; different
content fails closed. The temporary file is unlinked afterward.

On Windows, ``os.replace`` updates the destination name atomically on the same
volume. Conflict detection is performed before replace and is not a concurrent
multi-writer lock. D1 does not expose delete or garbage collection.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.ids import ManifestId, SnapshotId
from speaker_attribution_video.data.manifest import MediaManifest
from speaker_attribution_video.data.serialize import (
    canonical_dumps_manifest,
    canonical_dumps_snapshot,
    loads_manifest,
    loads_snapshot,
)
from speaker_attribution_video.data.snapshot import IngestionSnapshot

_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_KINDS = frozenset({"manifests", "snapshots"})
_DIR_MODE = 0o700
_FILE_MODE = 0o600


def _require_digest(digest: str) -> str:
    if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
        raise DataContractError("store.id", "content address must be a SHA-256 digest")
    return digest


def _relative(kind: str, digest: str) -> Path:
    if kind not in _KINDS:
        raise DataContractError("store.kind", "unsupported store document kind")
    hex_digest = _require_digest(digest)
    return Path(kind) / hex_digest[:2] / f"{hex_digest}.json"


class ManifestSnapshotStore:
    """Persist MediaManifest and IngestionSnapshot JSON only."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise DataContractError("store.root", "store root must be a path")
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._chmod_dir(self._root)

    def put_snapshot(self, snapshot: IngestionSnapshot) -> SnapshotId:
        if not snapshot.finalized:
            raise DataContractError(
                "store.partial",
                "partial snapshots cannot be persisted as finalized documents",
            )
        payload = canonical_dumps_snapshot(snapshot).encode()
        self._put("snapshots", snapshot.snapshot_id.digest, payload)
        return snapshot.snapshot_id

    def put_manifest(self, manifest: MediaManifest) -> ManifestId:
        payload = canonical_dumps_manifest(manifest).encode()
        self._put("manifests", manifest.manifest_id.digest, payload)
        return manifest.manifest_id

    def get_snapshot(self, snapshot_id: SnapshotId) -> IngestionSnapshot:
        text = self._read("snapshots", snapshot_id.digest)
        snapshot = loads_snapshot(text)
        if snapshot.snapshot_id != snapshot_id:
            raise DataContractError("store.identity", "stored snapshot identity mismatch")
        return snapshot

    def get_manifest(self, manifest_id: ManifestId) -> MediaManifest:
        text = self._read("manifests", manifest_id.digest)
        manifest = loads_manifest(text)
        if manifest.manifest_id != manifest_id:
            raise DataContractError("store.identity", "stored manifest identity mismatch")
        return manifest

    def _path(self, kind: str, digest: str) -> Path:
        relative = _relative(kind, digest)
        candidate = (self._root / relative).resolve()
        try:
            candidate.relative_to(self._root.resolve())
        except ValueError as exc:
            raise DataContractError("store.traversal", "store path escaped the root") from exc
        return candidate

    def _put(self, kind: str, digest: str, payload: bytes) -> None:
        target = self._path(kind, digest)
        if b"RIFF" in payload or b"ftyp" in payload:
            raise DataContractError("store.media", "raw media must not be stored")
        if target.exists():
            existing = target.read_bytes()
            if existing == payload:
                return
            raise DataContractError(
                "store.conflict",
                "existing document conflicts with the supplied identity",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        self._chmod_dir(target.parent)
        fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=target.parent)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, _FILE_MODE)
            self._publish(tmp, target, payload)
        except DataContractError:
            tmp.unlink(missing_ok=True)
            raise
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise DataContractError("store.io", "document could not be written") from exc
        self._chmod_file(target)

    def _publish(self, tmp: Path, target: Path, payload: bytes) -> None:
        try:
            os.link(tmp, target)
        except FileExistsError:
            existing = target.read_bytes()
            if existing != payload:
                raise DataContractError(
                    "store.conflict",
                    "existing document conflicts with the supplied identity",
                ) from None
        except OSError:
            if os.name == "posix":
                raise
            if target.exists():
                existing = target.read_bytes()
                if existing != payload:
                    raise DataContractError(
                        "store.conflict",
                        "existing document conflicts with the supplied identity",
                    ) from None
                return
            os.replace(tmp, target)
            return
        finally:
            tmp.unlink(missing_ok=True)

    def _read(self, kind: str, digest: str) -> str:
        target = self._path(kind, digest)
        try:
            return target.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise DataContractError("store.missing", "document is not in the store") from exc
        except OSError as exc:
            raise DataContractError("store.io", "document could not be read") from exc

    @staticmethod
    def _chmod_dir(path: Path) -> None:
        if os.name == "posix":
            os.chmod(path, _DIR_MODE)

    @staticmethod
    def _chmod_file(path: Path) -> None:
        if os.name == "posix" and path.exists():
            os.chmod(path, _FILE_MODE)


__all__ = ["ManifestSnapshotStore"]
