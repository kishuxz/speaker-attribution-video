"""Narrow magic-byte sniffing. Extension is never authoritative. No media decode."""

from __future__ import annotations

HEADER_BYTES = 16


def sniff_media_type(header: bytes) -> str | None:
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "audio/wav"
    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video/mp4"
    if header.startswith(b"fLaC"):
        return "audio/flac"
    if header.startswith(b"OggS"):
        return "audio/ogg"
    if header.startswith(b"ID3") or header[:2] in {
        b"\xff\xfb",
        b"\xff\xfa",
        b"\xff\xf3",
        b"\xff\xf2",
    }:
        return "audio/mpeg"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    return None
