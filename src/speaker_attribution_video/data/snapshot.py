"""Immutable ingestion snapshot contracts. Snapshots store manifests, not media."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from speaker_attribution_video.data.enums import IngestionFindingSeverity, IngestionState
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.ids import ArtifactId, ManifestId, SnapshotId
from speaker_attribution_video.data.source import reject_filesystem_path
from speaker_attribution_video.data.versions import (
    SNAPSHOT_SCHEMA_VERSION,
    SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS,
)
from speaker_attribution_video.graph.enums import parse_enum
from speaker_attribution_video.graph.ids import JobId, NamespaceId, require_hex64, require_slug
from speaker_attribution_video.graph.time import format_utc, parse_utc, require_utc

_SUCCESS = IngestionState.ACCEPTED
_MAX_FINDINGS = 64
_MAX_MESSAGE = 256


@dataclass(frozen=True, slots=True)
class IngestionFinding:
    code: str
    severity: IngestionFindingSeverity
    message: str

    def __post_init__(self) -> None:
        require_slug(self.code, label="finding_code")
        if not isinstance(self.severity, IngestionFindingSeverity):
            raise DataContractError("snapshot.finding", "finding severity is invalid")
        if (
            not isinstance(self.message, str)
            or not self.message
            or len(self.message) > _MAX_MESSAGE
        ):
            raise DataContractError(
                "snapshot.finding", "finding message must be a short redacted string"
            )
        if any(ch in self.message for ch in "\n\r\t"):
            raise DataContractError(
                "snapshot.finding", "finding message must be a short redacted string"
            )
        reject_filesystem_path(self.message, label="finding")

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "severity": self.severity.value}

    def identity_dict(self) -> dict[str, object]:
        return self.to_dict()

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> IngestionFinding:
        return cls(
            code=str(data.get("code")),
            severity=parse_enum(
                IngestionFindingSeverity, data.get("severity"), code="snapshot.finding"
            ),
            message=str(data.get("message")),
        )


def _findings(values: Sequence[IngestionFinding]) -> tuple[IngestionFinding, ...]:
    if len(values) > _MAX_FINDINGS:
        raise DataContractError("snapshot.findings", "too many findings")
    return tuple(values)


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    artifact_id: ArtifactId
    content_sha256: str
    logical_filename: str
    state: IngestionState
    findings: tuple[IngestionFinding, ...] = ()
    manifest_id: ManifestId | None = None

    def __post_init__(self) -> None:
        digest = require_hex64(self.content_sha256, label="content_sha256")
        if self.artifact_id.digest != digest:
            raise DataContractError("snapshot.entry", "artifact_id must match content SHA-256")
        require_slug(self.logical_filename, label="logical_filename")
        reject_filesystem_path(self.logical_filename, label="logical_filename")
        if not isinstance(self.state, IngestionState):
            raise DataContractError("snapshot.state", "ingestion state is invalid")
        object.__setattr__(self, "findings", _findings(self.findings))
        if self.state is _SUCCESS and any(
            finding.severity is IngestionFindingSeverity.ERROR for finding in self.findings
        ):
            raise DataContractError(
                "snapshot.success",
                "accepted entries cannot carry error findings",
            )

    def identity_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "artifact_id": self.artifact_id.value,
            "content_sha256": self.content_sha256,
            "finding_codes": [finding.code for finding in self.findings],
            "logical_filename": self.logical_filename,
            "state": self.state.value,
        }
        if self.manifest_id is not None:
            data["manifest_id"] = self.manifest_id.value
        return data

    def to_dict(self) -> dict[str, Any]:
        data = self.identity_dict()
        data.pop("finding_codes", None)
        data["findings"] = [finding.to_dict() for finding in self.findings]
        return {k: data[k] for k in sorted(data)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SnapshotEntry:
        digest = str(data.get("content_sha256"))
        findings_raw = data.get("findings") or []
        if not isinstance(findings_raw, list):
            raise DataContractError("snapshot.findings", "findings must be an array")
        manifest = data.get("manifest_id")
        return cls(
            artifact_id=ArtifactId.from_digest(digest),
            content_sha256=digest,
            logical_filename=str(data.get("logical_filename")),
            state=parse_enum(IngestionState, data.get("state"), code="snapshot.state"),
            findings=tuple(IngestionFinding.from_dict(item) for item in findings_raw),
            manifest_id=ManifestId(str(manifest)) if manifest is not None else None,
        )


def derive_snapshot_state(entry_states: Sequence[IngestionState]) -> IngestionState:
    if not entry_states:
        return IngestionState.REJECTED
    unique = frozenset(entry_states)
    if unique == {_SUCCESS}:
        return IngestionState.ACCEPTED
    if _SUCCESS in unique:
        return IngestionState.PARTIAL
    if unique == {IngestionState.DEGRADED}:
        return IngestionState.DEGRADED
    if unique == {IngestionState.FAILED_VALIDATION}:
        return IngestionState.FAILED_VALIDATION
    if unique == {IngestionState.FAILED_POLICY}:
        return IngestionState.FAILED_POLICY
    if unique == {IngestionState.REJECTED}:
        return IngestionState.REJECTED
    return IngestionState.PARTIAL


def snapshot_identity_payload(
    *,
    namespace_id: NamespaceId,
    job_id: JobId,
    entries: Sequence[SnapshotEntry],
    state: IngestionState,
    connector_name: str,
    connector_version: str,
    schema_version: str,
    findings: Sequence[IngestionFinding],
    finalized: bool,
) -> dict[str, object]:
    return {
        "connector_name": connector_name,
        "connector_version": connector_version,
        "entries": [
            entry.identity_dict()
            for entry in sorted(
                entries, key=lambda item: (item.content_sha256, item.logical_filename)
            )
        ],
        "finalized": finalized,
        "finding_codes": [finding.code for finding in findings],
        "job_id": job_id.value,
        "namespace_id": namespace_id.value,
        "schema_version": schema_version,
        "state": state.value,
    }


@dataclass(frozen=True, slots=True)
class IngestionSnapshot:
    """Append-only after finalization. Failed entries remain visible."""

    snapshot_id: SnapshotId
    namespace_id: NamespaceId
    job_id: JobId
    entries: tuple[SnapshotEntry, ...]
    state: IngestionState
    connector_name: str
    connector_version: str
    created_at: datetime
    finalized: bool = True
    findings: tuple[IngestionFinding, ...] = ()
    schema_version: str = SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_SNAPSHOT_SCHEMA_VERSIONS:
            raise DataContractError("snapshot.schema", "unsupported snapshot schema version")
        if not isinstance(self.state, IngestionState):
            raise DataContractError("snapshot.state", "ingestion state is invalid")
        require_slug(self.connector_name, label="connector_name")
        if not isinstance(self.connector_version, str) or not self.connector_version:
            raise DataContractError("snapshot.connector", "connector version is invalid")
        if any(ch in self.connector_version for ch in "/\\ \n\r\t"):
            raise DataContractError("snapshot.connector", "connector version is invalid")
        require_utc(self.created_at)
        object.__setattr__(self, "findings", _findings(self.findings))
        derived = derive_snapshot_state(tuple(entry.state for entry in self.entries))
        if derived != self.state:
            raise DataContractError(
                "snapshot.state",
                "snapshot state must be derived from entry states",
            )
        if self.state is _SUCCESS:
            if not self.entries:
                raise DataContractError("snapshot.success", "accepted snapshots require entries")
            if any(entry.state is not _SUCCESS for entry in self.entries):
                raise DataContractError(
                    "snapshot.success",
                    "partial ingestion must never be recorded as complete success",
                )
            if any(finding.severity is IngestionFindingSeverity.ERROR for finding in self.findings):
                raise DataContractError(
                    "snapshot.success",
                    "accepted snapshots cannot carry error findings",
                )
        expected = SnapshotId.derive(self.identity_dict())
        if expected != self.snapshot_id:
            raise DataContractError("snapshot.id", "snapshot_id does not match canonical identity")

    def identity_dict(self) -> dict[str, object]:
        return snapshot_identity_payload(
            namespace_id=self.namespace_id,
            job_id=self.job_id,
            entries=self.entries,
            state=self.state,
            connector_name=self.connector_name,
            connector_version=self.connector_version,
            schema_version=self.schema_version,
            findings=self.findings,
            finalized=self.finalized,
        )

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.identity_dict())
        data.pop("finding_codes", None)
        data["created_at"] = format_utc(self.created_at)
        data["snapshot_id"] = self.snapshot_id.value
        data["entries"] = [entry.to_dict() for entry in self.entries]
        data["findings"] = [finding.to_dict() for finding in self.findings]
        return {k: data[k] for k in sorted(data)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> IngestionSnapshot:
        created = data.get("created_at")
        if not isinstance(created, str):
            raise DataContractError("snapshot.created_at", "created_at is required")
        entries_raw = data.get("entries") or []
        findings_raw = data.get("findings") or []
        if not isinstance(entries_raw, list) or not isinstance(findings_raw, list):
            raise DataContractError("snapshot.entries", "entries and findings must be arrays")
        return make_ingestion_snapshot(
            namespace_id=NamespaceId(str(data.get("namespace_id"))),
            job_id=JobId(str(data.get("job_id"))),
            entries=tuple(SnapshotEntry.from_dict(item) for item in entries_raw),
            connector_name=str(data.get("connector_name")),
            connector_version=str(data.get("connector_version")),
            created_at=parse_utc(created),
            finalized=bool(data.get("finalized", True)),
            findings=tuple(IngestionFinding.from_dict(item) for item in findings_raw),
            schema_version=str(data.get("schema_version", SNAPSHOT_SCHEMA_VERSION)),
        )


def make_ingestion_snapshot(
    *,
    namespace_id: NamespaceId,
    job_id: JobId,
    entries: tuple[SnapshotEntry, ...],
    connector_name: str,
    connector_version: str,
    created_at: datetime,
    finalized: bool = True,
    findings: tuple[IngestionFinding, ...] = (),
    schema_version: str = SNAPSHOT_SCHEMA_VERSION,
) -> IngestionSnapshot:
    state = derive_snapshot_state(tuple(entry.state for entry in entries))
    payload = snapshot_identity_payload(
        namespace_id=namespace_id,
        job_id=job_id,
        entries=entries,
        state=state,
        connector_name=connector_name,
        connector_version=connector_version,
        schema_version=schema_version,
        findings=findings,
        finalized=finalized,
    )
    return IngestionSnapshot(
        snapshot_id=SnapshotId.derive(payload),
        namespace_id=namespace_id,
        job_id=job_id,
        entries=entries,
        state=state,
        connector_name=connector_name,
        connector_version=connector_version,
        created_at=created_at,
        finalized=finalized,
        findings=findings,
        schema_version=schema_version,
    )
