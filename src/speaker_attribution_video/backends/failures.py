"""Typed backend failures. Messages must not include transcripts, media, tokens, or paths."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from speaker_attribution_video.graph.errors import redact_for_error


class FailureReason(str, Enum):
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    UNAVAILABLE_BACKEND = "unavailable_backend"
    MISSING_MODEL = "missing_model"
    TIMEOUT = "timeout"
    CANCELLATION = "cancellation"
    RESOURCE_LIMIT = "resource_limit"
    MALFORMED_OUTPUT = "malformed_output"
    SCHEMA_MISMATCH = "schema_mismatch"
    EXTERNAL_DEPENDENCY_FAILURE = "external_dependency_failure"
    UNSAFE_CONFIGURATION = "unsafe_configuration"
    PRIVACY_POLICY_REJECTION = "privacy_policy_rejection"


class ResultState(str, Enum):
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    UNRESOLVED = "UNRESOLVED"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    FAILED_BACKEND = "FAILED_BACKEND"
    FAILED_TIMEOUT = "FAILED_TIMEOUT"
    FAILED_CANCELLED = "FAILED_CANCELLED"
    FAILED_RESOURCE_LIMIT = "FAILED_RESOURCE_LIMIT"


_BLOCKED_DETAIL_KEYS = frozenset(
    {
        "transcript",
        "text",
        "embedded",
        "tokens",
        "token",
        "audio_bytes",
        "video_bytes",
        "path",
        "filepath",
        "filename",
        "home",
    }
)

SUCCESS_EQUIVALENTS = frozenset({ResultState.SUCCESS})


def is_successful(state: ResultState) -> bool:
    return state is ResultState.SUCCESS


def _safe_details(details: Mapping[str, object] | None) -> dict[str, object]:
    if details is None:
        return {}
    out: dict[str, object] = {}
    for key, value in details.items():
        if key.lower() in _BLOCKED_DETAIL_KEYS:
            out[key] = redact_for_error(value)
            continue
        if isinstance(value, str) and (
            "/" in value and not value.startswith(("artifact://", "g1.id.v1/"))
        ):
            out[key] = redact_for_error(value)
            continue
        out[key] = value
    return out


class BackendError(Exception):
    """Typed backend failure. Default string form is redacted."""

    def __init__(
        self,
        reason: FailureReason,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.reason = reason
        self.details = _safe_details(details)
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.reason.value}: {super().__str__()}"
