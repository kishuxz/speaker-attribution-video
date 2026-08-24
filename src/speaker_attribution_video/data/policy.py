"""Deterministic rights and data-policy evaluator.

This module is an engineering gate over declared source, rights, and
sensitivity fields. It is **not legal advice**, not license verification, and
not automated acceptance of third-party terms. Unknown never defaults to allow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from speaker_attribution_video.data.enums import (
    DataSensitivity,
    PolicyDecision,
    PolicyOperation,
    PolicyReason,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.rights import RightsRecord
from speaker_attribution_video.data.source import SourceDescriptor
from speaker_attribution_video.graph.time import require_utc, utc_now_for_tests

_PUBLIC_OPS = frozenset({PolicyOperation.DEMO, PolicyOperation.REDISTRIBUTE})
_TRAIN_EXPORT = frozenset({PolicyOperation.TRAIN, PolicyOperation.EXPORT_METADATA})
_IDENTITY_SENSITIVE = frozenset({DataSensitivity.PERSONAL_DATA, DataSensitivity.BIOMETRIC_DATA})
_RESTRICTED_SENSITIVITY = frozenset(
    {
        DataSensitivity.RESTRICTED,
        DataSensitivity.PERSONAL_DATA,
        DataSensitivity.BIOMETRIC_DATA,
        DataSensitivity.UNKNOWN,
    }
)


@dataclass(frozen=True, slots=True)
class PolicyResult:
    decision: PolicyDecision
    reason: PolicyReason
    operation: PolicyOperation

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PolicyDecision):
            raise TypeError("policy decision is invalid")
        if not isinstance(self.reason, PolicyReason):
            raise TypeError("policy reason is invalid")
        if not isinstance(self.operation, PolicyOperation):
            raise TypeError("policy operation is invalid")


def _deny(operation: PolicyOperation, reason: PolicyReason) -> PolicyResult:
    return PolicyResult(PolicyDecision.DENY, reason, operation)


def _review(operation: PolicyOperation, reason: PolicyReason) -> PolicyResult:
    return PolicyResult(PolicyDecision.REQUIRES_REVIEW, reason, operation)


def _allow(operation: PolicyOperation, reason: PolicyReason) -> PolicyResult:
    return PolicyResult(PolicyDecision.ALLOW, reason, operation)


def _project_synthetic(
    source: SourceDescriptor, rights: RightsRecord, sensitivity: DataSensitivity
) -> bool:
    return (
        source.source_type is SourceType.SYNTHETIC
        and sensitivity is DataSensitivity.SYNTHETIC
        and rights.verification is RightsVerification.VERIFIED
        and rights.license_id == "apache-2.0"
        and not rights.research_only
    )


def evaluate_policy(
    *,
    source: SourceDescriptor,
    rights: RightsRecord,
    sensitivity: DataSensitivity,
    operation: PolicyOperation,
    now: datetime | None = None,
) -> PolicyResult:
    """Evaluate a requested operation. Unknown never defaults to allow."""

    if not isinstance(operation, PolicyOperation):
        raise DataContractError("policy.operation", "operation is invalid")
    if not isinstance(sensitivity, DataSensitivity):
        raise DataContractError("policy.sensitivity", "sensitivity is invalid")

    observed = now if now is not None else utc_now_for_tests()
    require_utc(observed)

    if rights.verification is RightsVerification.PROHIBITED:
        return _deny(operation, PolicyReason.PROHIBITED_RIGHTS)

    if rights.consent_required and rights.terms_accepted_by is None:
        return _deny(operation, PolicyReason.CONSENT_REQUIRED)

    if rights.expires_at is not None and observed >= rights.expires_at:
        if operation is PolicyOperation.EXPORT_METADATA:
            return _review(operation, PolicyReason.LICENSE_EXPIRED)
        return _deny(operation, PolicyReason.LICENSE_EXPIRED)

    if operation is PolicyOperation.REDISTRIBUTE:
        if rights.redistribution_permitted is not True:
            return _deny(operation, PolicyReason.UNKNOWN_REDISTRIBUTION)
        if rights.verification is not RightsVerification.VERIFIED:
            return _deny(operation, PolicyReason.UNKNOWN_REDISTRIBUTION)
        if rights.research_only or sensitivity in _RESTRICTED_SENSITIVITY:
            return _deny(operation, PolicyReason.UNKNOWN_REDISTRIBUTION)

    if rights.research_only and operation in _PUBLIC_OPS:
        return _deny(operation, PolicyReason.RESEARCH_ONLY_PUBLIC_USE)

    if source.source_type is SourceType.RESEARCH_RESTRICTED and operation in {
        PolicyOperation.TRAIN,
        PolicyOperation.DEMO,
        PolicyOperation.REDISTRIBUTE,
    }:
        return _deny(operation, PolicyReason.RESEARCH_RESTRICTED)

    if sensitivity in _IDENTITY_SENSITIVE and operation is PolicyOperation.DEMO:
        return _deny(operation, PolicyReason.PERSONAL_DATA_DEMO)

    if sensitivity in _IDENTITY_SENSITIVE and operation in _TRAIN_EXPORT:
        return _review(operation, PolicyReason.BIOMETRIC_OR_PERSONAL_REVIEW)

    if sensitivity is DataSensitivity.UNKNOWN:
        if operation in {PolicyOperation.TRAIN, PolicyOperation.DEMO, PolicyOperation.REDISTRIBUTE}:
            return _deny(operation, PolicyReason.UNKNOWN_SENSITIVITY)
        return _review(operation, PolicyReason.UNKNOWN_SENSITIVITY)

    if rights.verification is RightsVerification.RESTRICTED:
        if operation in {PolicyOperation.TRAIN, *_PUBLIC_OPS}:
            return _deny(operation, PolicyReason.RESTRICTED_RIGHTS)
        return _review(operation, PolicyReason.RESTRICTED_RIGHTS)

    if rights.verification is RightsVerification.UNVERIFIED:
        if operation in {PolicyOperation.TRAIN, *_PUBLIC_OPS}:
            return _deny(operation, PolicyReason.UNVERIFIED_TERMS)
        return _review(operation, PolicyReason.UNVERIFIED_TERMS)

    if _project_synthetic(source, rights, sensitivity):
        if operation is PolicyOperation.TRAIN:
            return _review(operation, PolicyReason.SYNTHETIC_TRAINING_REVIEW)
        if operation is PolicyOperation.REDISTRIBUTE and rights.redistribution_permitted is True:
            return _allow(operation, PolicyReason.SYNTHETIC_PROJECT_PROVENANCE)
        if operation in {
            PolicyOperation.INGEST,
            PolicyOperation.EVALUATE,
            PolicyOperation.DEMO,
            PolicyOperation.EXPORT_METADATA,
        }:
            return _allow(operation, PolicyReason.SYNTHETIC_PROJECT_PROVENANCE)

    if rights.verification is RightsVerification.USER_ATTESTED:
        if operation is PolicyOperation.INGEST:
            return _allow(operation, PolicyReason.USER_ATTESTED_INGEST)
        return _review(operation, PolicyReason.USER_ATTESTED_REVIEW)

    if rights.verification is RightsVerification.VERIFIED:
        if operation is PolicyOperation.TRAIN and sensitivity is DataSensitivity.RESTRICTED:
            return _review(operation, PolicyReason.RESTRICTED_RIGHTS)
        if operation in {
            PolicyOperation.INGEST,
            PolicyOperation.EVALUATE,
            PolicyOperation.EXPORT_METADATA,
        }:
            return _allow(operation, PolicyReason.VERIFIED_ALLOW)
        if operation is PolicyOperation.DEMO and sensitivity in {
            DataSensitivity.PUBLIC,
            DataSensitivity.INTERNAL,
            DataSensitivity.SYNTHETIC,
        }:
            return _allow(operation, PolicyReason.VERIFIED_ALLOW)
        if operation is PolicyOperation.REDISTRIBUTE and rights.redistribution_permitted is True:
            return _allow(operation, PolicyReason.VERIFIED_ALLOW)
        if operation is PolicyOperation.TRAIN:
            return _review(operation, PolicyReason.TRAINING_REVIEW)

    return _deny(operation, PolicyReason.UNKNOWN_DEFAULT_DENY)


__all__ = ["PolicyResult", "evaluate_policy"]
