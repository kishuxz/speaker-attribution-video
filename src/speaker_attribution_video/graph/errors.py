"""Graph contract errors. Messages must never include raw transcript text."""

from __future__ import annotations


class GraphContractError(ValueError):
    """Raised when an identifier, node, or field violates the G1 contract."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def redact_for_error(_value: object) -> str:
    """Placeholder used instead of interpolating sensitive strings into errors."""
    return "<redacted>"
