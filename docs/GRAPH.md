# G1 identifier and node contracts

G1 defines **graph contracts only**. There is no diarization, transcription, or
model inference in this phase.

## Canonical identifiers

Format:

```
g1.id.v1/<kind>/<payload>
```

| Part | Meaning |
|---|---|
| `g1.id.v1` | Identifier schema version. Unsupported versions are rejected. |
| `kind` | `namespace`, `job`, `node`, `edge`, `media`, `model_invocation`, `reviewer` |
| `payload` | Restricted slug (namespace, reviewer) or SHA-256 hex of canonical JSON |

Canonical JSON for derived IDs uses sorted keys, no floating-point numbers, and
**never includes raw transcript text**. Utterance/token identity uses a text
hash or external content reference.

The same canonical input produces the same ID. Distinct Python types (`JobId`,
`NodeId`, …) are not equal to each other even when payloads collide.

UTC timestamps serialize as `YYYY-MM-DDTHH:MM:SS.ffffffZ`.

Timeline values are **integer microseconds**. Overlapping turns are allowed at
the node level; a false non-overlap rule is not imposed.

## Nodes

Each `GraphNode` has: ID, node type, schema version `g1.node.v1`, namespace ID,
job ID, UTC created_at, producer, JSON-safe bounded metadata, sensitivity, and
provenance references, plus a typed payload.

Transcript text is `SensitiveText`: `redacted`, `hash`, `external_ref`, or
explicit `embedded` with sensitive/restricted classification. Exception messages
must not include raw transcript content.

Media nodes record content hash, duration, MIME/container, logical URI, and a
redacted display name. Raw audio/video bytes are not required.

## Edges (G1C)

Allowed relationship types are explicit. There is no generic `RELATED_TO` escape hatch.
Cross-namespace and cross-job edges are rejected. Self-edges are rejected.

Provenance/derivation types that must be acyclic (enforced in the graph validator):
`DERIVED_FROM`, `EXTRACTED_FROM`, `NORMALIZED_FROM`, `SEGMENTED_FROM`,
`CORRECTED_BY`, `PRODUCED_BY`.

## Attribution admission (G1D)

| State | Rule |
|---|---|
| `ATTRIBUTED` | Exactly one selected candidate, in the approved candidate set, and ≥1 `SUPPORTS` edge. Confidence cannot admit this state alone. |
| `UNRESOLVED` | No selected identity. |
| `CONTRADICTED` | ≥1 `CONTRADICTS` edge. |
| `REQUIRES_REVIEW` | Typed `review_reason_code`. |
| `REJECTED` | Typed rejection reason. |

## Graph document and validator (G1E/G1F)

`EvidenceGraphDocument` holds schema version `g1.graph.v1`, namespace, job, nodes,
edges, and creation metadata. `max_correction_attempts` defaults to **1** and is
hard-capped at 8. Attempt numbers for a given target decision must be sequential
starting at 1. Corrections are append-only: the resulting decision is a new node.

`validate_graph` returns structured findings (`code`, `severity`, node/edge refs,
redacted `message`, `repair_category`). `load_graph` raises before returning an
invalid document.

Retry exhaustion is represented as `UNRESOLVED` / `REQUIRES_REVIEW` / validation
failure. The graph does not implement an attribution agent.

