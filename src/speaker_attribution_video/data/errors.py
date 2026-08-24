"""D1 contract errors. Messages must not include paths, media, or transcripts."""

from __future__ import annotations

from speaker_attribution_video.graph.errors import GraphContractError, redact_for_error


class DataContractError(GraphContractError):
    """Raised when a D1 source, rights, or manifest field is invalid."""


__all__ = ["DataContractError", "redact_for_error"]
