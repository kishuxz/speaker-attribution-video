"""Rights record. Missing license fields are not permission. Not legal advice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from speaker_attribution_video.data.enums import RightsVerification
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.versions import (
    RIGHTS_SCHEMA_VERSION,
    SUPPORTED_RIGHTS_SCHEMA_VERSIONS,
)
from speaker_attribution_video.graph.enums import parse_enum
from speaker_attribution_video.graph.ids import require_slug
from speaker_attribution_video.graph.text import require_logical_uri
from speaker_attribution_video.graph.time import format_utc, parse_utc, require_utc

_MAX_NOTE = 256


def _granted(value: bool | None) -> bool:
    return value is True


def _opt_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise DataContractError("rights.bool", "permission flags must be booleans or omitted")


def _opt_note(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > _MAX_NOTE:
        raise DataContractError("rights.note", "reviewer note must be a short redacted string")
    if any(ch in value for ch in "\n\r\t"):
        raise DataContractError("rights.note", "reviewer note must be a short redacted string")
    if "/" in value or "\\" in value:
        raise DataContractError("rights.note", "reviewer note must not include filesystem paths")
    return value


@dataclass(frozen=True, slots=True)
class RightsRecord:
    verification: RightsVerification
    schema_version: str = RIGHTS_SCHEMA_VERSION
    license_id: str | None = None
    license_ref: str | None = None
    redistribution_permitted: bool | None = None
    derivative_use_permitted: bool | None = None
    commercial_use_permitted: bool | None = None
    research_only: bool = False
    attribution_required: bool = False
    consent_required: bool = False
    terms_accepted_by: str | None = None
    terms_accepted_at: datetime | None = None
    expires_at: datetime | None = None
    reviewer_note: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_RIGHTS_SCHEMA_VERSIONS:
            raise DataContractError("rights.schema", "unsupported rights schema version")
        if not isinstance(self.verification, RightsVerification):
            raise DataContractError("rights.verification", "verification status is invalid")
        if self.license_id is not None:
            require_slug(self.license_id, label="license_id")
        if self.license_ref is not None:
            require_logical_uri(self.license_ref, label="license_ref")
        if self.terms_accepted_by is not None:
            require_slug(self.terms_accepted_by, label="terms_accepted_by")
        if self.terms_accepted_at is not None:
            require_utc(self.terms_accepted_at)
            if self.terms_accepted_by is None:
                raise DataContractError(
                    "rights.terms",
                    "terms acceptance time requires an explicit acceptor; "
                    "acceptance is never automated",
                )
        if self.expires_at is not None:
            require_utc(self.expires_at)
        _opt_note(self.reviewer_note)

        prohibited_grant = (
            _granted(self.redistribution_permitted)
            or _granted(self.derivative_use_permitted)
            or _granted(self.commercial_use_permitted)
        )
        if self.verification is RightsVerification.PROHIBITED and prohibited_grant:
            raise DataContractError(
                "rights.prohibited", "prohibited data cannot grant use permissions"
            )

        if _granted(self.redistribution_permitted):
            if self.verification in {
                RightsVerification.UNVERIFIED,
                RightsVerification.PROHIBITED,
                RightsVerification.RESTRICTED,
            }:
                raise DataContractError(
                    "rights.redistribution",
                    "unknown or restricted rights cannot be marked redistributable",
                )
            if self.license_id is None:
                raise DataContractError(
                    "rights.license",
                    "missing license fields are not permission to redistribute",
                )
            if self.research_only:
                raise DataContractError(
                    "rights.research_only",
                    "research-only data cannot be marked redistributable",
                )

    def independently_verified_redistributable(self) -> bool:
        return (
            self.verification is RightsVerification.VERIFIED
            and _granted(self.redistribution_permitted)
            and not self.research_only
        )

    def identity_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "attribution_required": self.attribution_required,
            "consent_required": self.consent_required,
            "research_only": self.research_only,
            "schema_version": self.schema_version,
            "verification": self.verification.value,
        }
        if self.license_id is not None:
            data["license_id"] = self.license_id
        if self.license_ref is not None:
            data["license_ref"] = self.license_ref
        if self.redistribution_permitted is not None:
            data["redistribution_permitted"] = self.redistribution_permitted
        if self.derivative_use_permitted is not None:
            data["derivative_use_permitted"] = self.derivative_use_permitted
        if self.commercial_use_permitted is not None:
            data["commercial_use_permitted"] = self.commercial_use_permitted
        if self.terms_accepted_by is not None:
            data["terms_accepted_by"] = self.terms_accepted_by
        if self.terms_accepted_at is not None:
            data["terms_accepted_at"] = format_utc(self.terms_accepted_at)
        if self.expires_at is not None:
            data["expires_at"] = format_utc(self.expires_at)
        return data

    def to_dict(self) -> dict[str, Any]:
        data = self.identity_dict()
        if self.reviewer_note is not None:
            data["reviewer_note"] = self.reviewer_note
        return {k: data[k] for k in sorted(data)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RightsRecord:
        accepted_at = data.get("terms_accepted_at")
        expires = data.get("expires_at")
        return cls(
            verification=parse_enum(
                RightsVerification, data.get("verification"), code="rights.verification"
            ),
            schema_version=str(data.get("schema_version", RIGHTS_SCHEMA_VERSION)),
            license_id=str(data["license_id"]) if data.get("license_id") is not None else None,
            license_ref=str(data["license_ref"]) if data.get("license_ref") is not None else None,
            redistribution_permitted=_opt_bool(data.get("redistribution_permitted")),
            derivative_use_permitted=_opt_bool(data.get("derivative_use_permitted")),
            commercial_use_permitted=_opt_bool(data.get("commercial_use_permitted")),
            research_only=bool(data.get("research_only", False)),
            attribution_required=bool(data.get("attribution_required", False)),
            consent_required=bool(data.get("consent_required", False)),
            terms_accepted_by=str(data["terms_accepted_by"])
            if data.get("terms_accepted_by") is not None
            else None,
            terms_accepted_at=parse_utc(str(accepted_at)) if accepted_at is not None else None,
            expires_at=parse_utc(str(expires)) if expires is not None else None,
            reviewer_note=str(data["reviewer_note"])
            if data.get("reviewer_note") is not None
            else None,
        )


def project_fixture_rights() -> RightsRecord:
    """Original-project synthetic fixture rights. Not a third-party license grant."""
    return RightsRecord(
        verification=RightsVerification.VERIFIED,
        license_id="apache-2.0",
        license_ref="artifact://synth.example/licenses/apache-2.0",
        redistribution_permitted=True,
        derivative_use_permitted=True,
        commercial_use_permitted=True,
        research_only=False,
        attribution_required=True,
    )
