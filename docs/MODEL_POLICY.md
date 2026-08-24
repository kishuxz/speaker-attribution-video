# Model policy

## Original code vs models

Apache-2.0 covers original source in this repository only. Model weights, tokenizers, and checkpoints keep their own licenses.

## F0 rule

This repository **must not** download or bundle weights. There is no silent `from_pretrained` on import. CI must not require hub credentials.

## Intended backends (not implemented in F0)

| Backend | Interface | Implementation status |
|---|---|---|
| pyannote diarization | `DiarizationBackend` | docs/interface only |
| Whisper / WhisperX | `TranscriptionBackend` | docs/interface only |
| ECAPA (SpeechBrain) | `VoiceSimilarityBackend` | docs/interface only |
| Llama-family attribution LM | `AttributionLanguageModelBackend` | docs/interface only |
| InsightFace | `FaceEvidenceBackend` | **research-only / license review required** |
| LightASD | `ActiveSpeakerBackend` | **research-only / license review required** |

InsightFace and LightASD must not be implemented, imported, or downloaded in this repository until their licenses and model terms are independently verified.

## Credentials

`HF_TOKEN` may appear as a name in `.env.example`. Values are never committed. F0 code does not read `HF_TOKEN`.
