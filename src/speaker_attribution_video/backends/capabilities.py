"""Capability descriptors. A backend must not claim a capability it cannot provide."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from speaker_attribution_video.backends.failures import BackendError, FailureReason


class Capability(str, Enum):
    BATCH = "batch"
    STREAMING = "streaming"
    OVERLAPPING_SPEECH = "overlapping_speech"
    SPEAKER_COUNT_HINTS = "speaker_count_hints"
    WORD_TIMESTAMPS = "word_timestamps"
    CONFIDENCE = "confidence"
    GPU = "gpu"
    OFFLINE = "offline"
    DETERMINISTIC_REPLAY = "deterministic_replay"
    VIDEO_EVIDENCE = "video_evidence"
    REDACTED_TELEMETRY = "redacted_telemetry"


@dataclass(frozen=True, slots=True)
class Capabilities:
    batch: bool = False
    streaming: bool = False
    overlapping_speech: bool = False
    speaker_count_hints: bool = False
    word_timestamps: bool = False
    confidence: bool = False
    gpu: bool = False
    offline: bool = True
    deterministic_replay: bool = True
    video_evidence: bool = False
    redacted_telemetry: bool = True

    def offered(self) -> frozenset[Capability]:
        return frozenset(cap for cap in Capability if bool(getattr(self, cap.value)))

    def supports(self, capability: Capability) -> bool:
        return bool(getattr(self, capability.value))


def require_capabilities(offered: Capabilities, requested: Iterable[Capability]) -> None:
    missing = [cap for cap in requested if not offered.supports(cap)]
    if missing:
        names = ",".join(sorted(cap.value for cap in missing))
        raise BackendError(
            FailureReason.UNSUPPORTED_CAPABILITY,
            "requested capability is not offered",
            details={"capabilities": names},
        )
