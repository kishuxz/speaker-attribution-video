"""Enumerations for D1 source, rights, and sensitivity contracts."""

from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    SYNTHETIC = "SYNTHETIC"
    LOCAL_USER_FILE = "LOCAL_USER_FILE"
    USER_PROVIDED_DATASET = "USER_PROVIDED_DATASET"
    PUBLIC_DATASET_REFERENCE = "PUBLIC_DATASET_REFERENCE"
    RESEARCH_RESTRICTED = "RESEARCH_RESTRICTED"
    UNKNOWN = "UNKNOWN"


class AcquisitionMethod(str, Enum):
    GENERATED = "generated"
    USER_COPY = "user_copy"
    DECLARED_REFERENCE = "declared_reference"
    UNKNOWN = "unknown"


class RightsVerification(str, Enum):
    VERIFIED = "VERIFIED"
    USER_ATTESTED = "USER_ATTESTED"
    UNVERIFIED = "UNVERIFIED"
    RESTRICTED = "RESTRICTED"
    PROHIBITED = "PROHIBITED"


class DataSensitivity(str, Enum):
    """Ingestion sensitivity. Distinct from G1 graph Sensitivity.

    Voiceprints, face embeddings, and identity mappings are BIOMETRIC_DATA
    even though D1 does not generate them.
    """

    PUBLIC = "PUBLIC"
    SYNTHETIC = "SYNTHETIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"
    PERSONAL_DATA = "PERSONAL_DATA"
    BIOMETRIC_DATA = "BIOMETRIC_DATA"
    UNKNOWN = "UNKNOWN"


class RedactionState(str, Enum):
    NONE = "none"
    LOGICAL_NAMES = "logical_names"
    PATHS_EXCLUDED = "paths_excluded"
    CONTENTS_EXCLUDED = "contents_excluded"


class MediaTypeStatus(str, Enum):
    DECLARED = "declared"
    DETECTED = "detected"
    UNKNOWN = "unknown"
