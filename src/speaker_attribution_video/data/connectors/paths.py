"""Safe path containment. Never logs or returns absolute filesystem paths."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from speaker_attribution_video.data.connector import ConnectorError
from speaker_attribution_video.data.enums import ConnectorFailureReason

_RELATIVE_REF_MAX = 256


def require_relative_request(requested: str) -> str:
    if not isinstance(requested, str) or not requested or len(requested) > _RELATIVE_REF_MAX:
        raise ConnectorError(ConnectorFailureReason.INVALID_INPUT, "media reference is invalid")
    if (
        "\\" in requested
        or requested.startswith(("/", "\\"))
        or ":\\" in requested
        or "://" in requested
    ):
        raise ConnectorError(ConnectorFailureReason.PATH_ESCAPE, "absolute paths are not allowed")
    parts = Path(requested.replace("\\", "/")).parts
    if any(part in {os.pardir, os.curdir, ""} for part in parts):
        raise ConnectorError(ConnectorFailureReason.PATH_ESCAPE, "path traversal is not allowed")
    if "\x00" in requested:
        raise ConnectorError(ConnectorFailureReason.INVALID_INPUT, "media reference is invalid")
    return requested.replace("\\", "/")


def resolve_inside_root(root: Path, requested: str) -> Path:
    relative = require_relative_request(requested)
    if not root.is_dir():
        raise ConnectorError(
            ConnectorFailureReason.UNSAFE_CONFIGURATION,
            "allowed root is missing or not a directory",
        )
    root_resolved = root.resolve()
    candidate = root_resolved / relative
    if candidate.is_symlink():
        resolved = candidate.resolve()
        if not _is_relative_to(resolved, root_resolved):
            raise ConnectorError(
                ConnectorFailureReason.PATH_ESCAPE,
                "symlink escape is not allowed",
            )
    else:
        resolved = candidate.resolve()
    if not _is_relative_to(resolved, root_resolved):
        raise ConnectorError(ConnectorFailureReason.PATH_ESCAPE, "path is outside the allowed root")
    return resolved


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def require_regular_file(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ConnectorError(ConnectorFailureReason.INVALID_INPUT, "file is missing") from exc
    except OSError as exc:
        raise ConnectorError(
            ConnectorFailureReason.IO_FAILURE, "file could not be inspected"
        ) from exc
    mode = info.st_mode
    if stat.S_ISLNK(mode):
        # Inside-root symlinks are resolved by the caller; dangling links fail.
        try:
            info = path.stat()
        except OSError as exc:
            raise ConnectorError(
                ConnectorFailureReason.INVALID_INPUT, "symlink target is missing"
            ) from exc
        mode = info.st_mode
    if stat.S_ISDIR(mode):
        raise ConnectorError(ConnectorFailureReason.INVALID_INPUT, "a regular file is required")
    if stat.S_ISCHR(mode) or stat.S_ISBLK(mode) or stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode):
        raise ConnectorError(ConnectorFailureReason.INVALID_INPUT, "special files are not allowed")
    if not stat.S_ISREG(mode):
        raise ConnectorError(ConnectorFailureReason.INVALID_INPUT, "a regular file is required")
    return info
