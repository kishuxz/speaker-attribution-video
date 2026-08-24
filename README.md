# Speaker Attribution Graph

Speaker Attribution Graph is a production-shaped framework for tracing how audio, transcript and optional video evidence become speaker-attribution decisions. It separates deterministic diarization from bounded attribution agents, preserves unresolved cases, and exposes evidence graphs, evaluation and observability.

This repository (`kishuxz/speaker-attribution-video`) holds original source under Apache-2.0. It is **private during G1**. It is not a release of a production pipeline, and it does not ship models, datasets, or research media.

## Current phase (G1)

Typed evidence and execution-graph **contracts** only:

- identifiers, nodes, edges, attribution and correction rules
- invariant validator and canonical JSON + JSON Schema
- synthetic fixtures (engineering tests, not benchmarks)

There is **no** real diarization, transcription, model inference, or agent execution. Graph provenance is not proof; confidence is not correctness.

```bash
python3.11 -m pip install -r requirements.lock
python3.11 -m pip install -e .
python3.11 -m speaker_attribution_video --help
python3.11 -m pytest
python3.11 scripts/verify_g1.py
```

Python **3.11** only (`requires-python = ">=3.11,<3.12"`).

## What this is not

- Not a claim that prior research code was production-ready
- Not a redistribution of television corpora, transcripts, or logs
- Not a bundle of pyannote, WhisperX, ECAPA, Llama, InsightFace, or LightASD weights
- InsightFace and LightASD remain **research-only / license review required**

See `docs/LIMITATIONS.md`, `docs/GRAPH.md`, `docs/MODEL_POLICY.md`, and `THIRD_PARTY_NOTICES.md`.
