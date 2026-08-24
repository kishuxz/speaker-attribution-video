"""Versioned MediaManifest. File contents and absolute paths are never serialized."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from speaker_attribution_video.data.enums import (
    DataSensitivity,
    MediaTypeStatus,
    RedactionState,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.ids import ArtifactId, IngestionEventId, ManifestId
from speaker_attribution_video.data.rights import RightsRecord
from speaker_attribution_video.data.sensitivity import require_unambiguous
from speaker_attribution_video.data.source import SourceDescriptor, reject_filesystem_path
from speaker_attribution_video.data.versions import (
    MANIFEST_SCHEMA_VERSION,
    SUPPORTED_MANIFEST_SCHEMA_VERSIONS,
)
from speaker_attribution_video.graph.enums import parse_enum
from speaker_attribution_video.graph.ids import JobId, NamespaceId, require_hex64, require_slug
from speaker_attribution_video.graph.nodes import require_mime
from speaker_attribution_video.graph.time import (
    format_utc,
    parse_utc,
    require_nonneg_int,
    require_utc,
)

_MAX_WARNING = 256
_MAX_WARNINGS = 16


@dataclass(frozen=True, slots=True)
class StreamMetadata:
    """Optional stream facts supplied externally. D1 does not decode media."""

    sample_rate_hz: int | None = None
    channels: int | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None

    def __post_init__(self) -> None:
        for label, value in (
            ("sample_rate_hz", self.sample_rate_hz),
            ("channels", self.channels),
            ("width", self.width),
            ("height", self.height),
        ):
            if value is not None:
                require_nonneg_int(value, code="stream.field", label=label)
                if value < 1:
                    raise DataContractError("stream.field", f"{label} must be >= 1 when present")
        if self.codec is not None:
            require_slug(self.codec, label="codec")

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.sample_rate_hz is not None:
            data["sample_rate_hz"] = self.sample_rate_hz
        if self.channels is not None:
            data["channels"] = self.channels
        if self.width is not None:
            data["width"] = self.width
        if self.height is not None:
            data["height"] = self.height
        if self.codec is not None:
            data["codec"] = self.codec
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> StreamMetadata:
        codec = data.get("codec")
        if codec is not None and not isinstance(codec, str):
            raise DataContractError("stream.field", "codec expected string")
        return cls(
            sample_rate_hz=_opt_int(data.get("sample_rate_hz")),
            channels=_opt_int(data.get("channels")),
            width=_opt_int(data.get("width")),
            height=_opt_int(data.get("height")),
            codec=codec,
        )


def _warnings(values: Sequence[str]) -> tuple[str, ...]:
    if len(values) > _MAX_WARNINGS:
        raise DataContractError("manifest.warnings", "too many warnings")
    out: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item or len(item) > _MAX_WARNING:
            raise DataContractError("manifest.warnings", "warning must be a short redacted string")
        if any(ch in item for ch in "\n\r\t"):
            raise DataContractError("manifest.warnings", "warning must be a short redacted string")
        reject_filesystem_path(item, label="warning")
        out.append(item)
    return tuple(out)


def _require_connector_version(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 32:
        raise DataContractError("manifest.connector", "connector version is invalid")
    if any(ch in value for ch in "/\\ \n\r\t"):
        raise DataContractError("manifest.connector", "connector version is invalid")
    return value


def manifest_identity_payload(
    *,
    namespace_id: NamespaceId,
    job_id: JobId,
    content_sha256: str,
    source: SourceDescriptor,
    rights: RightsRecord,
    sensitivity: DataSensitivity,
    logical_filename: str,
    media_type_status: MediaTypeStatus,
    byte_size: int,
    connector_name: str,
    connector_version: str,
    configuration_fingerprint: str,
    schema_version: str,
    media_type_declared: str | None,
    media_type_detected: str | None,
    duration_us: int | None,
    audio_stream: StreamMetadata | None,
    video_stream: StreamMetadata | None,
    redaction: RedactionState,
) -> dict[str, object]:
    """Canonical identity fields. Observation timestamps and warnings are excluded.

    Content identity is SHA-256 of source bytes (artifact_id). Manifest identity
    hashes this payload. Changing a display label changes the manifest id but not
    the artifact id. Changing source bytes changes the artifact id.
    """
    artifact_id = ArtifactId.from_digest(content_sha256)
    data: dict[str, object] = {
        "artifact_id": artifact_id.value,
        "byte_size": byte_size,
        "configuration_fingerprint": configuration_fingerprint,
        "connector_name": connector_name,
        "connector_version": connector_version,
        "content_sha256": content_sha256,
        "job_id": job_id.value,
        "logical_filename": logical_filename,
        "media_type_status": media_type_status.value,
        "namespace_id": namespace_id.value,
        "redaction": redaction.value,
        "rights": rights.identity_dict(),
        "schema_version": schema_version,
        "sensitivity": sensitivity.value,
        "source": source.identity_dict(),
    }
    if media_type_declared is not None:
        data["media_type_declared"] = media_type_declared
    if media_type_detected is not None:
        data["media_type_detected"] = media_type_detected
    if duration_us is not None:
        data["duration_us"] = duration_us
    if audio_stream is not None:
        data["audio_stream"] = audio_stream.to_dict()
    if video_stream is not None:
        data["video_stream"] = video_stream.to_dict()
    return data


def _enforce_policy(
    *, source: SourceDescriptor, rights: RightsRecord, sensitivity: DataSensitivity
) -> None:
    require_unambiguous(
        sensitivity=sensitivity,
        redistribution=rights.redistribution_permitted is True,
    )
    if rights.verification is RightsVerification.PROHIBITED:
        raise DataContractError("manifest.prohibited", "prohibited data fails closed at ingest")
    if source.source_type is SourceType.RESEARCH_RESTRICTED:
        if sensitivity in {DataSensitivity.PUBLIC, DataSensitivity.SYNTHETIC}:
            raise DataContractError(
                "manifest.research",
                "research-restricted data cannot be classified public or synthetic",
            )
        if rights.redistribution_permitted is True:
            raise DataContractError(
                "manifest.research",
                "research-restricted data cannot be redistributable",
            )
    if rights.research_only and sensitivity in {DataSensitivity.PUBLIC, DataSensitivity.SYNTHETIC}:
        raise DataContractError(
            "manifest.research_only",
            "research-only data cannot be emitted as public or synthetic fixtures",
        )


@dataclass(frozen=True, slots=True)
class MediaManifest:
    """Immutable description of an ingested artifact. Does not contain file bytes."""

    namespace_id: NamespaceId
    job_id: JobId
    artifact_id: ArtifactId
    manifest_id: ManifestId
    ingestion_event_id: IngestionEventId
    source: SourceDescriptor
    rights: RightsRecord
    sensitivity: DataSensitivity
    logical_filename: str
    media_type_status: MediaTypeStatus
    byte_size: int
    content_sha256: str
    ingested_at: datetime
    connector_name: str
    connector_version: str
    configuration_fingerprint: str
    schema_version: str = MANIFEST_SCHEMA_VERSION
    media_type_declared: str | None = None
    media_type_detected: str | None = None
    duration_us: int | None = None
    audio_stream: StreamMetadata | None = None
    video_stream: StreamMetadata | None = None
    warnings: tuple[str, ...] = ()
    redaction: RedactionState = RedactionState.CONTENTS_EXCLUDED

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
            raise DataContractError("manifest.schema", "unsupported manifest schema version")
        if not isinstance(self.sensitivity, DataSensitivity):
            raise DataContractError("manifest.sensitivity", "sensitivity is invalid")
        if not isinstance(self.media_type_status, MediaTypeStatus):
            raise DataContractError("manifest.media_type", "media type status is invalid")
        if not isinstance(self.redaction, RedactionState):
            raise DataContractError("manifest.redaction", "redaction state is invalid")
        require_slug(self.logical_filename, label="logical_filename")
        reject_filesystem_path(self.logical_filename, label="logical_filename")
        require_nonneg_int(self.byte_size, code="manifest.size", label="byte_size")
        digest = require_hex64(self.content_sha256, label="content_sha256")
        if self.artifact_id.digest != digest:
            raise DataContractError("manifest.artifact", "artifact_id must match content SHA-256")
        if self.duration_us is not None:
            require_nonneg_int(self.duration_us, code="manifest.duration", label="duration_us")
        if self.media_type_declared is not None:
            require_mime(self.media_type_declared)
        if self.media_type_detected is not None:
            require_mime(self.media_type_detected)
        if self.media_type_status is MediaTypeStatus.DECLARED and self.media_type_declared is None:
            raise DataContractError("manifest.media_type", "declared media type is missing")
        if self.media_type_status is MediaTypeStatus.DETECTED and self.media_type_detected is None:
            raise DataContractError("manifest.media_type", "detected media type is missing")
        require_utc(self.ingested_at)
        require_slug(self.connector_name, label="connector_name")
        _require_connector_version(self.connector_version)
        require_hex64(self.configuration_fingerprint, label="configuration_fingerprint")
        _warnings(self.warnings)
        _enforce_policy(source=self.source, rights=self.rights, sensitivity=self.sensitivity)
        expected_manifest = ManifestId.derive(self.identity_dict())
        if expected_manifest != self.manifest_id:
            raise DataContractError(
                "manifest.id", "manifest_id does not match canonical identity fields"
            )
        expected_event = IngestionEventId.derive(
            manifest_id=self.manifest_id,
            ingested_at=format_utc(self.ingested_at),
            connector=self.connector_name,
        )
        if expected_event != self.ingestion_event_id:
            raise DataContractError(
                "manifest.event",
                "ingestion_event_id does not match manifest identity and observation time",
            )

    def identity_dict(self) -> dict[str, object]:
        return manifest_identity_payload(
            namespace_id=self.namespace_id,
            job_id=self.job_id,
            content_sha256=self.content_sha256,
            source=self.source,
            rights=self.rights,
            sensitivity=self.sensitivity,
            logical_filename=self.logical_filename,
            media_type_status=self.media_type_status,
            byte_size=self.byte_size,
            connector_name=self.connector_name,
            connector_version=self.connector_version,
            configuration_fingerprint=self.configuration_fingerprint,
            schema_version=self.schema_version,
            media_type_declared=self.media_type_declared,
            media_type_detected=self.media_type_detected,
            duration_us=self.duration_us,
            audio_stream=self.audio_stream,
            video_stream=self.video_stream,
            redaction=self.redaction,
        )

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.identity_dict())
        data["ingested_at"] = format_utc(self.ingested_at)
        data["ingestion_event_id"] = self.ingestion_event_id.value
        data["manifest_id"] = self.manifest_id.value
        data["warnings"] = list(self.warnings)
        data["source"] = self.source.to_dict()
        data["rights"] = self.rights.to_dict()
        return {k: data[k] for k in sorted(data)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MediaManifest:
        ingested = data.get("ingested_at")
        if not isinstance(ingested, str):
            raise DataContractError("manifest.ingested_at", "ingested_at is required")
        warnings_raw = data.get("warnings") or []
        if not isinstance(warnings_raw, list) or not all(
            isinstance(item, str) for item in warnings_raw
        ):
            raise DataContractError("manifest.warnings", "warnings must be an array of strings")
        audio = data.get("audio_stream")
        video = data.get("video_stream")
        built = make_media_manifest(
            namespace_id=NamespaceId(str(data.get("namespace_id"))),
            job_id=JobId(str(data.get("job_id"))),
            source=SourceDescriptor.from_dict(_as_map(data.get("source"))),
            rights=RightsRecord.from_dict(_as_map(data.get("rights"))),
            sensitivity=parse_enum(
                DataSensitivity, data.get("sensitivity"), code="manifest.sensitivity"
            ),
            logical_filename=str(data.get("logical_filename")),
            media_type_status=parse_enum(
                MediaTypeStatus, data.get("media_type_status"), code="manifest.media_type"
            ),
            byte_size=_require_int(data.get("byte_size"), "byte_size"),
            content_sha256=str(data.get("content_sha256")),
            ingested_at=parse_utc(ingested),
            connector_name=str(data.get("connector_name")),
            connector_version=str(data.get("connector_version")),
            configuration_fingerprint=str(data.get("configuration_fingerprint")),
            schema_version=str(data.get("schema_version", MANIFEST_SCHEMA_VERSION)),
            media_type_declared=_opt_str(data.get("media_type_declared")),
            media_type_detected=_opt_str(data.get("media_type_detected")),
            duration_us=_opt_int(data.get("duration_us")),
            audio_stream=StreamMetadata.from_dict(_as_map(audio)) if audio is not None else None,
            video_stream=StreamMetadata.from_dict(_as_map(video)) if video is not None else None,
            warnings=tuple(warnings_raw),
            redaction=parse_enum(RedactionState, data.get("redaction"), code="manifest.redaction")
            if data.get("redaction") is not None
            else RedactionState.CONTENTS_EXCLUDED,
        )
        _require_matching_id(data.get("manifest_id"), built.manifest_id.value, "manifest.id")
        _require_matching_id(
            data.get("ingestion_event_id"), built.ingestion_event_id.value, "manifest.event"
        )
        _require_matching_id(data.get("artifact_id"), built.artifact_id.value, "manifest.artifact")
        return built


def make_media_manifest(
    *,
    namespace_id: NamespaceId,
    job_id: JobId,
    source: SourceDescriptor,
    rights: RightsRecord,
    sensitivity: DataSensitivity,
    logical_filename: str,
    media_type_status: MediaTypeStatus,
    byte_size: int,
    content_sha256: str,
    ingested_at: datetime,
    connector_name: str,
    connector_version: str,
    configuration_fingerprint: str,
    schema_version: str = MANIFEST_SCHEMA_VERSION,
    media_type_declared: str | None = None,
    media_type_detected: str | None = None,
    duration_us: int | None = None,
    audio_stream: StreamMetadata | None = None,
    video_stream: StreamMetadata | None = None,
    warnings: tuple[str, ...] = (),
    redaction: RedactionState = RedactionState.CONTENTS_EXCLUDED,
) -> MediaManifest:
    digest = require_hex64(content_sha256, label="content_sha256")
    artifact_id = ArtifactId.from_digest(digest)
    payload = manifest_identity_payload(
        namespace_id=namespace_id,
        job_id=job_id,
        content_sha256=digest,
        source=source,
        rights=rights,
        sensitivity=sensitivity,
        logical_filename=logical_filename,
        media_type_status=media_type_status,
        byte_size=byte_size,
        connector_name=connector_name,
        connector_version=connector_version,
        configuration_fingerprint=configuration_fingerprint,
        schema_version=schema_version,
        media_type_declared=media_type_declared,
        media_type_detected=media_type_detected,
        duration_us=duration_us,
        audio_stream=audio_stream,
        video_stream=video_stream,
        redaction=redaction,
    )
    manifest_id = ManifestId.derive(payload)
    event_id = IngestionEventId.derive(
        manifest_id=manifest_id,
        ingested_at=format_utc(ingested_at),
        connector=connector_name,
    )
    return MediaManifest(
        namespace_id=namespace_id,
        job_id=job_id,
        artifact_id=artifact_id,
        manifest_id=manifest_id,
        ingestion_event_id=event_id,
        source=source,
        rights=rights,
        sensitivity=sensitivity,
        logical_filename=logical_filename,
        media_type_status=media_type_status,
        byte_size=byte_size,
        content_sha256=digest,
        ingested_at=ingested_at,
        connector_name=connector_name,
        connector_version=connector_version,
        configuration_fingerprint=configuration_fingerprint,
        schema_version=schema_version,
        media_type_declared=media_type_declared,
        media_type_detected=media_type_detected,
        duration_us=duration_us,
        audio_stream=audio_stream,
        video_stream=video_stream,
        warnings=warnings,
        redaction=redaction,
    )


def _require_matching_id(provided: object, expected: str, code: str) -> None:
    if provided is None:
        return
    if str(provided) != expected:
        raise DataContractError(code, "serialized identifier does not match canonical identity")


def _as_map(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise DataContractError("manifest.object", "expected object")
    return value


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise DataContractError("manifest.field", "expected string")


def _opt_int(value: object) -> int | None:
    if value is None:
        return None
    return _require_int(value, "integer")


def _require_int(value: object, label: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise DataContractError("manifest.field", f"{label} expected integer")
