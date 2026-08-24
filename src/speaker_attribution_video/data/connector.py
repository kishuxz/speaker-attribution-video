"""Source-neutral DataConnector protocol. No HTTP, S3, Hugging Face, or database I/O."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from speaker_attribution_video.backends.contracts import (
    CancellationToken,
    RequestContext,
    fingerprint_config,
)
from speaker_attribution_video.data.enums import (
    ConnectorCapability,
    ConnectorFailureReason,
    IngestionState,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.manifest import MediaManifest
from speaker_attribution_video.data.snapshot import IngestionFinding, IngestionSnapshot
from speaker_attribution_video.data.versions import (
    CONNECTOR_INPUT_SCHEMA_VERSION,
    CONNECTOR_OUTPUT_SCHEMA_VERSION,
    SUPPORTED_CONNECTOR_INPUT_SCHEMA_VERSIONS,
    SUPPORTED_CONNECTOR_OUTPUT_SCHEMA_VERSIONS,
)
from speaker_attribution_video.graph.errors import redact_for_error
from speaker_attribution_video.graph.ids import require_slug

_BLOCKED_DETAIL_KEYS = frozenset(
    {
        "path",
        "filepath",
        "filename",
        "home",
        "transcript",
        "audio_bytes",
        "video_bytes",
    }
)


@dataclass(frozen=True, slots=True)
class ConnectorCapabilities:
    local_files: bool = False
    directory_manifests: bool = False
    synthetic_generation: bool = False
    external_references: bool = False
    checksum_verification: bool = False
    immutable_snapshots: bool = False
    rights_metadata: bool = False
    sensitivity_enforcement: bool = False

    def offered(self) -> frozenset[ConnectorCapability]:
        return frozenset(cap for cap in ConnectorCapability if bool(getattr(self, cap.value)))

    def supports(self, capability: ConnectorCapability) -> bool:
        return bool(getattr(self, capability.value))


def require_connector_capabilities(
    offered: ConnectorCapabilities, requested: Iterable[ConnectorCapability]
) -> None:
    missing = [cap for cap in requested if not offered.supports(cap)]
    if missing:
        names = ",".join(sorted(cap.value for cap in missing))
        raise ConnectorError(
            ConnectorFailureReason.UNSUPPORTED_CAPABILITY,
            "requested capability is not offered",
            details={"capabilities": names},
        )


def _safe_details(details: Mapping[str, object] | None) -> dict[str, object]:
    if details is None:
        return {}
    out: dict[str, object] = {}
    for key, value in details.items():
        if key.lower() in _BLOCKED_DETAIL_KEYS:
            out[key] = redact_for_error(value)
            continue
        if (
            isinstance(value, str)
            and "/" in value
            and not value.startswith(("artifact://", "d1.id.v1/", "g1.id.v1/", "catalog://"))
        ):
            out[key] = redact_for_error(value)
            continue
        out[key] = value
    return out


class ConnectorError(Exception):
    """Typed connector failure. Default string form is redacted."""

    def __init__(
        self,
        reason: ConnectorFailureReason,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.reason = reason
        self.details = _safe_details(details)
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.reason.value}: {super().__str__()}"


@dataclass(frozen=True, slots=True)
class ConnectorIdentity:
    name: str
    version: str
    configuration_fingerprint: str
    input_schema_version: str = CONNECTOR_INPUT_SCHEMA_VERSION
    output_schema_version: str = CONNECTOR_OUTPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        require_slug(self.name, label="connector_name")
        if not isinstance(self.version, str) or not self.version or len(self.version) > 32:
            raise DataContractError("connector.version", "connector version is invalid")
        if any(ch in self.version for ch in "/\\ \n\r\t"):
            raise DataContractError("connector.version", "connector version is invalid")
        if self.input_schema_version not in SUPPORTED_CONNECTOR_INPUT_SCHEMA_VERSIONS:
            raise DataContractError(
                "connector.schema", "unsupported connector input schema version"
            )
        if self.output_schema_version not in SUPPORTED_CONNECTOR_OUTPUT_SCHEMA_VERSIONS:
            raise DataContractError(
                "connector.schema", "unsupported connector output schema version"
            )

    @property
    def connector_id(self) -> str:
        return f"{self.name}/{self.version}"


@dataclass(frozen=True, slots=True)
class ConnectorRef:
    """Logical media reference. Absolute filesystem paths are not part of the protocol."""

    logical_ref: str
    display_name: str
    content_sha256: str | None = None
    byte_size: int | None = None


@dataclass(frozen=True, slots=True)
class InspectRequest:
    context: RequestContext
    target: ConnectorRef
    requested_capabilities: frozenset[ConnectorCapability] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ValidateRequest:
    context: RequestContext
    target: ConnectorRef
    requested_capabilities: frozenset[ConnectorCapability] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class IngestRequest:
    context: RequestContext
    targets: tuple[ConnectorRef, ...]
    requested_capabilities: frozenset[ConnectorCapability] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class ConnectorResult:
    state: IngestionState
    identity: ConnectorIdentity
    output_schema_version: str
    snapshot: IngestionSnapshot | None = None
    manifests: tuple[MediaManifest, ...] = ()
    findings: tuple[IngestionFinding, ...] = ()
    failure_reason: ConnectorFailureReason | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.state is IngestionState.ACCEPTED:
            if self.failure_reason is not None:
                raise DataContractError(
                    "connector.success", "accepted results cannot carry a failure reason"
                )
            if self.snapshot is None:
                raise DataContractError(
                    "connector.success", "accepted ingestion requires a snapshot"
                )
            if self.snapshot.state is not IngestionState.ACCEPTED:
                raise DataContractError(
                    "connector.success",
                    "partial ingestion must never be recorded as complete success",
                )
        if self.output_schema_version not in SUPPORTED_CONNECTOR_OUTPUT_SCHEMA_VERSIONS:
            raise DataContractError(
                "connector.schema", "unsupported connector output schema version"
            )


@runtime_checkable
class DataConnector(Protocol):
    def identity(self) -> ConnectorIdentity: ...

    def capabilities(self) -> ConnectorCapabilities: ...

    def validate(
        self,
        request: ValidateRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> ConnectorResult: ...

    def inspect(
        self,
        request: InspectRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> ConnectorResult: ...

    def ingest(
        self,
        request: IngestRequest,
        *,
        cancel: CancellationToken | None = None,
    ) -> ConnectorResult: ...

    def close(self) -> None: ...


def require_input_schema(version: str) -> str:
    if version not in SUPPORTED_CONNECTOR_INPUT_SCHEMA_VERSIONS:
        raise ConnectorError(
            ConnectorFailureReason.SCHEMA_MISMATCH,
            "unsupported connector input schema version",
            details={"schema": version},
        )
    return version


__all__ = [
    "CancellationToken",
    "ConnectorCapabilities",
    "ConnectorError",
    "ConnectorIdentity",
    "ConnectorRef",
    "ConnectorResult",
    "DataConnector",
    "IngestRequest",
    "InspectRequest",
    "ValidateRequest",
    "fingerprint_config",
    "require_connector_capabilities",
    "require_input_schema",
]
