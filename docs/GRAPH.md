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

Full graph validation, edges, and serialization stability are later G1 PRs.
