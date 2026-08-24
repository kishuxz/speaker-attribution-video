"""UTC timestamps and integer microsecond timelines."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from speaker_attribution_video.graph.errors import GraphContractError

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
TIME_UNIT = "microseconds"


def utc_now_for_tests(fixed: datetime | None = None) -> datetime:
    if fixed is not None:
        return require_utc(fixed)
    return datetime.now(timezone.utc).replace(tzinfo=timezone.utc)


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise GraphContractError("time.naive", "timestamp must be timezone-aware UTC")
    aware = value.astimezone(timezone.utc)
    return aware.replace(tzinfo=timezone.utc)


def format_utc(value: datetime) -> str:
    return require_utc(value).strftime(TIMESTAMP_FORMAT)


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GraphContractError("time.format", "timestamp must use UTC Z serialization")
    try:
        parsed = datetime.strptime(value, TIMESTAMP_FORMAT)
    except ValueError as exc:
        raise GraphContractError("time.format", "timestamp must use UTC Z serialization") from exc
    return parsed.replace(tzinfo=timezone.utc)


def require_nonneg_int(value: int, *, code: str, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise GraphContractError(code, f"{label} must be an integer")
    if value < 0:
        raise GraphContractError(code, f"{label} must be nonnegative")
    return value


class TimeSpan:
    """Half-open [start_us, end_us) interval in microseconds."""

    __slots__ = ("start_us", "end_us")

    def __init__(self, start_us: int, end_us: int) -> None:
        self.start_us = require_nonneg_int(start_us, code="span.start", label="start_us")
        self.end_us = require_nonneg_int(end_us, code="span.end", label="end_us")
        if self.end_us <= self.start_us:
            raise GraphContractError("span.order", "end_us must be greater than start_us")

    def duration_us(self) -> int:
        return self.end_us - self.start_us

    def contains(self, other: TimeSpan) -> bool:
        return self.start_us <= other.start_us and other.end_us <= self.end_us

    def within_duration(self, duration_us: int | None) -> None:
        if duration_us is None:
            return
        require_nonneg_int(duration_us, code="span.duration", label="duration_us")
        if self.end_us > duration_us:
            raise GraphContractError("span.media_bounds", "span exceeds known media duration")

    def to_dict(self) -> dict[str, int]:
        return {"start_us": self.start_us, "end_us": self.end_us}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TimeSpan:
        start = data.get("start_us")
        end = data.get("end_us")
        if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool) or isinstance(end, bool):
            raise GraphContractError("span.type", "span requires integer start_us and end_us")
        return cls(start, end)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TimeSpan):
            return NotImplemented
        return self.start_us == other.start_us and self.end_us == other.end_us

    def __hash__(self) -> int:
        return hash((self.start_us, self.end_us))
