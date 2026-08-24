"""Sensitive text handling. Raw content must not appear in exceptions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Mapping

from speaker_attribution_video.graph.enums import Sensitivity, TextMode, parse_enum
from speaker_attribution_video.graph.errors import GraphContractError, redact_for_error
from speaker_attribution_video.graph.ids import require_hex64, require_slug

_URI_RE = re.compile(r"^[a-z][a-z0-9+.-]{1,31}:[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=\-]{1,512}$")
_REDACTED_RE = re.compile(r"^\[redacted\]([a-z0-9._-]{0,64})?$")


def require_logical_uri(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _URI_RE.fullmatch(value):
        raise GraphContractError("uri.invalid", f"{label} is not a safe logical URI")
    return value


def normalize_text_for_hash(value: str) -> str:
    collapsed = " ".join(value.split())
    return collapsed.strip()


def sha256_normalized_text(value: str) -> str:
    normalized = normalize_text_for_hash(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SensitiveText:
    """Transcript-bearing payload.

    Use redacted, hash, or external_ref by default. Embedded text is opt-in and
    must carry Sensitivity.SENSITIVE or RESTRICTED. Exception paths never include
    the embedded or hash-source content.
    """

    mode: TextMode
    sensitivity: Sensitivity
    redacted: str | None = None
    sha256: str | None = None
    external_ref: str | None = None
    embedded: str | None = None

    def __post_init__(self) -> None:
        if self.mode is TextMode.REDACTED:
            if self.redacted is None or not _REDACTED_RE.fullmatch(self.redacted):
                raise GraphContractError("text.redacted", "redacted text must use the [redacted] form")
            if self.embedded is not None:
                raise GraphContractError("text.embedded", "redacted mode must not embed text")
        elif self.mode is TextMode.HASH:
            if self.sha256 is None:
                raise GraphContractError("text.hash", "hash mode requires sha256")
            require_hex64(self.sha256, label="text.sha256")
            if self.embedded is not None:
                raise GraphContractError("text.embedded", "hash mode must not embed text")
        elif self.mode is TextMode.EXTERNAL_REF:
            if self.external_ref is None:
                raise GraphContractError("text.ref", "external_ref mode requires a reference")
            require_logical_uri(self.external_ref, label="text.external_ref")
            if self.embedded is not None:
                raise GraphContractError("text.embedded", "external_ref mode must not embed text")
        elif self.mode is TextMode.EMBEDDED:
            if self.embedded is None or not self.embedded.strip():
                raise GraphContractError("text.embedded", "embedded mode requires opt-in text")
            if self.sensitivity not in (Sensitivity.SENSITIVE, Sensitivity.RESTRICTED):
                raise GraphContractError(
                    "text.sensitivity",
                    "embedded text must be classified sensitive or restricted",
                )
            if len(self.embedded) > 4096:
                raise GraphContractError("text.length", "embedded text exceeds bound")
            if self.sha256 is None:
                object.__setattr__(self, "sha256", sha256_normalized_text(self.embedded))
        else:
            raise GraphContractError("text.mode", "unsupported text mode")

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "mode": self.mode.value,
            "sensitivity": self.sensitivity.value,
        }
        if self.redacted is not None:
            data["redacted"] = self.redacted
        if self.sha256 is not None:
            data["sha256"] = self.sha256
        if self.external_ref is not None:
            data["external_ref"] = self.external_ref
        if self.embedded is not None:
            data["embedded"] = self.embedded
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> SensitiveText:
        mode = parse_enum(TextMode, data.get("mode"), code="text.mode")
        sensitivity = parse_enum(Sensitivity, data.get("sensitivity"), code="text.sensitivity")
        return cls(
            mode=mode,  # type: ignore[arg-type]
            sensitivity=sensitivity,  # type: ignore[arg-type]
            redacted=_opt_str(data.get("redacted")),
            sha256=_opt_str(data.get("sha256")),
            external_ref=_opt_str(data.get("external_ref")),
            embedded=_opt_str(data.get("embedded")),
        )

    def safe_preview(self) -> str:
        if self.mode is TextMode.REDACTED and self.redacted is not None:
            return self.redacted
        if self.mode is TextMode.HASH and self.sha256 is not None:
            return f"sha256:{self.sha256[:12]}"
        if self.mode is TextMode.EXTERNAL_REF:
            return "external_ref"
        return redact_for_error(self.embedded)


def _opt_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise GraphContractError("text.type", "text field must be a string")


def require_display_name(value: str) -> str:
    return require_slug(value, label="display_name")
