# Observability

## Intended telemetry (later phases)

- Structured logs per graph node (start, end, counts) without transcript payloads in default log level
- Evidence-graph export (JSON) for each run
- Counters: turns in, turns attributed, unresolved, validator retries
- Timing per node

## G1

No runtime telemetry. CLI prints help/version only. Graph documents can be serialized to JSON for later observability phases.

## Forbidden in logs and CI

Transcript bodies, training JSONL, W&B private metadata, credentials, absolute personal paths, and research-file hashes.
