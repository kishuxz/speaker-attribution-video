# Media processing (MP1)

MP1 inspects accepted D1 local/synthetic media and normalizes **one** canonical
audio stream. It does **not** diarize, transcribe, align, run models, or start
agents.

This node currently lands **toolchain contracts and a safe subprocess runner**
(MP1A/MP1B). Inspection, FFmpeg normalization, the artifact store, and G1
projection follow in later MP1 PRs.

## External tools

MP1 may invoke separately installed `ffprobe` and `ffmpeg`. Binaries are **not**
bundled and are **not** downloaded by this repository. Apache-2.0 on original
source does **not** relicense FFmpeg or its codecs. See `docs/FFMPEG.md`.

## Safe runner

`MediaToolRunner` accepts only explicitly configured `ffmpeg`/`ffprobe`
executables. It uses argument arrays with `shell=False`, disables inherited
stdin, uses a minimal environment, bounds stdout/stderr, honors timeout and
cancellation, and terminates the process group it created. Default errors do
not include absolute paths, command lines, environment variables, media
filenames, or media bytes.

Core CI remains model-free and does **not** require FFmpeg. Stub executables
prove runner behavior. A later `media-integration` job will run real tools on
synthetic fixtures only.

## Canonical audio (later MP1E)

Future normalization target: WAV, signed 16-bit little-endian PCM, mono,
16 kHz. That artifact is the only audio future diarization/transcription
backends may consume. Pyannote must not be run twice on unnormalized media.

## What MP1 does not do

* No diarization, transcription, alignment, or video evidence
* No model inference and no Hugging Face downloads
* No network input protocols
* No logging of raw media
* Historical television research data is not part of this repository
