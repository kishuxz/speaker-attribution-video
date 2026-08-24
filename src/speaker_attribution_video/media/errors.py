"""MP1 errors. Messages must not include paths, media bytes, or command lines."""

from __future__ import annotations

from collections.abc import Mapping

from speaker_attribution_video.graph.errors import GraphContractError, redact_for_error
from speaker_attribution_video.media.enums import ToolFailureReason

_BLOCKED_DETAIL_KEYS = frozenset(
    {
        "path",
        "filepath",
        "filename",
        "home",
        "argv",
        "command",
        "cmd",
        "executable",
        "stderr",
        "stdout",
        "environ",
        "env",
        "audio_bytes",
        "video_bytes",
        "transcript",
    }
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
            and not value.startswith(
                ("artifact://", "d1.id.v1/", "g1.id.v1/", "userfile://", "catalog://")
            )
        ):
            out[key] = redact_for_error(value)
            continue
        out[key] = value
    return out


class MediaContractError(GraphContractError):
    """Raised when an MP1 toolchain or media-processing contract is invalid."""


class ToolError(Exception):
    """Typed media-tool failure. Default string form is redacted."""

    def __init__(
        self,
        reason: ToolFailureReason,
        message: str,
        *,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.reason = reason
        self.details = _safe_details(details)
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.reason.value}: {super().__str__()}"


__all__ = ["MediaContractError", "ToolError", "redact_for_error"]
