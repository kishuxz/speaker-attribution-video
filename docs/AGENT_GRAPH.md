# Agent graph

Intended graph for a later implementation phase. **G1 does not execute these nodes.** It only defines typed evidence/execution records that a future pipeline can write.

| Node | Kind | G1 status | Responsibility |
|---|---|---|---|
| preprocessor | deterministic | planned | Audio extract; run diarization + transcription backends |
| format_detector | heuristic | planned | Lightweight format cues from caller metadata — no title catalog |
| context_extractor | deterministic/NLP | planned | Mentions, vocatives, introductions from transcript text |
| video_agent | optional | planned | Face / active-speaker features when licensed backends exist |
| fusion | deterministic | planned | Merge audio and optional video signals |
| sequence_decoder | bounded | planned | Temporal consistency over SPEAKER_N sequences |
| resegmenter | deterministic | planned | Turn boundaries from alignment |
| speaker_resolver | bounded agent | planned | Map SPEAKER_N → names or `unresolved` |
| validator | gate | **contracts only** | Constraints; at most one bounded retry (`CorrectionAttempt`) |
| demographic / topic | optional research | planned | Out of default product path unless explicitly enabled |
| format_converter | deterministic | planned | Export attributed transcript + evidence graph |

## Bounds (encoded in G1, not executed)

- Validator retry: **one** by default (`max_correction_attempts`).
- Resolver must not invent names absent from the candidate set in the graph.
- Empty or conflicting evidence → `UNRESOLVED` or `CONTRADICTED`, not a best guess.

Agents in the private research prototype inspired this sketch. Their source is **not** copied here.
