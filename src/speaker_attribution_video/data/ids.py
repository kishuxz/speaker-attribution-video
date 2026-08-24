"""D1 identifiers. Distinct from G1 kinds; same canonical hashing rules."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass

from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.versions import (
    DATA_ID_SCHEMA_VERSION,
    SUPPORTED_DATA_ID_SCHEMA_VERSIONS,
)
from speaker_attribution_video.graph.ids import require_hex64, require_slug
from speaker_attribution_video.graph.jsonutil import canonical_object

_ID_RE = re.compile(
    r"^d1\.id\.v1/(source|artifact|manifest|ingestion_event|dataset|snapshot)/[A-Za-z0-9._:-]{1,256}$"
)
_KINDS = frozenset({"source", "artifact", "manifest", "ingestion_event", "dataset", "snapshot"})


def _sha256_hex(canonical_json: str) -> str:
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _format_id(kind: str, payload: str) -> str:
    if kind not in _KINDS:
        raise DataContractError("id.kind", "unsupported identifier kind")
    text = f"{DATA_ID_SCHEMA_VERSION}/{kind}/{payload}"
    if not _ID_RE.fullmatch(text):
        raise DataContractError("id.malformed", "identifier is blank or malformed")
    return text


def parse_data_id(value: str, *, expected_kind: str) -> tuple[str, str, str]:
    if not isinstance(value, str) or not value.strip():
        raise DataContractError("id.blank", "identifier is blank or malformed")
    parts = value.split("/", 2)
    if len(parts) != 3:
        raise DataContractError("id.malformed", "identifier is blank or malformed")
    schema, kind, payload = parts
    if schema not in SUPPORTED_DATA_ID_SCHEMA_VERSIONS:
        raise DataContractError("id.schema", "unsupported identifier schema version")
    if kind != expected_kind or kind not in _KINDS:
        raise DataContractError("id.kind", "identifier kind does not match expected type")
    if not payload or not _ID_RE.fullmatch(value):
        raise DataContractError("id.malformed", "identifier is blank or malformed")
    return schema, kind, payload


@dataclass(frozen=True, slots=True)
class SourceId:
    value: str

    def __post_init__(self) -> None:
        parse_data_id(self.value, expected_kind="source")

    @classmethod
    def derive(
        cls,
        *,
        source_type: str,
        provider: str,
        logical_ref: str,
        source_revision: str | None = None,
    ) -> SourceId:
        revision = (
            "none" if source_revision is None else require_slug(source_revision, label="revision")
        )
        payload = _sha256_hex(
            canonical_object(
                {
                    "kind": "source",
                    "logical_ref": hashlib.sha256(logical_ref.encode("utf-8")).hexdigest(),
                    "provider": require_slug(provider, label="provider"),
                    "revision": revision,
                    "schema": DATA_ID_SCHEMA_VERSION,
                    "source_type": source_type,
                }
            )
        )
        return cls(_format_id("source", payload))


@dataclass(frozen=True, slots=True)
class ArtifactId:
    """Content identity: derived only from the SHA-256 digest of source bytes."""

    value: str

    def __post_init__(self) -> None:
        parse_data_id(self.value, expected_kind="artifact")

    @classmethod
    def from_digest(cls, content_sha256: str) -> ArtifactId:
        digest = require_hex64(content_sha256, label="content_sha256")
        return cls(_format_id("artifact", digest))

    @property
    def digest(self) -> str:
        return parse_data_id(self.value, expected_kind="artifact")[2]


@dataclass(frozen=True, slots=True)
class ManifestId:
    """Manifest identity: canonical fields excluding observation timestamps."""

    value: str

    def __post_init__(self) -> None:
        parse_data_id(self.value, expected_kind="manifest")

    @classmethod
    def derive(cls, identity_fields: Mapping[str, object]) -> ManifestId:
        payload = _sha256_hex(canonical_object(dict(identity_fields)))
        return cls(_format_id("manifest", payload))


@dataclass(frozen=True, slots=True)
class IngestionEventId:
    """Ingestion-event identity: manifest identity plus observation timestamp."""

    value: str

    def __post_init__(self) -> None:
        parse_data_id(self.value, expected_kind="ingestion_event")

    @classmethod
    def derive(
        cls, *, manifest_id: ManifestId, ingested_at: str, connector: str
    ) -> IngestionEventId:
        payload = _sha256_hex(
            canonical_object(
                {
                    "connector": require_slug(connector, label="connector"),
                    "ingested_at": ingested_at,
                    "kind": "ingestion_event",
                    "manifest": manifest_id.value,
                    "schema": DATA_ID_SCHEMA_VERSION,
                }
            )
        )
        return cls(_format_id("ingestion_event", payload))


@dataclass(frozen=True, slots=True)
class DatasetId:
    """Dataset identity: name and version only. Entries are hashed separately."""

    value: str

    def __post_init__(self) -> None:
        parse_data_id(self.value, expected_kind="dataset")

    @classmethod
    def derive(cls, *, name: str, version: str) -> DatasetId:
        payload = _sha256_hex(
            canonical_object(
                {
                    "kind": "dataset",
                    "name": require_slug(name, label="dataset_name"),
                    "schema": DATA_ID_SCHEMA_VERSION,
                    "version": require_slug(version, label="dataset_version"),
                }
            )
        )
        return cls(_format_id("dataset", payload))


@dataclass(frozen=True, slots=True)
class SnapshotId:
    """Snapshot identity: canonical entries excluding observation timestamps."""

    value: str

    def __post_init__(self) -> None:
        parse_data_id(self.value, expected_kind="snapshot")

    @classmethod
    def derive(cls, identity_fields: Mapping[str, object]) -> SnapshotId:
        payload = _sha256_hex(canonical_object(dict(identity_fields)))
        return cls(_format_id("snapshot", payload))
