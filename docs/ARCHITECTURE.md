# Architecture

F0 defines the intended shape. Runtime implementations are not in this repository yet.

```
media (caller-supplied, not in git)
        │
        ▼
┌───────────────────┐
│  Deterministic    │  diarization + transcription/alignment
│  signal layer     │  (pyannote, Whisper/WhisperX — adapters later)
└─────────┬─────────┘
          │ SPEAKER_N turns + text (+ optional video features)
          ▼
┌───────────────────┐
│  Evidence graph   │  nodes/edges for audio, text, optional face/ASD
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  Bounded agents   │  attribution with validation and limited retry
└─────────┬─────────┘
          ▼
   named turns, unresolved cases, evaluation + observability exports
```

## Layers

1. **Ingest** — caller provides paths via configuration. The project never vendors media.
2. **Deterministic signals** — diarization and ASR/alignment. These should be replayable given the same inputs and tool versions.
3. **Optional video signals** — active-speaker / face evidence, behind interfaces. InsightFace and LightASD stay unimplemented pending license review.
4. **Attribution agents** — bounded LLM (or equivalent) mapping with validators. Unresolved is valid output.
5. **Evidence graph** — structured provenance of each decision.
6. **Evaluation / observability** — metrics only from declared protocols; no unsupported historical numbers.

Python **3.11** is the only supported runtime.
