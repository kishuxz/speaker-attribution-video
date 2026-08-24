"""Shared enumerations for graph contracts."""

from __future__ import annotations

from enum import Enum

from speaker_attribution_video.graph.errors import GraphContractError


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


class ProducerKind(str, Enum):
    SYSTEM = "system"
    DETERMINISTIC = "deterministic"
    MODEL = "model"
    HUMAN = "human"
    TEST = "test"


class NodeType(str, Enum):
    MEDIA_ARTIFACT = "MediaArtifact"
    AUDIO_ARTIFACT = "AudioArtifact"
    PROCESSING_STEP = "ProcessingStep"
    MODEL_INVOCATION = "ModelInvocation"
    OUTPUT_ARTIFACT = "OutputArtifact"
    AUDIO_SEGMENT = "AudioSegment"
    DIARIZATION_TURN = "DiarizationTurn"
    TRANSCRIPT_UTTERANCE = "TranscriptUtterance"
    TRANSCRIPT_TOKEN = "TranscriptToken"
    SPEAKER_CLUSTER = "SpeakerCluster"
    CANDIDATE_IDENTITY = "CandidateIdentity"
    AUDIO_EVIDENCE = "AudioEvidence"
    VISUAL_EVIDENCE = "VisualEvidence"
    DIALOGUE_EVIDENCE = "DialogueEvidence"
    ATTRIBUTION_DECISION = "AttributionDecision"
    VALIDATION_FINDING = "ValidationFinding"
    CORRECTION_ATTEMPT = "CorrectionAttempt"
    HUMAN_REVIEW_DECISION = "HumanReviewDecision"


class ModelRole(str, Enum):
    """Logical role only. Does not name or import a vendor model."""

    UNSPECIFIED = "unspecified"
    DIARIZATION = "diarization"
    TRANSCRIPTION = "transcription"
    VOICE_SIMILARITY = "voice_similarity"
    LANGUAGE_MODEL = "language_model"
    OTHER = "other"


class DecisionState(str, Enum):
    ATTRIBUTED = "ATTRIBUTED"
    UNRESOLVED = "UNRESOLVED"
    CONTRADICTED = "CONTRADICTED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    REJECTED = "REJECTED"


class ReasonCode(str, Enum):
    OK = "ok"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    NO_CANDIDATE = "no_candidate"
    MULTIPLE_CANDIDATES = "multiple_candidates"
    LOW_SUPPORT = "low_support"
    VALIDATION_FAILED = "validation_failed"
    RETRY_EXHAUSTED = "retry_exhausted"
    HUMAN_REQUIRED = "human_required"
    OUT_OF_CANDIDATE_SET = "out_of_candidate_set"
    REVIEW_OVERRIDE = "review_override"
    REJECTED_BY_POLICY = "rejected_by_policy"


class RepairCategory(str, Enum):
    IDENTIFIER = "identifier"
    TIMELINE = "timeline"
    EDGE_MATRIX = "edge_matrix"
    ATTRIBUTION = "attribution"
    CORRECTION = "correction"
    REVIEW = "review"
    SCHEMA = "schema"
    ISOLATION = "isolation"
    PROVENANCE = "provenance"
    SENSITIVITY = "sensitivity"


class FindingSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ReviewOutcome(str, Enum):
    UPHOLD = "uphold"
    OVERRIDE = "override"
    REJECT = "reject"


class TextMode(str, Enum):
    REDACTED = "redacted"
    HASH = "hash"
    EXTERNAL_REF = "external_ref"
    EMBEDDED = "embedded"


class DialogueKind(str, Enum):
    MENTION = "mention"
    VOCATIVE = "vocative"
    SELF_ID = "self_id"
    OTHER = "other"


class EvidenceSummary(str, Enum):
    VOICE_SIMILARITY = "voice_similarity"
    SEGMENT_OVERLAP = "segment_overlap"
    CLUSTER_SUPPORT = "cluster_support"
    FACE_COPRESENCE = "face_copresence"
    ACTIVE_SPEAKER = "active_speaker"
    OTHER = "other"


def parse_enum(enum_cls: type[Enum], value: object, *, code: str) -> Enum:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            pass
    raise GraphContractError(code, f"unsupported {enum_cls.__name__} value")
