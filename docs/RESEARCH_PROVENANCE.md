# Research provenance

This public-project repository is a **new Git history**. It is not a fork of the private research repository and does not copy that Git database, branches, tags, or implementation.

## Prior private research (documentation only)

Earlier **private** work explored multimodal television speaker attribution as a research prototype, including:

- pyannote-based diarization
- Whisper / WhisperX transcription and alignment
- active-speaker and face-evidence **experiments**
- ECAPA voice similarity
- LoRA-adapted local language-model attribution
- SLURM / A100 experimentation
- graph orchestration with bounded validation retry

Those experiments informed the product shape described in `docs/ARCHITECTURE.md` and `docs/AGENT_GRAPH.md`. They do **not** constitute a production-ready system, and this repository does not ship their code, data, or weights.

## Must not appear here

- show names in fixtures or examples
- dialogue from research transcripts
- screenshots containing transcripts
- model weights
- private filesystem paths
- personal metadata (emails, cluster usernames, account IDs, hostnames, node lists)
- unsupported historical metrics
- claims that the research pipeline was production-ready

## Relationship of repositories

| Repository | Role | Visibility (this phase) |
|---|---|---|
| Private research tree | Historical prototype and research assets | private; not to be made public without history-remediation and legal review |
| `kishuxz/speaker-attribution-video` | Public-project foundation | **private** during G1 |

No private material may be copied into this project.
