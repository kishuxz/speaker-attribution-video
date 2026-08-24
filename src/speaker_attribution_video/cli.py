"""CLI stub. F0 does not run diarization, transcription, or attribution."""

from __future__ import annotations

import argparse
import sys

from speaker_attribution_video import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="speaker-attribution-video",
        description=(
            "Speaker Attribution Graph — foundation only. No inference, no model download."
        ),
    )
    parser.add_argument("--version", action="store_true", help="print package version")
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
