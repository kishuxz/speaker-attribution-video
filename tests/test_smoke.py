from __future__ import annotations

import pytest

from speaker_attribution_video import __version__
from speaker_attribution_video.cli import main
from speaker_attribution_video.integrations import (
    ActiveSpeakerBackend,
    FaceEvidenceBackend,
)


def test_import_version() -> None:
    assert __version__ == "0.1.0"


def test_cli_help() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_version(capsys) -> None:
    assert main(["--version"]) == 0
    assert "0.1.0" in capsys.readouterr().out


def test_cli_default_help_text(capsys) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "Speaker Attribution Graph" in out
    assert "No inference" in out


def test_research_only_backends_are_documented() -> None:
    assert "research-only" in (FaceEvidenceBackend.__doc__ or "").lower()
    assert "research-only" in (ActiveSpeakerBackend.__doc__ or "").lower()
