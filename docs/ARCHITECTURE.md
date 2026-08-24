# Architecture

**G1 implements the evidence graph contracts in the center of this diagram.** T1 adds verification around those contracts. D1 describes artifacts and can ingest local/synthetic files. MP1 adds toolchain contracts and a safe runner for separately installed FFprobe/FFmpeg; inspection and canonical normalization follow in later MP1 PRs. Surrounding diarization/ASR boxes are planned and are not executable yet.

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
                 │ MP1 media inspection   │  contracts + safe runner
                 │ canonical audio (later)│  (no diarization)
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

D1 describes artifacts. MP1A/B can invoke configured media tools without decoding in Python. Overlapping speech is **representable** but not processed. Sensitive content is hashed, redacted, externally referenced, or explicitly classified if embedded.

Python **3.11** is the only supported runtime. A local Python 3.14 interpreter is an environment mismatch, not a product failure. See `docs/GRAPH.md`, `docs/INGESTION.md`, `docs/MEDIA_PROCESSING.md`, `docs/FFMPEG.md`, `docs/BACKEND_CONTRACTS.md`, and `docs/TESTING.md`.
