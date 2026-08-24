"""Local-file connector. Hashes bytes; does not decode audio/video or copy media."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path

from speaker_attribution_video.backends.contracts import CancellationToken, fingerprint_config
from speaker_attribution_video.data.connector import (
    ConnectorCapabilities,
    ConnectorError,
    ConnectorIdentity,
    ConnectorResult,
    IngestRequest,
    InspectRequest,
    ValidateRequest,
    require_connector_capabilities,
    require_input_schema,
)
from speaker_attribution_video.data.connectors.headers import HEADER_BYTES, sniff_media_type
from speaker_attribution_video.data.connectors.paths import (
    require_regular_file,
    resolve_inside_root,
)
from speaker_attribution_video.data.enums import (
    AcquisitionMethod,
    ConnectorCapability,
    ConnectorFailureReason,
    DataSensitivity,
    IngestionFindingSeverity,
    IngestionState,
    MediaTypeStatus,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.ids import ArtifactId
from speaker_attribution_video.data.manifest import MediaManifest, make_media_manifest
from speaker_attribution_video.data.rights import RightsRecord
from speaker_attribution_video.data.snapshot import (
    IngestionFinding,
    SnapshotEntry,
    make_ingestion_snapshot,
)
from speaker_attribution_video.data.source import make_source
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.ids import JobId, NamespaceId, require_slug
from speaker_attribution_video.graph.time import utc_now_for_tests

_SLUG_FALLBACK = "user-file"
_CHUNK_DEFAULT = 65_536
_MAX_BYTES_DEFAULT = 10_000_000
_VERSION = "0.1.0"


def safe_logical_name(filename: str) -> str:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", filename.lower()).strip("-._")
    if not cleaned:
        return _SLUG_FALLBACK
    try:
        return require_slug(cleaned, label="logical_filename")
    except GraphContractError:
        return _SLUG_FALLBACK


class LocalFileConnector:
    """User-supplied local files inside an explicitly configured allowed root."""

    def __init__(
        self,
        *,
        allowed_root: Path,
        max_bytes: int = _MAX_BYTES_DEFAULT,
        chunk_size: int = _CHUNK_DEFAULT,
        require_rights: bool = True,
        ingested_at: datetime | None = None,
    ) -> None:
        if max_bytes < 1 or chunk_size < 1:
            raise ConnectorError(
                ConnectorFailureReason.UNSAFE_CONFIGURATION,
                "size bounds are invalid",
            )
        self._root = allowed_root
        self._max_bytes = max_bytes
        self._chunk_size = chunk_size
        self._require_rights = require_rights
        self._ingested_at = ingested_at
        root_digest = hashlib.sha256(str(allowed_root).encode("utf-8")).hexdigest()
        self._identity = ConnectorIdentity(
            name="local-file",
            version=_VERSION,
            configuration_fingerprint=fingerprint_config(
                {
                    "chunk_size": chunk_size,
                    "max_bytes": max_bytes,
                    "require_rights": require_rights,
                    "root_sha256": root_digest,
                }
            ),
        )
        self._caps = ConnectorCapabilities(
            local_files=True,
            checksum_verification=True,
            immutable_snapshots=True,
            rights_metadata=True,
            sensitivity_enforcement=True,
        )

    def identity(self) -> ConnectorIdentity:
        return self._identity

    def capabilities(self) -> ConnectorCapabilities:
        return self._caps

    def close(self) -> None:
        return

    def validate(
        self, request: ValidateRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        return self._run_one(
            namespace_id=request.context.namespace_id,
            job_id=request.context.job_id,
            schema=request.context.input_schema_version,
            requested=request.requested_capabilities,
            relative=request.target.logical_ref,
            rights=request.rights,
            sensitivity=request.sensitivity,
            declared_media_type=None,
            known_duration_us=None,
            cancel=cancel,
            ingest=False,
        )

    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        return self._run_one(
            namespace_id=request.context.namespace_id,
            job_id=request.context.job_id,
            schema=request.context.input_schema_version,
            requested=request.requested_capabilities,
            relative=request.target.logical_ref,
            rights=request.rights,
            sensitivity=request.sensitivity,
            declared_media_type=request.declared_media_type,
            known_duration_us=request.known_duration_us,
            cancel=cancel,
            ingest=False,
        )

    def ingest(
        self, request: IngestRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        require_input_schema(request.context.input_schema_version)
        require_connector_capabilities(self._caps, request.requested_capabilities)
        entries: list[SnapshotEntry] = []
        manifests: list[MediaManifest] = []
        findings: list[IngestionFinding] = []
        for target in request.targets:
            if cancel is not None and cancel.is_cancelled():
                raise ConnectorError(ConnectorFailureReason.CANCELLATION, "cancelled")
            try:
                result = self._run_one(
                    namespace_id=request.context.namespace_id,
                    job_id=request.context.job_id,
                    schema=request.context.input_schema_version,
                    requested=request.requested_capabilities,
                    relative=target.logical_ref,
                    rights=request.rights,
                    sensitivity=request.sensitivity,
                    declared_media_type=request.declared_media_type,
                    known_duration_us=request.known_duration_us,
                    cancel=cancel,
                    ingest=True,
                )
            except ConnectorError as exc:
                if len(request.targets) == 1:
                    raise
                logical = safe_logical_name(Path(target.logical_ref).name)
                finding = IngestionFinding(
                    code=exc.reason.value.replace("_", "-"),
                    severity=IngestionFindingSeverity.ERROR,
                    message="local-file-rejected",
                )
                findings.append(finding)
                marker = hashlib.sha256(f"d1.unobserved.v1|{logical}".encode()).hexdigest()
                entries.append(
                    SnapshotEntry(
                        artifact_id=ArtifactId.from_digest(marker),
                        content_sha256=marker,
                        logical_filename=logical,
                        state=IngestionState.REJECTED,
                        findings=(finding,),
                    )
                )
                continue
            entries.extend(result.snapshot.entries if result.snapshot is not None else ())
            manifests.extend(result.manifests)
            findings.extend(result.findings)
        if not entries and findings:
            snapshot = make_ingestion_snapshot(
                namespace_id=request.context.namespace_id,
                job_id=request.context.job_id,
                entries=(),
                connector_name=self._identity.name,
                connector_version=self._identity.version,
                created_at=self._ingested_at or utc_now_for_tests(),
                findings=tuple(findings),
            )
            return ConnectorResult(
                state=snapshot.state,
                identity=self._identity,
                output_schema_version=self._identity.output_schema_version,
                snapshot=snapshot,
                findings=tuple(findings),
                failure_reason=ConnectorFailureReason.INVALID_INPUT,
                message="local-file-rejected",
            )
        snapshot = make_ingestion_snapshot(
            namespace_id=request.context.namespace_id,
            job_id=request.context.job_id,
            entries=tuple(entries),
            connector_name=self._identity.name,
            connector_version=self._identity.version,
            created_at=self._ingested_at or utc_now_for_tests(),
            findings=tuple(findings),
        )
        return ConnectorResult(
            state=snapshot.state,
            identity=self._identity,
            output_schema_version=self._identity.output_schema_version,
            snapshot=snapshot,
            manifests=tuple(manifests),
            findings=tuple(findings),
        )

    def _run_one(
        self,
        *,
        namespace_id: NamespaceId,
        job_id: JobId,
        schema: str,
        requested: frozenset[ConnectorCapability],
        relative: str,
        rights: RightsRecord | None,
        sensitivity: DataSensitivity | None,
        declared_media_type: str | None,
        known_duration_us: int | None,
        cancel: CancellationToken | None,
        ingest: bool,
    ) -> ConnectorResult:
        require_input_schema(schema)
        require_connector_capabilities(self._caps, requested)
        if cancel is not None and cancel.is_cancelled():
            raise ConnectorError(ConnectorFailureReason.CANCELLATION, "cancelled")
        if self._require_rights and rights is None:
            raise ConnectorError(
                ConnectorFailureReason.POLICY_REJECTION,
                "rights metadata is required",
            )
        resolved = resolve_inside_root(self._root, relative)
        info = require_regular_file(resolved)
        if info.st_size > self._max_bytes:
            raise ConnectorError(
                ConnectorFailureReason.RESOURCE_LIMIT,
                "file exceeds configured maximum size",
            )
        digest, byte_size, header, nlink = self._hash_file(resolved, expected=info)
        logical_name = safe_logical_name(Path(relative).name)
        detected = sniff_media_type(header)
        if detected is not None:
            media_status = MediaTypeStatus.DETECTED
            media_detected = detected
        elif declared_media_type is not None:
            media_status = MediaTypeStatus.DECLARED
            media_detected = None
        else:
            media_status = MediaTypeStatus.UNKNOWN
            media_detected = None
        warnings: list[str] = []
        if nlink > 1:
            warnings.append("hard-link-shared-inode")
        source = make_source(
            source_type=SourceType.LOCAL_USER_FILE,
            provider="caller",
            logical_ref=f"userfile://entry/{logical_name}",
            acquisition_method=AcquisitionMethod.USER_COPY,
            acquired_at=self._ingested_at or utc_now_for_tests(),
        )
        used_rights = (
            rights
            if rights is not None
            else RightsRecord(verification=RightsVerification.UNVERIFIED)
        )
        used_sensitivity = sensitivity if sensitivity is not None else DataSensitivity.UNKNOWN
        try:
            manifest = make_media_manifest(
                namespace_id=namespace_id,
                job_id=job_id,
                source=source,
                rights=used_rights,
                sensitivity=used_sensitivity,
                logical_filename=logical_name,
                media_type_status=media_status,
                media_type_declared=declared_media_type,
                media_type_detected=media_detected,
                byte_size=byte_size,
                content_sha256=digest,
                ingested_at=self._ingested_at or utc_now_for_tests(),
                connector_name=self._identity.name,
                connector_version=self._identity.version,
                configuration_fingerprint=self._identity.configuration_fingerprint,
                duration_us=known_duration_us,
                warnings=tuple(warnings),
            )
        except (GraphContractError, ConnectorError) as exc:
            raise ConnectorError(
                ConnectorFailureReason.POLICY_REJECTION,
                "manifest was rejected by data policy",
            ) from exc
        findings = tuple(
            IngestionFinding(
                code="hard-link-shared-inode",
                severity=IngestionFindingSeverity.INFO,
                message="path-uniqueness-is-not-content-uniqueness",
            )
            for _ in warnings
        )
        snapshot = make_ingestion_snapshot(
            namespace_id=namespace_id,
            job_id=job_id,
            entries=(
                SnapshotEntry(
                    artifact_id=ArtifactId.from_digest(digest),
                    content_sha256=digest,
                    logical_filename=logical_name,
                    state=IngestionState.ACCEPTED,
                    findings=findings,
                    manifest_id=manifest.manifest_id,
                ),
            ),
            connector_name=self._identity.name,
            connector_version=self._identity.version,
            created_at=manifest.ingested_at,
            findings=findings,
        )
        _ = ingest
        return ConnectorResult(
            state=IngestionState.ACCEPTED,
            identity=self._identity,
            output_schema_version=self._identity.output_schema_version,
            snapshot=snapshot,
            manifests=(manifest,),
            findings=findings,
        )

    def _hash_file(self, path: Path, *, expected: os.stat_result) -> tuple[str, int, bytes, int]:
        before = path.stat()
        if before.st_size != expected.st_size:
            raise ConnectorError(
                ConnectorFailureReason.CHANGED_DURING_READ,
                "file changed during inspection",
            )
        digest = hashlib.sha256()
        header = b""
        size = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(self._chunk_size)
                if not chunk:
                    break
                if size == 0:
                    header = chunk[:HEADER_BYTES]
                size += len(chunk)
                if size > self._max_bytes:
                    raise ConnectorError(
                        ConnectorFailureReason.RESOURCE_LIMIT,
                        "file exceeds configured maximum size",
                    )
                digest.update(chunk)
        after = path.stat()
        if (
            before.st_mtime_ns != after.st_mtime_ns
            or before.st_size != after.st_size
            or before.st_ino != after.st_ino
            or size != before.st_size
        ):
            raise ConnectorError(
                ConnectorFailureReason.CHANGED_DURING_READ,
                "file changed during inspection",
            )
        return digest.hexdigest(), size, header, int(before.st_nlink)
