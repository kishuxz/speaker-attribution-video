# Architecture

**G1 implements the evidence graph contracts in the center of this diagram.** Surrounding boxes are planned and are not executable in this repository yet.

```
                    caller media (not in git)
                              │
                              ▼
                 ┌────────────────────────┐
                 │ Deterministic signals  │  planned
                 │ diarization / ASR      │  (not G1)
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
                 │ Bounded agents         │  planned
                 │ + observability        │  (not G1)
                 └────────────────────────┘
```

G1 records how a media artifact *could* become diarization, transcript, and attribution decisions. It does not run those steps. Overlapping speech is **representable** but not processed. Sensitive content is hashed, redacted, externally referenced, or explicitly classified if embedded.

Python **3.11** is the only supported runtime. A local Python 3.14 interpreter is an environment mismatch, not a product failure. See `docs/GRAPH.md` for identifier, node, edge, and validator contracts. T1 adds verification tooling; it does not run audio or models.
