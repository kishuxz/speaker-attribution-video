"""Controlled temporary workspace for media-tool outputs. Never stores source media."""

from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path

from speaker_attribution_video.media.enums import ToolFailureReason
from speaker_attribution_video.media.errors import MediaContractError, ToolError

_ALLOWED_SUFFIXES = frozenset({".wav", ".json", ".tmp"})
_DIR_MODE = 0o700


class TemporaryWorkspace:
    """Allocate files under an explicit root and delete them on close."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise MediaContractError("workspace.root", "workspace root must be a path")
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(self._root, _DIR_MODE)
        self._closed = False

    @property
    def root(self) -> Path:
        return self._root

    def allocate(self, *, suffix: str = ".tmp") -> Path:
        if self._closed:
            raise ToolError(ToolFailureReason.UNSAFE_CONFIGURATION, "workspace is closed")
        if suffix not in _ALLOWED_SUFFIXES:
            raise MediaContractError("workspace.suffix", "temporary suffix is not allowed")
        name = secrets.token_hex(16) + suffix
        path = (self._root / name).resolve()
        try:
            path.relative_to(self._root.resolve())
        except ValueError as exc:
            raise MediaContractError(
                "workspace.traversal", "temporary path escaped the root"
            ) from exc
        return path

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._root.exists():
            shutil.rmtree(self._root, ignore_errors=True)

    def __enter__(self) -> TemporaryWorkspace:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
