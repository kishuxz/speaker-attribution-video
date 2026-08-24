# Architecture

**G1 implements the evidence graph contracts in the center of this diagram.** T1 adds verification around those contracts. D1 can now describe artifacts, ingest local/synthetic files, persist manifest snapshots, evaluate declared rights, and project an accepted ingestion into a G1 graph. Surrounding media-processing boxes are planned and are not executable in this repository yet.

```
                    caller media (not in git)
                              │
                              ▼
                 ┌────────────────────────┐
                 │ D1 ingestion boundary  │  contracts + local/synthetic
                 │ manifests / rights     │  (no media decode)
                 └───────────┬────────────┘
                             │
                 ┌────────────────────────┐
                 │ Deterministic signals  │  planned
                 │ diarization / ASR      │  (not D1)
                 └───────────┬────────────┘
                             │
     planned video ─ ─ ─ ─ ─ ┤
     (license review)        │
                             ▼
                 ┌────────────────────────┐
                 │  Evidence graph (G1)   │  implemented
                 │  nodes, edges, rules   │
                 └───────────┬────────────┘
                             │
                 ┌───────────┴────────────┐
                 │ T1 backend protocols   │  contracts + fakes only
                 │ + conformance suites   │
                 └───────────┬────────────┘
                             │
                 ┌───────────┴────────────┐
                 │ Bounded agents         │  planned
                 │ + observability        │  (not D1)
                 └────────────────────────┘
```

D1 describes artifacts. It does not run audio or models. Overlapping speech is **representable** but not processed. Sensitive content is hashed, redacted, externally referenced, or explicitly classified if embedded.

Python **3.11** is the only supported runtime. A local Python 3.14 interpreter is an environment mismatch, not a product failure. See `docs/GRAPH.md`, `docs/INGESTION.md`, `docs/BACKEND_CONTRACTS.md`, and `docs/TESTING.md`.
