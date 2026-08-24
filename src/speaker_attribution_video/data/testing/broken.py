"""Broken D1 connectors used only to prove conformance findings.

These are not production connectors.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from speaker_attribution_video.backends.contracts import CancellationToken
from speaker_attribution_video.data.connector import (
    ConnectorError,
    ConnectorResult,
    InspectRequest,
)
from speaker_attribution_video.data.connectors.local import LocalFileConnector
from speaker_attribution_video.data.connectors.synthetic import SyntheticFixtureConnector
from speaker_attribution_video.data.enums import (
    ConnectorFailureReason,
    DataSensitivity,
    IngestionState,
)
from speaker_attribution_video.data.graph import graph_from_accepted_ingestion
from speaker_attribution_video.data.ids import SnapshotId
from speaker_attribution_video.data.manifest import MediaManifest, make_media_manifest
from speaker_attribution_video.data.rights import project_fixture_rights
from speaker_attribution_video.data.snapshot import (
    IngestionSnapshot,
    SnapshotEntry,
    make_ingestion_snapshot,
)
from speaker_attribution_video.data.store import ManifestSnapshotStore
from speaker_attribution_video.graph.ids import JobId, NamespaceId


def _rebuild_manifest(result: ConnectorResult, **changes: object) -> MediaManifest:
    current = result.manifests[0]
    fields = {
        "namespace_id": current.namespace_id,
        "job_id": current.job_id,
        "source": current.source,
        "rights": current.rights,
        "sensitivity": current.sensitivity,
        "logical_filename": current.logical_filename,
        "media_type_status": current.media_type_status,
        "media_type_declared": current.media_type_declared,
        "media_type_detected": current.media_type_detected,
        "byte_size": current.byte_size,
        "content_sha256": current.content_sha256,
        "ingested_at": current.ingested_at,
        "connector_name": current.connector_name,
        "connector_version": current.connector_version,
        "configuration_fingerprint": current.configuration_fingerprint,
        "duration_us": current.duration_us,
    }
    fields.update(changes)
    return make_media_manifest(**fields)  # type: ignore[arg-type]


class ConstantHashConnector(SyntheticFixtureConnector):
    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        result = super().inspect(request, cancel=cancel)
        return replace(result, manifests=(_rebuild_manifest(result, content_sha256="a" * 64),))


class IgnoreInputConnector(SyntheticFixtureConnector):
    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        forced = InspectRequest(
            context=request.context,
            target=replace(request.target, logical_ref="tone"),
            requested_capabilities=request.requested_capabilities,
            rights=request.rights,
            sensitivity=request.sensitivity,
        )
        return super().inspect(forced, cancel=cancel)


class NamespaceRewritingConnector(SyntheticFixtureConnector):
    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        other_ns = NamespaceId.from_slug("other.example")
        other = InspectRequest(
            context=replace(
                request.context,
                namespace_id=other_ns,
                job_id=JobId.derive(other_ns, "job99"),
            ),
            target=request.target,
            requested_capabilities=request.requested_capabilities,
            rights=request.rights,
            sensitivity=request.sensitivity,
        )
        return super().inspect(other, cancel=cancel)


class SensitivityDowngradeConnector(SyntheticFixtureConnector):
    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        result = super().inspect(request, cancel=cancel)
        return replace(
            result,
            manifests=(_rebuild_manifest(result, sensitivity=DataSensitivity.PUBLIC),),
        )


class UnknownRightsRedistributableConnector(LocalFileConnector):
    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        forced = InspectRequest(
            context=request.context,
            target=request.target,
            requested_capabilities=request.requested_capabilities,
            rights=project_fixture_rights(),
            sensitivity=request.sensitivity,
            declared_media_type=request.declared_media_type,
            known_duration_us=request.known_duration_us,
        )
        return super().inspect(forced, cancel=cancel)


class PartialAsSuccessConnector(SyntheticFixtureConnector):
    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        result = super().inspect(request, cancel=cancel)
        if result.snapshot is None:
            raise ConnectorError(
                ConnectorFailureReason.INVALID_INPUT,
                "broken connector missing snapshot",
            )
        rejected = SnapshotEntry(
            artifact_id=result.snapshot.entries[0].artifact_id,
            content_sha256=result.snapshot.entries[0].content_sha256,
            logical_filename="synthetic-tone-02.wav",
            state=IngestionState.REJECTED,
        )
        mixed = make_ingestion_snapshot(
            namespace_id=result.snapshot.namespace_id,
            job_id=result.snapshot.job_id,
            entries=(result.snapshot.entries[0], rejected),
            connector_name=result.snapshot.connector_name,
            connector_version=result.snapshot.connector_version,
            created_at=result.snapshot.created_at,
            findings=result.snapshot.findings,
        )
        obj = object.__new__(ConnectorResult)
        object.__setattr__(obj, "state", IngestionState.ACCEPTED)
        object.__setattr__(obj, "identity", result.identity)
        object.__setattr__(obj, "output_schema_version", result.output_schema_version)
        object.__setattr__(obj, "snapshot", mixed)
        object.__setattr__(obj, "manifests", result.manifests)
        object.__setattr__(obj, "findings", result.findings)
        object.__setattr__(obj, "failure_reason", None)
        object.__setattr__(obj, "message", None)
        return obj


class MutatingConnector(SyntheticFixtureConnector):
    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        metadata = request.context.metadata
        if isinstance(metadata, dict):
            metadata["mutated"] = True
        return super().inspect(request, cancel=cancel)


class PathLeakingConnector(SyntheticFixtureConnector):
    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        if ".." in request.target.logical_ref or request.target.logical_ref.startswith("/"):
            raise ConnectorError(
                ConnectorFailureReason.INVALID_INPUT,
                "/Users/secret/private.wav",
            )
        return super().inspect(request, cancel=cancel)


class SymlinkEscapeConnector(LocalFileConnector):
    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        target = Path(self._root) / request.target.logical_ref
        if target.is_symlink():
            escaped = target.resolve()
            inside = Path(self._root) / "followed.wav"
            inside.write_bytes(escaped.read_bytes())
            request = InspectRequest(
                context=request.context,
                target=replace(request.target, logical_ref="followed.wav"),
                requested_capabilities=request.requested_capabilities,
                rights=request.rights,
                sensitivity=request.sensitivity,
            )
        return super().inspect(request, cancel=cancel)


class OverwritingSnapshotStore(ManifestSnapshotStore):
    def put_snapshot(self, snapshot: IngestionSnapshot) -> SnapshotId:
        from speaker_attribution_video.data.serialize import canonical_dumps_snapshot

        payload = canonical_dumps_snapshot(snapshot).encode()
        digest = snapshot.snapshot_id.digest
        target = self._path("snapshots", digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return snapshot.snapshot_id


def unsafe_graph_from_rejected(
    manifest: MediaManifest, snapshot: IngestionSnapshot, created_at: datetime
) -> object:
    """Broken projector: builds a graph even when ingestion was not accepted."""
    if snapshot.state is IngestionState.ACCEPTED:
        return graph_from_accepted_ingestion(
            manifest=manifest, snapshot=snapshot, created_at=created_at
        )
    forced_entries = tuple(
        replace(entry, state=IngestionState.ACCEPTED) for entry in snapshot.entries
    )
    forced = make_ingestion_snapshot(
        namespace_id=snapshot.namespace_id,
        job_id=snapshot.job_id,
        entries=forced_entries,
        connector_name=snapshot.connector_name,
        connector_version=snapshot.connector_version,
        created_at=created_at,
    )
    return graph_from_accepted_ingestion(manifest=manifest, snapshot=forced, created_at=created_at)
