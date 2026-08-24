"""Subprocess execution policy. Conservative local-demo defaults."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from speaker_attribution_video.graph.time import require_nonneg_int
from speaker_attribution_video.media.errors import MediaContractError
from speaker_attribution_video.media.versions import (
    SUBPROCESS_POLICY_VERSION,
    SUPPORTED_SUBPROCESS_POLICY_VERSIONS,
)

# Local-demo defaults. Not sized for production batch workloads.
_DEFAULT_TIMEOUT_MS = 15_000
_DEFAULT_STDOUT_BYTES = 262_144
_DEFAULT_STDERR_BYTES = 16_384
_DEFAULT_TERMINATE_MS = 1_000
_DEFAULT_KILL_MS = 1_000
_MAX_TIMEOUT_MS = 120_000
_MAX_CAPTURE_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class SubprocessPolicy:
    timeout_ms: int = _DEFAULT_TIMEOUT_MS
    max_stdout_bytes: int = _DEFAULT_STDOUT_BYTES
    max_stderr_bytes: int = _DEFAULT_STDERR_BYTES
    terminate_grace_ms: int = _DEFAULT_TERMINATE_MS
    kill_timeout_ms: int = _DEFAULT_KILL_MS
    max_launch_retries: int = 1
    policy_version: str = SUBPROCESS_POLICY_VERSION

    def __post_init__(self) -> None:
        if self.policy_version not in SUPPORTED_SUBPROCESS_POLICY_VERSIONS:
            raise MediaContractError("subprocess.schema", "unsupported subprocess policy version")
        for label, value, minimum, maximum in (
            ("timeout_ms", self.timeout_ms, 1, _MAX_TIMEOUT_MS),
            ("max_stdout_bytes", self.max_stdout_bytes, 64, _MAX_CAPTURE_BYTES),
            ("max_stderr_bytes", self.max_stderr_bytes, 64, _MAX_CAPTURE_BYTES),
            ("terminate_grace_ms", self.terminate_grace_ms, 1, 10_000),
            ("kill_timeout_ms", self.kill_timeout_ms, 1, 10_000),
        ):
            require_nonneg_int(value, code="subprocess.limit", label=label)
            if value < minimum or value > maximum:
                raise MediaContractError(
                    "subprocess.limit",
                    f"{label} is outside the allowed range",
                )
        if self.max_launch_retries not in {0, 1}:
            raise MediaContractError(
                "subprocess.retry",
                "at most one launch retry is permitted",
            )

    def identity_dict(self) -> dict[str, object]:
        return {
            "kill_timeout_ms": self.kill_timeout_ms,
            "max_launch_retries": self.max_launch_retries,
            "max_stderr_bytes": self.max_stderr_bytes,
            "max_stdout_bytes": self.max_stdout_bytes,
            "policy_version": self.policy_version,
            "terminate_grace_ms": self.terminate_grace_ms,
            "timeout_ms": self.timeout_ms,
        }

    def to_dict(self) -> dict[str, Any]:
        return dict(self.identity_dict())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SubprocessPolicy:
        return cls(
            timeout_ms=int(data.get("timeout_ms", _DEFAULT_TIMEOUT_MS)),
            max_stdout_bytes=int(data.get("max_stdout_bytes", _DEFAULT_STDOUT_BYTES)),
            max_stderr_bytes=int(data.get("max_stderr_bytes", _DEFAULT_STDERR_BYTES)),
            terminate_grace_ms=int(data.get("terminate_grace_ms", _DEFAULT_TERMINATE_MS)),
            kill_timeout_ms=int(data.get("kill_timeout_ms", _DEFAULT_KILL_MS)),
            max_launch_retries=int(data.get("max_launch_retries", 1)),
            policy_version=str(data.get("policy_version", SUBPROCESS_POLICY_VERSION)),
        )
