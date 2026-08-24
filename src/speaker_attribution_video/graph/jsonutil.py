"""JSON-safe values with deterministic encoding. Floats are rejected."""

from __future__ import annotations

import json
from collections.abc import Mapping

from speaker_attribution_video.graph.errors import GraphContractError

JsonAtom = None | bool | int | str
JsonValue = JsonAtom | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]

MAX_METADATA_KEYS = 32
MAX_METADATA_DEPTH = 4
MAX_JSON_STRING = 2048
MAX_JSON_LIST = 64
MAX_DOCUMENT_LIST = 4096

_KEY_RE_MSG = "json key is not a bounded slug"


def require_json_value(
    value: object,
    *,
    depth: int = 0,
    label: str = "value",
    max_depth: int = MAX_METADATA_DEPTH,
) -> JsonValue:
    if depth > max_depth:
        raise GraphContractError("json.depth", f"{label} exceeds max JSON depth")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 10**18:
            raise GraphContractError("json.int_range", f"{label} integer is out of bounds")
        return value
    if isinstance(value, float):
        raise GraphContractError(
            "json.float_forbidden", f"{label} must not use floating-point numbers"
        )
    if isinstance(value, str):
        if len(value) > MAX_JSON_STRING:
            raise GraphContractError("json.string_length", f"{label} string exceeds max length")
        return value
    if isinstance(value, list):
        limit = MAX_DOCUMENT_LIST if max_depth > MAX_METADATA_DEPTH else MAX_JSON_LIST
        if len(value) > limit:
            raise GraphContractError("json.list_length", f"{label} list exceeds max length")
        return [
            require_json_value(item, depth=depth + 1, label=label, max_depth=max_depth)
            for item in value
        ]
    if isinstance(value, dict):
        return require_json_object(value, depth=depth, label=label, max_depth=max_depth)
    raise GraphContractError("json.type", f"{label} is not JSON-safe")


def require_json_object(
    value: object,
    *,
    depth: int = 0,
    label: str = "metadata",
    max_depth: int = MAX_METADATA_DEPTH,
) -> JsonObject:
    if not isinstance(value, dict):
        raise GraphContractError("json.object", f"{label} must be an object")
    if len(value) > MAX_METADATA_KEYS and label == "metadata":
        raise GraphContractError("json.key_count", f"{label} has too many keys")
    if len(value) > 256:
        raise GraphContractError("json.key_count", f"{label} has too many keys")
    out: JsonObject = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _is_slug(key):
            raise GraphContractError("json.key", _KEY_RE_MSG)
        out[key] = require_json_value(item, depth=depth + 1, label=label, max_depth=max_depth)
    return out


def _is_slug(key: str) -> bool:
    if not key or len(key) > 64:
        return False
    if not key[0].isalpha():
        return False
    return all(ch.isalnum() or ch == "_" for ch in key)


def canonical_dumps(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_object(value: Mapping[str, object] | JsonObject) -> str:
    obj = require_json_object(dict(value))
    return canonical_dumps(obj)


def as_json_object(value: Mapping[str, object] | None) -> JsonObject:
    if value is None:
        return {}
    return require_json_object(dict(value))
