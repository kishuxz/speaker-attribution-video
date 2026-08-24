"""Tool identity and toolchain fingerprints. Absolute paths are never serialized."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from speaker_attribution_video.graph.ids import require_hex64, require_slug
from speaker_attribution_video.graph.jsonutil import canonical_object
from speaker_attribution_video.media.enums import ToolCapability, ToolLogicalName
from speaker_attribution_video.media.errors import MediaContractError
from speaker_attribution_video.media.versions import (
    MEDIA_TOOL_SCHEMA_VERSION,
    MEDIA_TOOLCHAIN_SCHEMA_VERSION,
    SUPPORTED_MEDIA_TOOL_SCHEMA_VERSIONS,
    SUPPORTED_MEDIA_TOOLCHAIN_SCHEMA_VERSIONS,
)

_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_VERSION_LINE = re.compile(
    r"^(?:ffmpeg|ffprobe) version (?P<version>[A-Za-z0-9._+-]+)",
    re.IGNORECASE,
)


def parse_tool_version_line(logical_name: str, first_line: str) -> str:
    if not isinstance(first_line, str) or not first_line.strip():
        raise MediaContractError("tool.version", "tool version output is missing")
    match = _VERSION_LINE.match(first_line.strip())
    if match is None:
        raise MediaContractError("tool.version", "tool version output is malformed")
    version = match.group("version")
    expected = logical_name.lower()
    lead = first_line.strip().split(None, 1)[0].lower()
    if lead != expected:
        raise MediaContractError("tool.version", "tool version identity does not match")
    if _VERSION_RE.fullmatch(version) is None:
        raise MediaContractError("tool.version", "tool version token is invalid")
    return version


@dataclass(frozen=True, slots=True)
class MediaToolIdentity:
    logical_name: ToolLogicalName
    version: str
    version_sha256: str
    schema_version: str = MEDIA_TOOL_SCHEMA_VERSION
    capabilities: frozenset[ToolCapability] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_MEDIA_TOOL_SCHEMA_VERSIONS:
            raise MediaContractError("tool.schema", "unsupported media-tool schema version")
        if not isinstance(self.logical_name, ToolLogicalName):
            raise MediaContractError("tool.name", "tool logical name is invalid")
        if _VERSION_RE.fullmatch(self.version) is None:
            raise MediaContractError("tool.version", "tool version token is invalid")
        require_hex64(self.version_sha256, label="version_sha256")
        for cap in self.capabilities:
            if not isinstance(cap, ToolCapability):
                raise MediaContractError("tool.capability", "tool capability is invalid")

    def identity_dict(self) -> dict[str, object]:
        return {
            "capabilities": sorted(cap.value for cap in self.capabilities),
            "logical_name": self.logical_name.value,
            "schema_version": self.schema_version,
            "version": self.version,
            "version_sha256": self.version_sha256,
        }

    def to_dict(self) -> dict[str, Any]:
        return {key: self.identity_dict()[key] for key in sorted(self.identity_dict())}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MediaToolIdentity:
        raw_caps = data.get("capabilities", ())
        if not isinstance(raw_caps, list | tuple):
            raise MediaContractError("tool.capability", "tool capability list is invalid")
        name = data.get("logical_name")
        if not isinstance(name, str):
            raise MediaContractError("tool.name", "tool logical name is invalid")
        try:
            caps = frozenset(ToolCapability(str(item)) for item in raw_caps)
            logical = ToolLogicalName(name)
        except ValueError as exc:
            raise MediaContractError("tool.identity", "tool identity fields are invalid") from exc
        return cls(
            logical_name=logical,
            version=str(data.get("version", "")),
            version_sha256=str(data.get("version_sha256", "")),
            schema_version=str(data.get("schema_version", MEDIA_TOOL_SCHEMA_VERSION)),
            capabilities=caps,
        )


@dataclass(frozen=True, slots=True)
class MediaToolchainFingerprint:
    ffmpeg: MediaToolIdentity
    ffprobe: MediaToolIdentity
    policy_version: str
    digest: str
    schema_version: str = MEDIA_TOOLCHAIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_MEDIA_TOOLCHAIN_SCHEMA_VERSIONS:
            raise MediaContractError("toolchain.schema", "unsupported toolchain schema version")
        if self.ffmpeg.logical_name is not ToolLogicalName.FFMPEG:
            raise MediaContractError("toolchain.ffmpeg", "ffmpeg identity is required")
        if self.ffprobe.logical_name is not ToolLogicalName.FFPROBE:
            raise MediaContractError("toolchain.ffprobe", "ffprobe identity is required")
        require_slug(self.policy_version, label="policy_version")
        require_hex64(self.digest, label="toolchain_digest")

    def identity_dict(self) -> dict[str, object]:
        return {
            "digest": self.digest,
            "ffmpeg": self.ffmpeg.identity_dict(),
            "ffprobe": self.ffprobe.identity_dict(),
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "digest": self.digest,
            "ffmpeg": self.ffmpeg.to_dict(),
            "ffprobe": self.ffprobe.to_dict(),
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
        }


def fingerprint_toolchain(
    *,
    ffmpeg: MediaToolIdentity,
    ffprobe: MediaToolIdentity,
    policy_version: str,
) -> MediaToolchainFingerprint:
    payload = {
        "ffmpeg": ffmpeg.identity_dict(),
        "ffprobe": ffprobe.identity_dict(),
        "policy_version": policy_version,
        "schema_version": MEDIA_TOOLCHAIN_SCHEMA_VERSION,
    }
    digest = hashlib.sha256(canonical_object(payload).encode("utf-8")).hexdigest()
    return MediaToolchainFingerprint(
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        policy_version=policy_version,
        digest=digest,
    )
