# Agent instructions

This repository is the **public-project foundation** for Speaker Attribution Graph (`kishuxz/speaker-attribution-video`). It is private during F0.

## Rules

1. **Python 3.11 only.** Do not add 3.12+ or 3.10 syntax or classifiers.
2. **Do not copy implementation** from the private research repository `kishuxz/speaker-diarization` (or any clone of it). Provenance belongs in `docs/RESEARCH_PROVENANCE.md` at documentation level only.
3. **Do not download models or datasets.** Do not use Hugging Face credentials. Do not vendor weights.
4. **InsightFace and LightASD** are research-only until independent license review. Do not implement or import them here.
5. **Do not publish** research datasets, transcripts, dialogue fixtures, show names in examples, weights, W&B metadata, SLURM logs, private paths, personal metadata, or unsupported historical metrics.
6. **Apache-2.0** applies only to original source in this repo. Do not claim it covers third-party models or datasets.
7. **PR discipline:** one issue per change; one focused PR; no direct pushes to `main`; tests and docs required; merge only with green CI; do not create artificial commit activity.
8. **Stop at the current approved phase.** Do not start G1 or production logic until asked.
9. Preserve honest limitations. Unresolved cases stay unresolved; do not invent speaker names in examples.

## Package layout

Original code lives under `src/speaker_attribution_video/`. Third-party backends are `typing.Protocol` stubs in `integrations/` until a later phase implements adapters behind those interfaces.
