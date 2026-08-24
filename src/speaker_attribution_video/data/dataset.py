"""Dataset catalog contracts. External files are referenced, never bundled."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from speaker_attribution_video.data.enums import (
    DataSensitivity,
    DatasetSplit,
    IntendedUse,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.ids import ArtifactId, DatasetId
from speaker_attribution_video.data.rights import RightsRecord
from speaker_attribution_video.data.sensitivity import require_unambiguous
from speaker_attribution_video.data.source import SourceDescriptor, reject_filesystem_path
from speaker_attribution_video.data.versions import (
    DATASET_SCHEMA_VERSION,
    SUPPORTED_DATASET_SCHEMA_VERSIONS,
)
from speaker_attribution_video.graph.enums import parse_enum
from speaker_attribution_video.graph.ids import require_hex64, require_slug
from speaker_attribution_video.graph.text import require_logical_uri
from speaker_attribution_video.graph.time import format_utc, parse_utc, require_utc

_EVAL_SPLITS = frozenset({DatasetSplit.VALIDATION, DatasetSplit.TEST})
_TRAINISH = frozenset({DatasetSplit.TRAIN})
_PUBLICISH = frozenset({DataSensitivity.PUBLIC, DataSensitivity.SYNTHETIC})
_RESTRICTEDISH = frozenset(
    {
        DataSensitivity.RESTRICTED,
        DataSensitivity.PERSONAL_DATA,
        DataSensitivity.BIOMETRIC_DATA,
        DataSensitivity.CONFIDENTIAL,
    }
)


@dataclass(frozen=True, slots=True)
class DatasetEntry:
    artifact_id: ArtifactId
    content_sha256: str
    logical_filename: str
    split: DatasetSplit
    sensitivity: DataSensitivity
    logical_ref: str | None = None

    def __post_init__(self) -> None:
        digest = require_hex64(self.content_sha256, label="content_sha256")
        if self.artifact_id.digest != digest:
            raise DataContractError("dataset.entry", "artifact_id must match content SHA-256")
        require_slug(self.logical_filename, label="logical_filename")
        reject_filesystem_path(self.logical_filename, label="logical_filename")
        if not isinstance(self.split, DatasetSplit):
            raise DataContractError("dataset.split", "dataset split is invalid")
        if not isinstance(self.sensitivity, DataSensitivity):
            raise DataContractError("dataset.sensitivity", "sensitivity is invalid")
        if self.logical_ref is not None:
            reject_filesystem_path(self.logical_ref, label="logical_ref")
            require_logical_uri(self.logical_ref, label="logical_ref")

    def identity_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "artifact_id": self.artifact_id.value,
            "content_sha256": self.content_sha256,
            "logical_filename": self.logical_filename,
            "sensitivity": self.sensitivity.value,
            "split": self.split.value,
        }
        if self.logical_ref is not None:
            data["logical_ref"] = self.logical_ref
        return data

    def to_dict(self) -> dict[str, Any]:
        return {k: self.identity_dict()[k] for k in sorted(self.identity_dict())}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DatasetEntry:
        digest = str(data.get("content_sha256"))
        return cls(
            artifact_id=ArtifactId.from_digest(digest),
            content_sha256=digest,
            logical_filename=str(data.get("logical_filename")),
            split=parse_enum(DatasetSplit, data.get("split"), code="dataset.split"),
            sensitivity=parse_enum(
                DataSensitivity, data.get("sensitivity"), code="dataset.sensitivity"
            ),
            logical_ref=str(data["logical_ref"]) if data.get("logical_ref") is not None else None,
        )


def _require_uses(values: Sequence[str]) -> tuple[str, ...]:
    out: list[str] = []
    for item in values:
        require_slug(item, label="prohibited_use")
        out.append(item)
    return tuple(out)


def _detect_entry_problems(entries: Sequence[DatasetEntry]) -> None:
    by_hash: dict[str, list[DatasetEntry]] = {}
    for entry in entries:
        by_hash.setdefault(entry.content_sha256, []).append(entry)
    for group in by_hash.values():
        if len(group) > 1:
            splits = {item.split for item in group}
            if splits & _TRAINISH and splits & _EVAL_SPLITS:
                raise DataContractError(
                    "dataset.split_contamination",
                    "evaluation fixtures must not silently enter training",
                )
            raise DataContractError(
                "dataset.duplicate_hash",
                "duplicate content hashes must be detected",
            )


def _enforce_dataset_policy(
    *,
    source: SourceDescriptor,
    rights: RightsRecord,
    sensitivity: DataSensitivity,
    intended_use: IntendedUse,
    entries: Sequence[DatasetEntry],
    split: DatasetSplit,
) -> None:
    require_unambiguous(
        sensitivity=sensitivity, redistribution=rights.redistribution_permitted is True
    )
    if source.source_type is SourceType.RESEARCH_RESTRICTED and sensitivity in _PUBLICISH:
        raise DataContractError(
            "dataset.research",
            "restricted data cannot be copied into a synthetic or public dataset",
        )
    if rights.research_only and sensitivity in _PUBLICISH:
        raise DataContractError(
            "dataset.research_only",
            "research-only data cannot be emitted as public or synthetic fixtures",
        )
    if any(entry.sensitivity in _RESTRICTEDISH for entry in entries) and sensitivity in _PUBLICISH:
        raise DataContractError(
            "dataset.restricted",
            "restricted data cannot be copied into a synthetic or public dataset",
        )
    if split is not DatasetSplit.UNASSIGNED:
        mismatched = [entry for entry in entries if entry.split != split]
        if mismatched:
            raise DataContractError(
                "dataset.split",
                "entry split must match the dataset split designation",
            )
    if intended_use is IntendedUse.TRAINING and any(
        entry.split in _EVAL_SPLITS for entry in entries
    ):
        raise DataContractError(
            "dataset.split_contamination",
            "evaluation fixtures must not silently enter training",
        )
    if intended_use is IntendedUse.EVALUATION and any(
        entry.split is DatasetSplit.TRAIN for entry in entries
    ):
        raise DataContractError(
            "dataset.split_contamination",
            "training entries cannot be declared as evaluation-only",
        )


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """Catalog of referenced artifacts. Does not bundle media bytes."""

    dataset_id: DatasetId
    name: str
    version: str
    source: SourceDescriptor
    rights: RightsRecord
    sensitivity: DataSensitivity
    entries: tuple[DatasetEntry, ...]
    split: DatasetSplit
    intended_use: IntendedUse
    prohibited_uses: tuple[str, ...]
    content_digests: tuple[str, ...]
    created_at: datetime
    producer: str
    schema_version: str = DATASET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_DATASET_SCHEMA_VERSIONS:
            raise DataContractError("dataset.schema", "unsupported dataset schema version")
        require_slug(self.name, label="dataset_name")
        require_slug(self.version, label="dataset_version")
        require_slug(self.producer, label="producer")
        if not isinstance(self.sensitivity, DataSensitivity):
            raise DataContractError("dataset.sensitivity", "sensitivity is invalid")
        if not isinstance(self.split, DatasetSplit):
            raise DataContractError("dataset.split", "dataset split is invalid")
        if not isinstance(self.intended_use, IntendedUse):
            raise DataContractError("dataset.intended_use", "intended use is invalid")
        require_utc(self.created_at)
        object.__setattr__(self, "prohibited_uses", _require_uses(self.prohibited_uses))
        _detect_entry_problems(self.entries)
        _enforce_dataset_policy(
            source=self.source,
            rights=self.rights,
            sensitivity=self.sensitivity,
            intended_use=self.intended_use,
            entries=self.entries,
            split=self.split,
        )
        expected_id = DatasetId.derive(name=self.name, version=self.version)
        if expected_id != self.dataset_id:
            raise DataContractError("dataset.id", "dataset_id does not match name and version")
        expected_digests = tuple(sorted(entry.content_sha256 for entry in self.entries))
        if expected_digests != self.content_digests:
            raise DataContractError("dataset.digests", "content_digests must match entry hashes")

    def identity_dict(self) -> dict[str, object]:
        return {
            "content_digests": list(self.content_digests),
            "dataset_id": self.dataset_id.value,
            "entries": [
                entry.identity_dict()
                for entry in sorted(
                    self.entries, key=lambda item: (item.content_sha256, item.logical_filename)
                )
            ],
            "intended_use": self.intended_use.value,
            "name": self.name,
            "prohibited_uses": list(self.prohibited_uses),
            "producer": self.producer,
            "rights": self.rights.identity_dict(),
            "schema_version": self.schema_version,
            "sensitivity": self.sensitivity.value,
            "source": self.source.identity_dict(),
            "split": self.split.value,
            "version": self.version,
        }

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.identity_dict())
        data["created_at"] = format_utc(self.created_at)
        data["source"] = self.source.to_dict()
        data["rights"] = self.rights.to_dict()
        data["entries"] = [
            entry.to_dict()
            for entry in sorted(
                self.entries, key=lambda item: (item.content_sha256, item.logical_filename)
            )
        ]
        return {k: data[k] for k in sorted(data)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DatasetManifest:
        created = data.get("created_at")
        if not isinstance(created, str):
            raise DataContractError("dataset.created_at", "created_at is required")
        entries_raw = data.get("entries") or []
        if not isinstance(entries_raw, list):
            raise DataContractError("dataset.entries", "entries must be an array")
        prohibited = data.get("prohibited_uses") or []
        if not isinstance(prohibited, list) or not all(
            isinstance(item, str) for item in prohibited
        ):
            raise DataContractError("dataset.uses", "prohibited_uses must be an array of strings")
        return make_dataset_manifest(
            name=str(data.get("name")),
            version=str(data.get("version")),
            source=SourceDescriptor.from_dict(_as_map(data.get("source"))),
            rights=RightsRecord.from_dict(_as_map(data.get("rights"))),
            sensitivity=parse_enum(
                DataSensitivity, data.get("sensitivity"), code="dataset.sensitivity"
            ),
            entries=tuple(DatasetEntry.from_dict(_as_map(item)) for item in entries_raw),
            split=parse_enum(DatasetSplit, data.get("split"), code="dataset.split"),
            intended_use=parse_enum(
                IntendedUse, data.get("intended_use"), code="dataset.intended_use"
            ),
            prohibited_uses=tuple(prohibited),
            created_at=parse_utc(created),
            producer=str(data.get("producer")),
            schema_version=str(data.get("schema_version", DATASET_SCHEMA_VERSION)),
        )


def make_dataset_manifest(
    *,
    name: str,
    version: str,
    source: SourceDescriptor,
    rights: RightsRecord,
    sensitivity: DataSensitivity,
    entries: tuple[DatasetEntry, ...],
    split: DatasetSplit,
    intended_use: IntendedUse,
    created_at: datetime,
    producer: str,
    prohibited_uses: tuple[str, ...] = (),
    schema_version: str = DATASET_SCHEMA_VERSION,
) -> DatasetManifest:
    dataset_id = DatasetId.derive(name=name, version=version)
    digests = tuple(sorted(entry.content_sha256 for entry in entries))
    return DatasetManifest(
        dataset_id=dataset_id,
        name=name,
        version=version,
        source=source,
        rights=rights,
        sensitivity=sensitivity,
        entries=entries,
        split=split,
        intended_use=intended_use,
        prohibited_uses=prohibited_uses,
        content_digests=digests,
        created_at=created_at,
        producer=producer,
        schema_version=schema_version,
    )


def _as_map(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise DataContractError("dataset.object", "expected object")
    return value
