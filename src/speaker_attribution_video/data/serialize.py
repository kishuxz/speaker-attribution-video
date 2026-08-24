"""Deterministic JSON serialization for MediaManifest. Never includes file bytes."""

from __future__ import annotations

import json
from pathlib import Path

from speaker_attribution_video.data.enums import (
    AcquisitionMethod,
    DataSensitivity,
    MediaTypeStatus,
    RedactionState,
    RightsVerification,
    SourceType,
)
from speaker_attribution_video.data.errors import DataContractError
from speaker_attribution_video.data.manifest import MediaManifest
from speaker_attribution_video.data.versions import MANIFEST_SCHEMA_VERSION
from speaker_attribution_video.graph.jsonutil import canonical_dumps, require_json_object

SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "media_manifest.d1.v1.json"
DOCUMENT_JSON_DEPTH = 8


def canonical_dumps_manifest(manifest: MediaManifest) -> str:
    obj = require_json_object(manifest.to_dict(), label="document", max_depth=DOCUMENT_JSON_DEPTH)
    return canonical_dumps(obj)


def canonical_bytes(manifest: MediaManifest) -> bytes:
    return canonical_dumps_manifest(manifest).encode("utf-8")


def loads_manifest(text: str) -> MediaManifest:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataContractError("manifest.json", "document is not valid JSON") from exc
    if not isinstance(data, dict):
        raise DataContractError("manifest.json", "document must be an object")
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise DataContractError("manifest.schema", "unsupported manifest schema version")
    return MediaManifest.from_dict(data)


def load_json_schema() -> dict[str, object]:
    loaded: object = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise DataContractError("schema.json", "JSON Schema must be an object")
    schema: dict[str, object] = {}
    for key, value in loaded.items():
        if not isinstance(key, str):
            raise DataContractError("schema.json", "JSON Schema keys must be strings")
        schema[key] = value
    return schema


def python_enums_for_schema() -> dict[str, object]:
    return {
        "acquisition_methods": [member.value for member in AcquisitionMethod],
        "media_type_statuses": [member.value for member in MediaTypeStatus],
        "redaction_states": [member.value for member in RedactionState],
        "rights_verifications": [member.value for member in RightsVerification],
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "sensitivities": [member.value for member in DataSensitivity],
        "source_types": [member.value for member in SourceType],
    }


def assert_manifest_schema_drift_free() -> None:
    schema = load_json_schema()
    enums = python_enums_for_schema()
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        raise DataContractError("schema.defs", "JSON Schema is missing $defs")
    expected = {
        "AcquisitionMethod": enums["acquisition_methods"],
        "DataSensitivity": enums["sensitivities"],
        "MediaTypeStatus": enums["media_type_statuses"],
        "RedactionState": enums["redaction_states"],
        "RightsVerification": enums["rights_verifications"],
        "SourceType": enums["source_types"],
    }
    for name, values in expected.items():
        spec = defs.get(name)
        if not isinstance(spec, dict) or spec.get("enum") != values:
            raise DataContractError("schema.drift", f"JSON Schema enum drift: {name}")
    props = schema.get("properties")
    if not isinstance(props, dict):
        raise DataContractError("schema.drift", "JSON Schema schema_version drift")
    version_spec = props.get("schema_version")
    if not isinstance(version_spec, dict) or version_spec.get("const") != enums["schema_version"]:
        raise DataContractError("schema.drift", "JSON Schema schema_version drift")
