"""Unit tests for the D1 policy evaluator. Not legal advice."""

from __future__ import annotations

from datetime import timedelta

import pytest

from data_factory import FIXED, synthetic_source, unverified_rights
from speaker_attribution_video.data.enums import (
    DataSensitivity,
    PolicyDecision,
    PolicyOperation,
    PolicyReason,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.policy import evaluate_policy
from speaker_attribution_video.data.rights import RightsRecord, project_fixture_rights

pytestmark = pytest.mark.unit


def _eval(
    *,
    operation: PolicyOperation,
    source=None,
    rights=None,
    sensitivity: DataSensitivity = DataSensitivity.SYNTHETIC,
    now=FIXED,
):
    return evaluate_policy(
        source=source if source is not None else synthetic_source(),
        rights=rights if rights is not None else project_fixture_rights(),
        sensitivity=sensitivity,
        operation=operation,
        now=now,
    )


def test_prohibited_unknown_research_and_consent_fail_closed() -> None:
    prohibited = _eval(
        operation=PolicyOperation.INGEST,
        rights=RightsRecord(verification=RightsVerification.PROHIBITED),
        sensitivity=DataSensitivity.INTERNAL,
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
    )
    assert prohibited.decision is PolicyDecision.DENY
    assert prohibited.reason is PolicyReason.PROHIBITED_RIGHTS
    unknown_redist = _eval(
        operation=PolicyOperation.REDISTRIBUTE,
        rights=unverified_rights(),
        sensitivity=DataSensitivity.INTERNAL,
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
    )
    assert unknown_redist.decision is PolicyDecision.DENY
    assert unknown_redist.reason is PolicyReason.UNKNOWN_REDISTRIBUTION
    research = _eval(
        operation=PolicyOperation.DEMO,
        rights=RightsRecord(verification=RightsVerification.VERIFIED, research_only=True),
        sensitivity=DataSensitivity.RESTRICTED,
        source=synthetic_source(source_type=SourceType.RESEARCH_RESTRICTED),
    )
    assert research.decision is PolicyDecision.DENY
    assert research.reason is PolicyReason.RESEARCH_ONLY_PUBLIC_USE
    consent = _eval(
        operation=PolicyOperation.INGEST,
        rights=RightsRecord(verification=RightsVerification.USER_ATTESTED, consent_required=True),
        sensitivity=DataSensitivity.INTERNAL,
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
    )
    assert consent.decision is PolicyDecision.DENY
    assert consent.reason is PolicyReason.CONSENT_REQUIRED


def test_synthetic_project_provenance_allows_test_and_demo_not_silent_train() -> None:
    demo = _eval(operation=PolicyOperation.DEMO)
    assert demo.decision is PolicyDecision.ALLOW
    assert demo.reason is PolicyReason.SYNTHETIC_PROJECT_PROVENANCE
    ingest = _eval(operation=PolicyOperation.INGEST)
    assert ingest.decision is PolicyDecision.ALLOW
    train = _eval(operation=PolicyOperation.TRAIN)
    assert train.decision is PolicyDecision.REQUIRES_REVIEW
    assert train.reason is PolicyReason.SYNTHETIC_TRAINING_REVIEW


def test_biometric_personal_unverified_and_expiry() -> None:
    bio_train = _eval(
        operation=PolicyOperation.TRAIN,
        sensitivity=DataSensitivity.BIOMETRIC_DATA,
        rights=RightsRecord(
            verification=RightsVerification.USER_ATTESTED, license_id="caller-attested"
        ),
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
    )
    assert bio_train.decision is PolicyDecision.REQUIRES_REVIEW
    assert bio_train.reason is PolicyReason.BIOMETRIC_OR_PERSONAL_REVIEW
    export = _eval(
        operation=PolicyOperation.EXPORT_METADATA,
        sensitivity=DataSensitivity.PERSONAL_DATA,
        rights=RightsRecord(
            verification=RightsVerification.USER_ATTESTED, license_id="caller-attested"
        ),
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
    )
    assert export.decision is PolicyDecision.REQUIRES_REVIEW
    unverified_train = _eval(
        operation=PolicyOperation.TRAIN,
        rights=unverified_rights(),
        sensitivity=DataSensitivity.INTERNAL,
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
    )
    assert unverified_train.decision is PolicyDecision.DENY
    assert unverified_train.reason is PolicyReason.UNVERIFIED_TERMS
    unverified_ingest = _eval(
        operation=PolicyOperation.INGEST,
        rights=unverified_rights(),
        sensitivity=DataSensitivity.INTERNAL,
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
    )
    assert unverified_ingest.decision is PolicyDecision.REQUIRES_REVIEW
    expired = _eval(
        operation=PolicyOperation.INGEST,
        rights=RightsRecord(
            verification=RightsVerification.VERIFIED,
            license_id="caller-license",
            expires_at=FIXED - timedelta(days=1),
        ),
        sensitivity=DataSensitivity.INTERNAL,
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
        now=FIXED,
    )
    assert expired.decision is PolicyDecision.DENY
    assert expired.reason is PolicyReason.LICENSE_EXPIRED
    expired_export = _eval(
        operation=PolicyOperation.EXPORT_METADATA,
        rights=RightsRecord(
            verification=RightsVerification.VERIFIED,
            license_id="caller-license",
            expires_at=FIXED - timedelta(days=1),
        ),
        sensitivity=DataSensitivity.INTERNAL,
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
        now=FIXED,
    )
    assert expired_export.decision is PolicyDecision.REQUIRES_REVIEW


def test_unknown_never_defaults_to_allow_and_user_attestation_is_distinct() -> None:
    unknown = _eval(
        operation=PolicyOperation.DEMO,
        rights=unverified_rights(),
        sensitivity=DataSensitivity.UNKNOWN,
        source=synthetic_source(source_type=SourceType.UNKNOWN),
    )
    assert unknown.decision is PolicyDecision.DENY
    assert unknown.reason is not PolicyReason.VERIFIED_ALLOW
    attested = _eval(
        operation=PolicyOperation.INGEST,
        rights=RightsRecord(
            verification=RightsVerification.USER_ATTESTED, license_id="caller-attested"
        ),
        sensitivity=DataSensitivity.INTERNAL,
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
    )
    assert attested.decision is PolicyDecision.ALLOW
    assert attested.reason is PolicyReason.USER_ATTESTED_INGEST
    attested_demo = _eval(
        operation=PolicyOperation.DEMO,
        rights=RightsRecord(
            verification=RightsVerification.USER_ATTESTED, license_id="caller-attested"
        ),
        sensitivity=DataSensitivity.INTERNAL,
        source=synthetic_source(source_type=SourceType.LOCAL_USER_FILE),
    )
    assert attested_demo.decision is PolicyDecision.REQUIRES_REVIEW
    assert attested_demo.reason is PolicyReason.USER_ATTESTED_REVIEW
