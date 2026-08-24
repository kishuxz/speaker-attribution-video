# Third-party notices

Apache-2.0 in `LICENSE` covers **original source code in this repository only**.
It does **not** cover models, datasets, pretrained weights, or the projects below.

F0 provides **interfaces and documentation only**. This repository does not
download, vendor, or bundle third-party weights. Callers must obtain each
component under its own terms.

| Component | Role (future) | License / terms | Status in this repository |
|---|---|---|---|
| FFmpeg / FFprobe | Container inspection and canonical audio normalization (MP1) | Separate (LGPL/GPL depending on build; not Apache-2.0 by virtue of this repo) | External dependency; not bundled; invoked only via `MediaToolRunner` |
| pyannote.audio (speaker diarization) | Deterministic diarization backend | Separate (not Apache-2.0 by virtue of this repo) | Interface + docs only; no weights |
| OpenAI Whisper / WhisperX | Transcription and alignment | Separate | Interface + docs only; no weights |
| SpeechBrain ECAPA-TDNN | Voice similarity embeddings | Separate | Interface + docs only; no weights |
| Llama (Meta) | Bounded attribution language model | Separate (Llama community / Meta terms) | Interface + docs only; no weights |
| InsightFace | Face evidence | Separate | **Research-only / license review required.** Not implemented. Do not download or bundle. |
| LightASD | Active-speaker evidence | Separate | **Research-only / license review required.** Not implemented. Do not download or bundle. |

Do not assume any of the above is Apache-2.0-licensed because this project uses Apache-2.0 for original code.

Dataset and television-corpus terms, where applicable, are also separate and are **not** redistributed here.
