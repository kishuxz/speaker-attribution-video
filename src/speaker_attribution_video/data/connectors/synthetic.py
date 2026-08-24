"""Deterministic synthetic fixture connector. Project-created content only."""

from __future__ import annotations

import hashlib
from datetime import datetime

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
from speaker_attribution_video.data.connectors.headers import sniff_media_type
from speaker_attribution_video.data.connectors.wav import SyntheticKind, render_fixture
from speaker_attribution_video.data.enums import (
    AcquisitionMethod,
    ConnectorCapability,
    ConnectorFailureReason,
    DataSensitivity,
    IngestionFindingSeverity,
    IngestionState,
    MediaTypeStatus,
    SourceType,
)
from speaker_attribution_video.data.ids import ArtifactId
from speaker_attribution_video.data.manifest import make_media_manifest
from speaker_attribution_video.data.rights import project_fixture_rights
from speaker_attribution_video.data.snapshot import (
    IngestionFinding,
    SnapshotEntry,
    make_ingestion_snapshot,
)
from speaker_attribution_video.data.source import make_source
from speaker_attribution_video.graph.ids import JobId, NamespaceId
from speaker_attribution_video.graph.time import utc_now_for_tests

_VERSION = "0.1.0"
_TRANSCRIPT_NOTE = "speaker-alpha-synthetic-sentence-one"

_KIND_BY_REF = {
    "silence": SyntheticKind.SILENCE,
    "tone": SyntheticKind.TONE,
    "noise": SyntheticKind.NOISE,
    "transcript-text": SyntheticKind.TRANSCRIPT_TEXT,
}


def fixture_bytes(kind: SyntheticKind, *, seed: int = 1, duration_ms: int = 100) -> bytes:
    return render_fixture(kind, seed=seed, duration_ms=duration_ms)


def fixture_digest(kind: SyntheticKind, *, seed: int = 1, duration_ms: int = 100) -> str:
    return hashlib.sha256(fixture_bytes(kind, seed=seed, duration_ms=duration_ms)).hexdigest()


class SyntheticFixtureConnector:
    """Generates original-project synthetic WAV bytes. Not a diarization benchmark."""

    def __init__(
        self, *, seed: int = 1, duration_ms: int = 100, ingested_at: datetime | None = None
    ) -> None:
        self._seed = seed
        self._duration_ms = duration_ms
        self._ingested_at = ingested_at
        self._identity = ConnectorIdentity(
            name="synthetic-fixture",
            version=_VERSION,
            configuration_fingerprint=fingerprint_config(
                {
                    "duration_ms": duration_ms,
                    "seed": seed,
                }
            ),
        )
        self._caps = ConnectorCapabilities(
            synthetic_generation=True,
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
        return self._produce(
            request.context.namespace_id,
            request.context.job_id,
            request.target.logical_ref,
            request.requested_capabilities,
            request.context.input_schema_version,
            cancel,
        )

    def inspect(
        self, request: InspectRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        return self._produce(
            request.context.namespace_id,
            request.context.job_id,
            request.target.logical_ref,
            request.requested_capabilities,
            request.context.input_schema_version,
            cancel,
        )

    def ingest(
        self, request: IngestRequest, *, cancel: CancellationToken | None = None
    ) -> ConnectorResult:
        if not request.targets:
            raise ConnectorError(
                ConnectorFailureReason.INVALID_INPUT, "ingest requires a fixture reference"
            )
        return self._produce(
            request.context.namespace_id,
            request.context.job_id,
            request.targets[0].logical_ref,
            request.requested_capabilities,
            request.context.input_schema_version,
            cancel,
        )

    def _produce(
        self,
        namespace_id: NamespaceId,
        job_id: JobId,
        logical_ref: str,
        requested: frozenset[ConnectorCapability],
        schema: str,
        cancel: CancellationToken | None,
    ) -> ConnectorResult:
        require_input_schema(schema)
        require_connector_capabilities(self._caps, requested)
        if cancel is not None and cancel.is_cancelled():
            raise ConnectorError(ConnectorFailureReason.CANCELLATION, "cancelled")
        slug = logical_ref.rsplit("/", 1)[-1]
        kind = _KIND_BY_REF.get(slug)
        if kind is None:
            raise ConnectorError(
                ConnectorFailureReason.INVALID_INPUT,
                "unknown synthetic fixture",
                details={"fixture": slug},
            )
        payload = fixture_bytes(kind, seed=self._seed, duration_ms=self._duration_ms)
        digest = hashlib.sha256(payload).hexdigest()
        detected = sniff_media_type(payload[:16])
        logical_name = f"synthetic-{kind.value}.wav"
        notes = (
            _TRANSCRIPT_NOTE
            if kind is SyntheticKind.TRANSCRIPT_TEXT
            else "project-synthetic-fixture"
        )
        source = make_source(
            source_type=SourceType.SYNTHETIC,
            provider="project-fixtures",
            logical_ref=f"artifact://synth.example/fixtures/{kind.value}",
            acquisition_method=AcquisitionMethod.GENERATED,
            acquired_at=self._ingested_at or utc_now_for_tests(),
            provenance_notes=notes,
            source_revision=f"seed-{self._seed}",
            source_checksum=digest,
        )
        duration_us = self._duration_ms * 1000
        manifest = make_media_manifest(
            namespace_id=namespace_id,
            job_id=job_id,
            source=source,
            rights=project_fixture_rights(),
            sensitivity=DataSensitivity.SYNTHETIC,
            logical_filename=logical_name,
            media_type_status=MediaTypeStatus.DETECTED if detected else MediaTypeStatus.DECLARED,
            media_type_declared="audio/wav",
            media_type_detected=detected,
            byte_size=len(payload),
            content_sha256=digest,
            ingested_at=self._ingested_at or utc_now_for_tests(),
            connector_name=self._identity.name,
            connector_version=self._identity.version,
            configuration_fingerprint=self._identity.configuration_fingerprint,
            duration_us=duration_us,
        )
        finding = IngestionFinding(
            code="synthetic-not-benchmark",
            severity=IngestionFindingSeverity.INFO,
            message="synthetic-tone-is-not-an-accuracy-benchmark",
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
                    findings=(finding,),
                    manifest_id=manifest.manifest_id,
                ),
            ),
            connector_name=self._identity.name,
            connector_version=self._identity.version,
            created_at=manifest.ingested_at,
            findings=(finding,),
        )
        return ConnectorResult(
            state=IngestionState.ACCEPTED,
            identity=self._identity,
            output_schema_version=self._identity.output_schema_version,
            snapshot=snapshot,
            manifests=(manifest,),
            findings=(finding,),
        )
