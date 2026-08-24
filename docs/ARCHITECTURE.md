# Architecture

**G1 implements the evidence graph contracts in the center of this diagram.** T1 adds verification around those contracts. Surrounding runtime boxes are planned and are not executable in this repository yet.

```
                    caller media (not in git)
                              │
                              ▼
                 ┌────────────────────────┐
                 │ Deterministic signals  │  planned
                 │ diarization / ASR      │  (not T1)
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
                 │ + observability        │  (not T1)
                 └────────────────────────┘
```

T1 implements **contracts and deterministic test doubles only**. It does not run audio or models. Overlapping speech is **representable** but not processed. Sensitive content is hashed, redacted, externally referenced, or explicitly classified if embedded.

Python **3.11** is the only supported runtime. A local Python 3.14 interpreter is an environment mismatch, not a product failure. See `docs/GRAPH.md`, `docs/BACKEND_CONTRACTS.md`, and `docs/TESTING.md`.
