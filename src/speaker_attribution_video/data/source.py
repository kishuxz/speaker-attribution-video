"""Source descriptor. Logical references only; never absolute filesystem paths."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from speaker_attribution_video.data.enums import AcquisitionMethod, SourceType
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.ids import SourceId
from speaker_attribution_video.data.versions import (
    SOURCE_SCHEMA_VERSION,
    SUPPORTED_SOURCE_SCHEMA_VERSIONS,
)
from speaker_attribution_video.graph.enums import parse_enum
from speaker_attribution_video.graph.ids import require_hex64, require_slug
from speaker_attribution_video.graph.text import require_logical_uri
from speaker_attribution_video.graph.time import format_utc, parse_utc, require_utc

_MAX_NOTE = 256


def reject_filesystem_path(value: str, *, label: str) -> None:
    lowered = value.lower()
    if (
        value.startswith(("/", "\\", "file:///"))
        or ":\\" in value
        or ".." in value
        or "/home/" in lowered
        or "/users/" in lowered
    ):
        raise DataContractError(
            "source.path", f"{label} must be a logical reference, not a filesystem path"
        )


def _require_note(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > _MAX_NOTE:
        raise DataContractError("source.note", "provenance note must be a short redacted string")
    if any(ch in value for ch in "\n\r\t"):
        raise DataContractError("source.note", "provenance note must be a short redacted string")
    reject_filesystem_path(value, label="provenance_notes")
    return value


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    source_id: SourceId
    source_type: SourceType
    provider: str
    logical_ref: str
    acquisition_method: AcquisitionMethod
    acquired_at: datetime
    schema_version: str = SOURCE_SCHEMA_VERSION
    declared_owner: str | None = None
    provenance_notes: str | None = None
    source_revision: str | None = None
    source_checksum: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_SOURCE_SCHEMA_VERSIONS:
            raise DataContractError("source.schema", "unsupported source schema version")
        if not isinstance(self.source_type, SourceType):
            raise DataContractError("source.type", "source type is invalid")
        if not isinstance(self.acquisition_method, AcquisitionMethod):
            raise DataContractError("source.acquisition", "acquisition method is invalid")
        require_slug(self.provider, label="provider")
        reject_filesystem_path(self.logical_ref, label="logical_ref")
        require_logical_uri(self.logical_ref, label="logical_ref")
        require_utc(self.acquired_at)
        if self.declared_owner is not None:
            require_slug(self.declared_owner, label="declared_owner")
        _require_note(self.provenance_notes)
        if self.source_revision is not None:
            require_slug(self.source_revision, label="source_revision")
        if self.source_checksum is not None:
            require_hex64(self.source_checksum, label="source_checksum")
        expected = SourceId.derive(
            source_type=self.source_type.value,
            provider=self.provider,
            logical_ref=self.logical_ref,
            source_revision=self.source_revision,
        )
        if expected != self.source_id:
            raise DataContractError("source.id", "source_id does not match canonical source fields")

    def identity_dict(self) -> dict[str, object]:
        """Fields that participate in source identity. Observation time is excluded."""
        data: dict[str, object] = {
            "logical_ref": self.logical_ref,
            "provider": self.provider,
            "schema_version": self.schema_version,
            "source_id": self.source_id.value,
            "source_type": self.source_type.value,
        }
        if self.declared_owner is not None:
            data["declared_owner"] = self.declared_owner
        if self.source_revision is not None:
            data["source_revision"] = self.source_revision
        if self.source_checksum is not None:
            data["source_checksum"] = self.source_checksum
        data["acquisition_method"] = self.acquisition_method.value
        return data

    def to_dict(self) -> dict[str, Any]:
        data = self.identity_dict()
        data["acquired_at"] = format_utc(self.acquired_at)
        if self.provenance_notes is not None:
            data["provenance_notes"] = self.provenance_notes
        return {k: data[k] for k in sorted(data)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceDescriptor:
        acquired = data.get("acquired_at")
        if not isinstance(acquired, str):
            raise DataContractError("source.acquired_at", "acquired_at is required")
        source_type = parse_enum(SourceType, data.get("source_type"), code="source.type")
        provider = str(data.get("provider"))
        logical_ref = str(data.get("logical_ref"))
        revision = data.get("source_revision")
        source_id = (
            SourceId(str(data.get("source_id")))
            if data.get("source_id")
            else SourceId.derive(
                source_type=source_type.value,
                provider=provider,
                logical_ref=logical_ref,
                source_revision=str(revision) if revision is not None else None,
            )
        )
        return cls(
            source_id=source_id,
            source_type=source_type,
            provider=provider,
            logical_ref=logical_ref,
            acquisition_method=parse_enum(
                AcquisitionMethod, data.get("acquisition_method"), code="source.acquisition"
            ),
            acquired_at=parse_utc(acquired),
            schema_version=str(data.get("schema_version", SOURCE_SCHEMA_VERSION)),
            declared_owner=str(data["declared_owner"])
            if data.get("declared_owner") is not None
            else None,
            provenance_notes=str(data["provenance_notes"])
            if data.get("provenance_notes") is not None
            else None,
            source_revision=str(revision) if revision is not None else None,
            source_checksum=str(data["source_checksum"])
            if data.get("source_checksum") is not None
            else None,
        )


def make_source(
    *,
    source_type: SourceType,
    provider: str,
    logical_ref: str,
    acquisition_method: AcquisitionMethod,
    acquired_at: datetime,
    declared_owner: str | None = None,
    provenance_notes: str | None = None,
    source_revision: str | None = None,
    source_checksum: str | None = None,
) -> SourceDescriptor:
    source_id = SourceId.derive(
        source_type=source_type.value,
        provider=provider,
        logical_ref=logical_ref,
        source_revision=source_revision,
    )
    return SourceDescriptor(
        source_id=source_id,
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
