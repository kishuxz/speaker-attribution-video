"""Stable conformance findings. These codes are part of the T1 contract."""

from __future__ import annotations


class ConformanceFailure(AssertionError):
    def __init__(self, finding: str, message: str) -> None:
        self.finding = finding
        super().__init__(f"{finding}: {message}")


def check(finding: str, condition: bool, message: str) -> None:
    if not condition:
        raise ConformanceFailure(finding, message)
