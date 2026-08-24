"""Versioned media inspection and normalization request/result contracts."""

from __future__ import annotations

from dataclasses import dataclass

from speaker_attribution_video.backends.contracts import RequestContext
from speaker_attribution_video.data.manifest import MediaManifest
from speaker_attribution_video.graph.ids import require_hex64
from speaker_attribution_video.graph.time import require_nonneg_int
from speaker_attribution_video.media.enums import (
    CaptureStatus,
    MediaStepState,
    StreamKind,
    StreamSelectionReason,
    ToolLogicalName,
)
from speaker_attribution_video.media.errors import MediaContractError
from speaker_attribution_video.media.identity import MediaToolchainFingerprint
from speaker_attribution_video.media.versions import (
    INSPECTION_INPUT_SCHEMA_VERSION,
    NORMALIZATION_INPUT_SCHEMA_VERSION,
    SUBPROCESS_POLICY_VERSION,
    SUPPORTED_INSPECTION_INPUT_SCHEMA_VERSIONS,
    SUPPORTED_INSPECTION_SCHEMA_VERSIONS,
    SUPPORTED_NORMALIZATION_INPUT_SCHEMA_VERSIONS,
    SUPPORTED_NORMALIZATION_SCHEMA_VERSIONS,
)

_MAX_WARNINGS = 16
_MAX_WARNING = 128
_RELATIVE_REF_MAX = 256


def _require_relative_ref(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _RELATIVE_REF_MAX:
        raise MediaContractError("media.ref", "source reference is invalid")
    if value.startswith(("/", "\\")) or ".." in value or "\\" in value or "://" in value:
        raise MediaContractError("media.ref", "source reference must be a relative logical name")
    if "\x00" in value:
        raise MediaContractError("media.ref", "source reference is invalid")
    return value


def _require_warnings(warnings: tuple[str, ...]) -> tuple[str, ...]:
    if len(warnings) > _MAX_WARNINGS:
        raise MediaContractError("media.warnings", "too many warnings")
    cleaned: list[str] = []
    for item in warnings:
        if not isinstance(item, str) or not item or len(item) > _MAX_WARNING:
            raise MediaContractError("media.warnings", "warning is invalid")
        if "/" in item or "\\" in item:
            raise MediaContractError("media.warnings", "warning must not include paths")
        cleaned.append(item)
    return tuple(cleaned)


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    logical_name: ToolLogicalName
    policy_version: str
    duration_us: int
    exit_status: int | None
    stdout_status: CaptureStatus
    stderr_status: CaptureStatus
    stdout_bytes: int
    stderr_bytes: int
    stdout_sha256: str | None
    stderr_sha256: str | None
    timed_out: bool
    cancelled: bool
    launch_attempts: int

    def __post_init__(self) -> None:
        if not isinstance(self.logical_name, ToolLogicalName):
            raise MediaContractError("tool.name", "tool logical name is invalid")
        if self.policy_version != SUBPROCESS_POLICY_VERSION:
            raise MediaContractError("subprocess.schema", "unsupported subprocess policy version")
        require_nonneg_int(self.duration_us, code="tool.duration", label="duration_us")
        if self.exit_status is not None:
            if not isinstance(self.exit_status, int) or isinstance(self.exit_status, bool):
                raise MediaContractError("tool.exit", "exit status is invalid")
            if self.exit_status < 0 or self.exit_status > 255:
                raise MediaContractError("tool.exit", "exit status is invalid")
        for label, status in (
            ("stdout_status", self.stdout_status),
            ("stderr_status", self.stderr_status),
        ):
            if not isinstance(status, CaptureStatus):
                raise MediaContractError("tool.capture", f"{label} is invalid")
        require_nonneg_int(self.stdout_bytes, code="tool.capture", label="stdout_bytes")
        require_nonneg_int(self.stderr_bytes, code="tool.capture", label="stderr_bytes")
        if self.stdout_sha256 is not None:
            require_hex64(self.stdout_sha256, label="stdout_sha256")
        if self.stderr_sha256 is not None:
            require_hex64(self.stderr_sha256, label="stderr_sha256")
        if self.launch_attempts not in {1, 2}:
            raise MediaContractError("tool.launch", "launch attempt count is invalid")

    def identity_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "cancelled": self.cancelled,
            "duration_us": self.duration_us,
            "launch_attempts": self.launch_attempts,
            "logical_name": self.logical_name.value,
            "policy_version": self.policy_version,
            "stderr_bytes": self.stderr_bytes,
            "stderr_status": self.stderr_status.value,
            "stdout_bytes": self.stdout_bytes,
            "stdout_status": self.stdout_status.value,
            "timed_out": self.timed_out,
        }
        if self.exit_status is not None:
            data["exit_status"] = self.exit_status
        if self.stdout_sha256 is not None:
            data["stdout_sha256"] = self.stdout_sha256
        if self.stderr_sha256 is not None:
            data["stderr_sha256"] = self.stderr_sha256
        return data


@dataclass(frozen=True, slots=True)
class InspectedStream:
    index: int
    kind: StreamKind
    codec_name: str | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    channel_layout: str | None = None
    width: int | None = None
    height: int | None = None
    frame_rate_num: int | None = None
    frame_rate_den: int | None = None
    bitrate_bps: int | None = None
    default_disposition: bool = False
    duration_us: int | None = None

    def __post_init__(self) -> None:
        require_nonneg_int(self.index, code="stream.index", label="index")
        if not isinstance(self.kind, StreamKind):
            raise MediaContractError("stream.kind", "stream kind is invalid")
        if self.codec_name is not None:
            if (
                not isinstance(self.codec_name, str)
                or not self.codec_name
                or "/" in self.codec_name
            ):
                raise MediaContractError("stream.codec", "codec name is invalid")
            if len(self.codec_name) > 32:
                raise MediaContractError("stream.codec", "codec name is invalid")
        for label, value in (
            ("sample_rate_hz", self.sample_rate_hz),
            ("channels", self.channels),
            ("width", self.width),
            ("height", self.height),
            ("frame_rate_num", self.frame_rate_num),
            ("frame_rate_den", self.frame_rate_den),
            ("bitrate_bps", self.bitrate_bps),
            ("duration_us", self.duration_us),
        ):
            if value is not None:
                require_nonneg_int(value, code="stream.field", label=label)
                if value < 1 and label != "duration_us":
                    raise MediaContractError("stream.field", f"{label} must be >= 1 when present")
        if self.channel_layout is not None:
            if not isinstance(self.channel_layout, str) or not self.channel_layout:
                raise MediaContractError("stream.layout", "channel layout is invalid")
            if "/" in self.channel_layout or len(self.channel_layout) > 32:
                raise MediaContractError("stream.layout", "channel layout is invalid")

    def identity_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "default_disposition": self.default_disposition,
            "index": self.index,
            "kind": self.kind.value,
        }
        optional = {
            "bitrate_bps": self.bitrate_bps,
            "channel_layout": self.channel_layout,
            "channels": self.channels,
            "codec_name": self.codec_name,
            "duration_us": self.duration_us,
            "frame_rate_den": self.frame_rate_den,
            "frame_rate_num": self.frame_rate_num,
            "height": self.height,
            "sample_rate_hz": self.sample_rate_hz,
            "width": self.width,
        }
        data.update({key: value for key, value in optional.items() if value is not None})
        return data


@dataclass(frozen=True, slots=True)
class MediaInspectionRequest:
    context: RequestContext
    source_manifest: MediaManifest
    source_relative_ref: str
    expected_sha256: str
    input_schema_version: str = INSPECTION_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.input_schema_version not in SUPPORTED_INSPECTION_INPUT_SCHEMA_VERSIONS:
            raise MediaContractError("inspect.schema", "unsupported inspection input schema")
        if self.context.namespace_id != self.source_manifest.namespace_id:
            raise MediaContractError("inspect.isolation", "namespace does not match the manifest")
        if self.context.job_id != self.source_manifest.job_id:
            raise MediaContractError("inspect.isolation", "job does not match the manifest")
        _require_relative_ref(self.source_relative_ref)
        require_hex64(self.expected_sha256, label="expected_sha256")
        if self.expected_sha256 != self.source_manifest.content_sha256:
            raise MediaContractError(
                "inspect.checksum",
                "expected digest does not match the accepted manifest",
            )


@dataclass(frozen=True, slots=True)
class MediaInspectionResult:
    state: MediaStepState
    schema_version: str
    stream_count: int
    streams: tuple[InspectedStream, ...]
    toolchain: MediaToolchainFingerprint | None = None
    container_format: str | None = None
    duration_us: int | None = None
    selected_stream_index: int | None = None
    selection_reason: StreamSelectionReason | None = None
    warnings: tuple[str, ...] = ()
    execution: ToolExecutionResult | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_INSPECTION_SCHEMA_VERSIONS:
            raise MediaContractError("inspect.schema", "unsupported inspection schema")
        if not isinstance(self.state, MediaStepState):
            raise MediaContractError("inspect.state", "inspection state is invalid")
        require_nonneg_int(self.stream_count, code="inspect.streams", label="stream_count")
        if self.stream_count != len(self.streams):
            raise MediaContractError("inspect.streams", "stream count does not match streams")
        if self.container_format is not None:
            if not isinstance(self.container_format, str) or not self.container_format:
                raise MediaContractError("inspect.container", "container format is invalid")
            if "/" in self.container_format or len(self.container_format) > 32:
                raise MediaContractError("inspect.container", "container format is invalid")
        if self.duration_us is not None:
            require_nonneg_int(self.duration_us, code="inspect.duration", label="duration_us")
        if self.selected_stream_index is not None:
            require_nonneg_int(
                self.selected_stream_index, code="inspect.stream", label="selected_stream_index"
            )
        if self.selection_reason is not None and not isinstance(
            self.selection_reason, StreamSelectionReason
        ):
            raise MediaContractError("inspect.selection", "selection reason is invalid")
        if self.state is MediaStepState.ACCEPTED and (
            self.toolchain is None or self.selected_stream_index is None
        ):
            raise MediaContractError(
                "inspect.success",
                "accepted inspection requires a toolchain and selected stream",
            )
        object.__setattr__(self, "warnings", _require_warnings(self.warnings))


@dataclass(frozen=True, slots=True)
class NormalizationRequest:
    context: RequestContext
    source_manifest: MediaManifest
    source_relative_ref: str
    selected_stream_index: int
    selection_reason: StreamSelectionReason
    input_schema_version: str = NORMALIZATION_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.input_schema_version not in SUPPORTED_NORMALIZATION_INPUT_SCHEMA_VERSIONS:
            raise MediaContractError("normalize.schema", "unsupported normalization input schema")
        if self.context.namespace_id != self.source_manifest.namespace_id:
            raise MediaContractError("normalize.isolation", "namespace does not match the manifest")
        if self.context.job_id != self.source_manifest.job_id:
            raise MediaContractError("normalize.isolation", "job does not match the manifest")
        _require_relative_ref(self.source_relative_ref)
        require_nonneg_int(
            self.selected_stream_index, code="normalize.stream", label="selected_stream_index"
        )
        if not isinstance(self.selection_reason, StreamSelectionReason):
            raise MediaContractError("normalize.selection", "selection reason is invalid")


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    state: MediaStepState
    schema_version: str
    sample_rate_hz: int | None = None
    channels: int | None = None
    sample_width_bytes: int | None = None
    duration_us: int | None = None
    output_sha256: str | None = None
    output_byte_size: int | None = None
    logical_uri: str | None = None
    toolchain: MediaToolchainFingerprint | None = None
    warnings: tuple[str, ...] = ()
    execution: ToolExecutionResult | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_NORMALIZATION_SCHEMA_VERSIONS:
            raise MediaContractError("normalize.schema", "unsupported normalization schema")
        if not isinstance(self.state, MediaStepState):
            raise MediaContractError("normalize.state", "normalization state is invalid")
        if self.state is MediaStepState.ACCEPTED:
            if (
                self.output_sha256 is None
                or self.output_byte_size is None
                or self.toolchain is None
                or self.logical_uri is None
            ):
                raise MediaContractError(
                    "normalize.success",
                    "accepted normalization requires verified output identity",
                )
            require_hex64(self.output_sha256, label="output_sha256")
            require_nonneg_int(
                self.output_byte_size, code="normalize.bytes", label="output_byte_size"
            )
            if self.output_byte_size < 1:
                raise MediaContractError("normalize.bytes", "canonical output is empty")
            if self.sample_rate_hz != 16_000 or self.channels != 1 or self.sample_width_bytes != 2:
                raise MediaContractError(
                    "normalize.format",
                    "canonical audio must be 16 kHz mono 16-bit PCM",
                )
        elif self.output_sha256 is not None:
            require_hex64(self.output_sha256, label="output_sha256")
        if self.duration_us is not None:
            require_nonneg_int(self.duration_us, code="normalize.duration", label="duration_us")
        if self.logical_uri is not None and (
            self.logical_uri.startswith(("/", "file://")) or "\\" in self.logical_uri
        ):
            raise MediaContractError("normalize.uri", "canonical URI must not be a filesystem path")
        object.__setattr__(self, "warnings", _require_warnings(self.warnings))
