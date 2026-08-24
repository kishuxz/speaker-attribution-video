"""Deterministic JSON serialization for EvidenceGraphDocument."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from speaker_attribution_video.graph.document import EvidenceGraphDocument
from speaker_attribution_video.graph.edges import EdgeType
from speaker_attribution_video.graph.enums import DecisionState, NodeType
from speaker_attribution_video.graph.errors import GraphContractError
from speaker_attribution_video.graph.jsonutil import canonical_dumps, require_json_object
from speaker_attribution_video.graph.validate import GraphValidationError, load_graph, validate_graph
from speaker_attribution_video.graph.versions import GRAPH_SCHEMA_VERSION

SCHEMA_PATH = Path(__file__).resolve().parent / "schemas" / "evidence_graph.g1.v1.json"
DOCUMENT_JSON_DEPTH = 16


def canonical_dumps_document(document: EvidenceGraphDocument) -> str:
    findings = validate_graph(document)
    errors = [f for f in findings if f.severity.value == "error"]
    if errors:
        raise GraphValidationError(tuple(errors))
    obj = require_json_object(document.to_dict(), label="document", max_depth=DOCUMENT_JSON_DEPTH)
    return canonical_dumps(obj)


def canonical_bytes(document: EvidenceGraphDocument) -> bytes:
    return canonical_dumps_document(document).encode("utf-8")


def loads_document(text: str) -> EvidenceGraphDocument:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GraphContractError("graph.json", "document is not valid JSON") from exc
    if not isinstance(data, dict):
        raise GraphContractError("graph.json", "document must be an object")
    if data.get("schema_version") != GRAPH_SCHEMA_VERSION:
        raise GraphContractError("graph.schema", "unsupported graph schema version")
    return load_graph(data)


def load_json_schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def python_enums_for_schema() -> dict[str, list[str]]:
    return {
        "node_types": [m.value for m in NodeType],
        "edge_types": [m.value for m in EdgeType],
        "decision_states": [m.value for m in DecisionState],
        "schema_version": GRAPH_SCHEMA_VERSION,
    }


def assert_schema_drift_free() -> None:
    schema = load_json_schema()
    enums = python_enums_for_schema()
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        raise GraphContractError("schema.defs", "JSON Schema is missing $defs")
    expected = {
        "NodeType": enums["node_types"],
        "EdgeType": enums["edge_types"],
        "DecisionState": enums["decision_states"],
    }
    for name, values in expected.items():
        spec = defs.get(name)
        if not isinstance(spec, dict) or spec.get("enum") != values:
            raise GraphContractError("schema.drift", f"JSON Schema enum drift: {name}")
    if schema.get("properties", {}).get("schema_version", {}).get("const") != enums["schema_version"]:
        raise GraphContractError("schema.drift", "JSON Schema schema_version drift")
