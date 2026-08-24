# Agent graph

Intended graph for a later implementation phase. F0 has no executable graph.

| Node | Kind | Responsibility |
|---|---|---|
| preprocessor | deterministic | Audio extract; run diarization + transcription backends |
| format_detector | heuristic | Lightweight show/format cues from metadata the caller provides — no hardcoded catalog of titles |
| context_extractor | deterministic/NLP | Mentions, vocatives, introductions from transcript text |
| video_agent | optional | Face / active-speaker features when licensed backends exist |
| fusion | deterministic | Merge audio and optional video signals; drop unused fields |
| sequence_decoder | bounded | Temporal consistency over SPEAKER_N sequences |
| resegmenter | deterministic | Turn boundaries from alignment |
| speaker_resolver | bounded agent | Map SPEAKER_N → names or `unresolved` |
| validator | gate | Check constraints; at most one bounded retry |
| demographic / topic | optional research | Out of default product path unless explicitly enabled |
| format_converter | deterministic | Export attributed transcript + evidence graph |

## Bounds

- Validator retry: **one** retry unless a later spec changes this in writing.
- Resolver must not invent names absent from evidence.
- Empty or conflicting evidence → `unresolved`, not a best guess.

Agents in the private research prototype inspired this sketch. Their source is **not** copied here.
