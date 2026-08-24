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


class DatasetSplit(str, Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"
    DEMO = "DEMO"
    UNASSIGNED = "UNASSIGNED"


class IntendedUse(str, Enum):
    TRAINING = "training"
    EVALUATION = "evaluation"
    DEMO = "demo"
    FIXTURE = "fixture"
    UNSPECIFIED = "unspecified"


class IngestionState(str, Enum):
    ACCEPTED = "ACCEPTED"
    DEGRADED = "DEGRADED"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    FAILED_POLICY = "FAILED_POLICY"


class IngestionFindingSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ConnectorCapability(str, Enum):
    LOCAL_FILES = "local_files"
    DIRECTORY_MANIFESTS = "directory_manifests"
    SYNTHETIC_GENERATION = "synthetic_generation"
    EXTERNAL_REFERENCES = "external_references"
    CHECKSUM_VERIFICATION = "checksum_verification"
    IMMUTABLE_SNAPSHOTS = "immutable_snapshots"
    RIGHTS_METADATA = "rights_metadata"
    SENSITIVITY_ENFORCEMENT = "sensitivity_enforcement"


class ConnectorFailureReason(str, Enum):
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    UNSAFE_CONFIGURATION = "unsafe_configuration"
    SCHEMA_MISMATCH = "schema_mismatch"
    POLICY_REJECTION = "policy_rejection"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    RESOURCE_LIMIT = "resource_limit"
    CANCELLATION = "cancellation"
    CHANGED_DURING_READ = "changed_during_read"
    IO_FAILURE = "io_failure"
    PATH_ESCAPE = "path_escape"
