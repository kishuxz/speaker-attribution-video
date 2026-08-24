# Speaker Attribution Graph

Speaker Attribution Graph is a production-shaped framework for tracing how audio, transcript and optional video evidence become speaker-attribution decisions. It separates deterministic diarization from bounded attribution agents, preserves unresolved cases, and exposes evidence graphs, evaluation and observability.

This repository (`kishuxz/speaker-attribution-video`) holds original source under Apache-2.0. It is **private during this foundation phase**. It is not a release of a production pipeline, and it does not ship models, datasets, or research media.

## Current phase (F0)

Governing foundation only:

- license and third-party boundaries
- empty typed Python 3.11 package
- documentation of product, architecture, data/model policy, and limitations
- import / CLI smoke test

**Not included yet:** inference code, model adapters, research datasets, weights, or copied private-research implementation.

```bash
python3.11 -m pip install -e ".[dev]"
python3.11 -m speaker_attribution_video --help
python3.11 -m pytest
```

Python **3.11** only (`requires-python = ">=3.11,<3.12"`).

## What this is not

- Not a claim that prior research code was production-ready
- Not a redistribution of television corpora, transcripts, or logs
- Not a bundle of pyannote, WhisperX, ECAPA, Llama, InsightFace, or LightASD weights
- InsightFace and LightASD remain **research-only / license review required**

See `docs/LIMITATIONS.md`, `docs/MODEL_POLICY.md`, and `THIRD_PARTY_NOTICES.md`.
