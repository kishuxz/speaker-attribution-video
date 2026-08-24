# Data policy

## This repository

- Original source is Apache-2.0.
- **No research datasets, transcripts, media, weights, W&B metadata, or SLURM logs** may be committed.
- Synthetic fixtures are allowed **only** under `tests/fixtures/synthetic/` and must not use real show names or copyrighted dialogue.
- The repository is **private** during D1. Publication does not license third-party data.

## Graph payloads

The G1 graph does not require raw audio or video bytes. Transcript text is sensitive: use redaction, a normalized text hash, an external content reference, or explicit opt-in embedded text with a sensitive/restricted classification. Raw transcript content must not appear in logs or exception messages by default.

## Ingestion manifests (D1)

Media manifests describe artifacts without embedding file bytes or absolute local paths. Unknown or missing license fields are **not** permission. User attestation is **not** independent verification. Local ingestion is **not** license verification. The application does not automate acceptance of third-party terms. A later policy engine is **not** legal advice.

Only synthetic fixtures and user-supplied local files are supported as runtime sources. There is no network dataset connector. Historical television research data is not part of this repository. Research-only data cannot be emitted into public fixtures or package artifacts.

## Caller data

Users will run a future pipeline on media they are authorized to process. This project does not grant rights to television corpora or any private research collection.

## Private research repository

A separate private repository holds prior research assets. **Do not copy** those assets, Git history, or implementation into this project.

## Retention

Do not store production media in git. Local caches belong in directories named by environment variables (see `.env.example`) and remain untracked.
