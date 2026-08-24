"""MP1 media-tool contracts and the safe subprocess runner.

These types describe external FFmpeg/FFprobe invocations. They do not bundle
binaries, download tools, decode media in Python, or run models.
"""

from __future__ import annotations

from speaker_attribution_video.media.contracts import (
    InspectedStream,
    MediaInspectionRequest,
    MediaInspectionResult,
    NormalizationRequest,
    NormalizationResult,
    ToolExecutionResult,
)
from speaker_attribution_video.media.enums import (
    CaptureStatus,
    MediaStepState,
    StreamKind,
    StreamSelectionReason,
    ToolCapability,
    ToolFailureReason,
    ToolLogicalName,
)
from speaker_attribution_video.media.errors import MediaContractError, ToolError
from speaker_attribution_video.media.identity import (
    MediaToolchainFingerprint,
    MediaToolIdentity,
    fingerprint_toolchain,
    parse_tool_version_line,
)
from speaker_attribution_video.media.policy import SubprocessPolicy
from speaker_attribution_video.media.runner import MediaToolRunner, ToolRun
from speaker_attribution_video.media.workspace import TemporaryWorkspace

__all__ = [
    "CaptureStatus",
    "InspectedStream",
    "MediaContractError",
    "MediaInspectionRequest",
    "MediaInspectionResult",
    "MediaStepState",
    "MediaToolIdentity",
    "MediaToolRunner",
    "MediaToolchainFingerprint",
    "NormalizationRequest",
    "NormalizationResult",
    "StreamKind",
    "StreamSelectionReason",
    "SubprocessPolicy",
    "TemporaryWorkspace",
    "ToolCapability",
    "ToolError",
    "ToolExecutionResult",
    "ToolFailureReason",
    "ToolLogicalName",
    "ToolRun",
    "fingerprint_toolchain",
    "parse_tool_version_line",
]
