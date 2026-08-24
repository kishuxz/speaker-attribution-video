"""Typed immutable identifiers.

Canonical representation
------------------------
Every identifier is a single string:

    g1.id.v1/<kind>/<payload>

* ``g1.id.v1`` is the identifier schema version.
* ``kind`` is one of: namespace, job, node, edge, media, model_invocation, reviewer.
* ``payload`` is either a restricted slug (namespace, some job keys) or a
  SHA-256 hex digest of a canonical JSON object. The JSON object never includes
  raw transcript text; utterance identity uses a text hash or external reference.

The same canonical input therefore yields the same identifier. Random UUIDs are
not used. Distinct Python types prevent comparing a JobId to a NodeId.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Mapping

from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.jsonutil import canonical_object
from speaker_attribution_video.graph.versions import ID_SCHEMA_VERSION, SUPPORTED_ID_SCHEMA_VERSIONS

_SLUG_RE = re.compile(r"^[a-z][a-z0-9]{0,31}(?:[._-][a-z0-9]{1,32}){0,6}$")
_HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
_ID_RE = re.compile(r"^g1\.id\.v1/(namespace|job|node|edge|media|model_invocation|reviewer)/[A-Za-z0-9._:-]{1,256}$")

_KINDS = frozenset(
    {"namespace", "job", "node", "edge", "media", "model_invocation", "reviewer"}
)


def require_slug(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _SLUG_RE.fullmatch(value):
        raise GraphContractError("id.slug", f"{label} is not a valid slug")
    return value


def _require_slug(value: str, *, label: str) -> str:
    return require_slug(value, label=label)


def _sha256_hex(canonical_json: str) -> str:
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _format_id(kind: str, payload: str) -> str:
    if kind not in _KINDS:
        raise GraphContractError("id.kind", "unsupported identifier kind")
    text = f"{ID_SCHEMA_VERSION}/{kind}/{payload}"
    if not _ID_RE.fullmatch(text):
        raise GraphContractError("id.malformed", "identifier is blank or malformed")
    return text


def parse_id(value: str, *, expected_kind: str) -> tuple[str, str, str]:
    if not isinstance(value, str) or not value.strip():
        raise GraphContractError("id.blank", "identifier is blank or malformed")
    parts = value.split("/", 2)
    if len(parts) != 3:
        raise GraphContractError("id.malformed", "identifier is blank or malformed")
    schema, kind, payload = parts
    if schema not in SUPPORTED_ID_SCHEMA_VERSIONS:
        raise GraphContractError("id.schema", "unsupported identifier schema version")
    if kind != expected_kind or kind not in _KINDS:
        raise GraphContractError("id.kind", "identifier kind does not match expected type")
    if not payload or not _ID_RE.fullmatch(value):
        raise GraphContractError("id.malformed", "identifier is blank or malformed")
    return schema, kind, payload


@dataclass(frozen=True, slots=True)
class NamespaceId:
    value: str

    def __post_init__(self) -> None:
        parse_id(self.value, expected_kind="namespace")

    @classmethod
    def from_slug(cls, slug: str) -> NamespaceId:
        return cls(_format_id("namespace", _require_slug(slug, label="namespace")))


@dataclass(frozen=True, slots=True)
class JobId:
    value: str

    def __post_init__(self) -> None:
        parse_id(self.value, expected_kind="job")

    @classmethod
    def derive(cls, namespace: NamespaceId, job_key: str) -> JobId:
        payload = _sha256_hex(
            canonical_object(
                {
                    "job_key": _require_slug(job_key, label="job_key"),
                    "kind": "job",
                    "namespace": namespace.value,
                    "schema": ID_SCHEMA_VERSION,
                }
            )
        )
        return cls(_format_id("job", payload))


@dataclass(frozen=True, slots=True)
class NodeId:
    value: str

    def __post_init__(self) -> None:
        parse_id(self.value, expected_kind="node")

    @classmethod
    def derive(cls, namespace: NamespaceId, job: JobId, node_type: str, parts: Mapping[str, object]) -> NodeId:
        payload = _sha256_hex(
            canonical_object(
                {
                    "job": job.value,
                    "kind": "node",
                    "namespace": namespace.value,
                    "node_type": node_type,
                    "parts": dict(parts),
                    "schema": ID_SCHEMA_VERSION,
                }
            )
        )
        return cls(_format_id("node", payload))


@dataclass(frozen=True, slots=True)
class EdgeId:
    value: str

    def __post_init__(self) -> None:
        parse_id(self.value, expected_kind="edge")

    @classmethod
    def derive(
        cls,
        namespace: NamespaceId,
        job: JobId,
        edge_type: str,
        source: NodeId,
        target: NodeId,
    ) -> EdgeId:
        payload = _sha256_hex(
            canonical_object(
                {
                    "edge_type": edge_type,
                    "job": job.value,
                    "kind": "edge",
                    "namespace": namespace.value,
                    "schema": ID_SCHEMA_VERSION,
                    "source": source.value,
                    "target": target.value,
                }
            )
        )
        return cls(_format_id("edge", payload))


@dataclass(frozen=True, slots=True)
class MediaId:
    value: str

    def __post_init__(self) -> None:
        parse_id(self.value, expected_kind="media")

    @classmethod
    def derive(cls, namespace: NamespaceId, job: JobId, content_hash: str, uri: str) -> MediaId:
        if not _HEX64_RE.fullmatch(content_hash):
            raise GraphContractError("id.content_hash", "content_hash must be sha256 hex")
        payload = _sha256_hex(
            canonical_object(
                {
                    "content_hash": content_hash,
                    "job": job.value,
                    "kind": "media",
                    "namespace": namespace.value,
                    "schema": ID_SCHEMA_VERSION,
                    "uri": uri,
                }
            )
        )
        return cls(_format_id("media", payload))


@dataclass(frozen=True, slots=True)
class ModelInvocationId:
    value: str

    def __post_init__(self) -> None:
        parse_id(self.value, expected_kind="model_invocation")

    @classmethod
    def derive(cls, namespace: NamespaceId, job: JobId, role: str, parameter_digest: str) -> ModelInvocationId:
        payload = _sha256_hex(
            canonical_object(
                {
                    "job": job.value,
                    "kind": "model_invocation",
                    "namespace": namespace.value,
                    "parameter_digest": parameter_digest,
                    "role": _require_slug(role, label="role"),
                    "schema": ID_SCHEMA_VERSION,
                }
            )
        )
        return cls(_format_id("model_invocation", payload))


@dataclass(frozen=True, slots=True)
class ReviewerId:
    value: str

    def __post_init__(self) -> None:
        parse_id(self.value, expected_kind="reviewer")

    @classmethod
    def from_slug(cls, slug: str) -> ReviewerId:
        return cls(_format_id("reviewer", _require_slug(slug, label="reviewer")))


def require_hex64(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise GraphContractError("hash.sha256", f"{label} must be a sha256 hex digest")
    return value
