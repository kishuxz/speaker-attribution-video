"""Enumerations for MP1 toolchain and media-processing contracts."""

from __future__ import annotations

from enum import Enum


class ToolLogicalName(str, Enum):
    FFMPEG = "ffmpeg"
    FFPROBE = "ffprobe"


class ToolCapability(str, Enum):
    INSPECT_CONTAINER = "inspect_container"
    EXTRACT_AUDIO = "extract_audio"
    NORMALIZE_PCM_WAV = "normalize_pcm_wav"


class CaptureStatus(str, Enum):
    EMPTY = "empty"
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    OMITTED = "omitted"


class ToolFailureReason(str, Enum):
    TOOL_MISSING = "tool_missing"
    UNSUPPORTED_VERSION = "unsupported_version"
    LAUNCH_FAILURE = "launch_failure"
    TIMEOUT = "timeout"
    CANCELLATION = "cancellation"
    NONZERO_EXIT = "nonzero_exit"
    MALFORMED_TOOL_OUTPUT = "malformed_tool_output"
    OUTPUT_LIMIT_EXCEEDED = "output_limit_exceeded"
    RESOURCE_LIMIT = "resource_limit"
    UNSAFE_CONFIGURATION = "unsafe_configuration"
    VERIFICATION_FAILURE = "verification_failure"
    PROCESS_UNSTOPPABLE = "process_unstoppable"


class MediaStepState(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    FAILED_TIMEOUT = "FAILED_TIMEOUT"
    FAILED_CANCELLED = "FAILED_CANCELLED"
    FAILED_TOOL = "FAILED_TOOL"
    FAILED_RESOURCE_LIMIT = "FAILED_RESOURCE_LIMIT"


class StreamKind(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"
    SUBTITLE = "subtitle"
    DATA = "data"
    ATTACHMENT = "attachment"
    UNKNOWN = "unknown"


class StreamSelectionReason(str, Enum):
    EXPLICIT_INDEX = "explicit_index"
    DEFAULT_DISPOSITION = "default_disposition"
    LOWEST_SUPPORTED_INDEX = "lowest_supported_index"
