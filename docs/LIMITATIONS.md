# Limitations

- **G1 is graph contracts only.** It does not transcribe, diarize, attribute speakers, or run agents.
- Graph provenance is **not proof**. Confidence is **not correctness**.
- Overlapping speech can be represented; it is not processed.
- Prior private research is **not** claimed to have been production-ready.
- Diarization errors cannot be fully repaired by text-only agents (when those agents exist).
- Optional video evidence remains unimplemented; InsightFace and LightASD are **not** available pending license review.
- Attribution may return `UNRESOLVED`. That is success of the policy, not a failure to “guess.”
- Third-party tools (pyannote, WhisperX, Llama, ECAPA) have their own hardware, license, and quality limits and are not integrated.
- Synthetic fixtures are engineering tests, not accuracy benchmarks.
- This repository is private during G1; Apache-2.0 on original source does not imply a public release.
