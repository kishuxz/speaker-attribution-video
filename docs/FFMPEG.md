# FFmpeg / FFprobe

FFmpeg and FFprobe are **externally installed** media tools. This repository
does not vendor, wrap in a shell, or silently download them.

## License

Apache-2.0 in `LICENSE` covers **original source in this repository only**. It
does **not** relicense FFmpeg, libavcodec, or any codec implementation. Callers
must obtain FFmpeg under its own license terms (typically LGPL/GPL depending on
the build). See `THIRD_PARTY_NOTICES.md`.

## Configuration

Executables are selected by explicit configuration (`ffmpeg` / `ffprobe` logical
names, or absolute paths whose basename is `ffmpeg`/`ffprobe`). User-controlled
arbitrary executables are rejected. Invocations use `subprocess` argument
arrays with `shell=False`.

## Reproducibility

Do **not** claim universal byte-identical output across all FFmpeg versions and
builds. The supported claim, once normalization lands, is:

> Identical accepted source bytes, normalization policy, and recorded FFmpeg
> toolchain fingerprint should produce an identical canonical artifact **within
> the verified toolchain**.

The toolchain fingerprint records logical names, parsed version tokens, and a
hash of bounded `-version` output. Absolute install paths are not serialized.

## CI

Core quality/test jobs stay FFmpeg-free. Real-tool checks belong in the later
`media-integration` job, which must print `ffmpeg -version` and
`ffprobe -version` and run only synthetic fixtures.
