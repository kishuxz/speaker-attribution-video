"""Safe subprocess runner for approved media tools only.

The runner never uses a shell, never inherits caller stdin, and never serializes
absolute executable paths, command lines, environment variables, or captured
stdio contents. FFmpeg/FFprobe must be installed separately; this module does
not download or bundle binaries.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from speaker_attribution_video.backends.contracts import CancellationToken
from speaker_attribution_video.media.contracts import ToolExecutionResult
from speaker_attribution_video.media.enums import CaptureStatus, ToolFailureReason, ToolLogicalName
from speaker_attribution_video.media.errors import MediaContractError, ToolError
from speaker_attribution_video.media.identity import MediaToolIdentity, parse_tool_version_line
from speaker_attribution_video.media.policy import SubprocessPolicy
from speaker_attribution_video.media.versions import SUBPROCESS_POLICY_VERSION

_UNSAFE_EXECUTABLE = re.compile(r"[;|&$<>`\n\r\t*?{}()[\]]")
_ALLOWED_BASENAMES = frozenset(name.value for name in ToolLogicalName)
_MAX_ARG_LEN = 4096
_MAX_ARGS = 64
_VERSION_CAPTURE = 4096
_POLL_MS = 20
_ENV = {
    "LANG": "C",
    "LC_ALL": "C",
    "TZ": "UTC",
}


@dataclass(frozen=True, slots=True)
class ToolRun:
    """Internal capture. Stdio bytes must not be logged or serialized."""

    result: ToolExecutionResult
    stdout: bytes
    stderr: bytes


class MediaToolRunner:
    """Execute configured ffmpeg/ffprobe binaries with argument arrays."""

    def __init__(
        self,
        *,
        executables: Mapping[str, str],
        policy: SubprocessPolicy | None = None,
    ) -> None:
        self._policy = policy if policy is not None else SubprocessPolicy()
        self._executables = self._resolve_all(executables)

    def close(self) -> None:
        return

    def identity_for(self, logical_name: ToolLogicalName) -> MediaToolIdentity:
        run = self.run(logical_name, ("-version",), timeout_ms=min(5_000, self._policy.timeout_ms))
        first = run.stdout.decode("utf-8", errors="replace").splitlines()[:1]
        line = first[0] if first else ""
        try:
            version = parse_tool_version_line(logical_name.value, line)
        except MediaContractError as exc:
            raise ToolError(
                ToolFailureReason.UNSUPPORTED_VERSION,
                "media tool version is unsupported or malformed",
            ) from exc
        digest = hashlib.sha256(run.stdout[:_VERSION_CAPTURE]).hexdigest()
        return MediaToolIdentity(
            logical_name=logical_name,
            version=version,
            version_sha256=digest,
        )

    def run(
        self,
        logical_name: ToolLogicalName,
        arguments: Sequence[str],
        *,
        cancel: CancellationToken | None = None,
        timeout_ms: int | None = None,
    ) -> ToolRun:
        if cancel is not None and cancel.is_cancelled():
            raise ToolError(ToolFailureReason.CANCELLATION, "cancelled")
        executable = self._executables.get(logical_name)
        if executable is None:
            raise ToolError(ToolFailureReason.UNSAFE_CONFIGURATION, "tool is not configured")
        argv = self._build_argv(arguments)
        timeout = self._policy.timeout_ms if timeout_ms is None else timeout_ms
        if timeout < 1:
            raise ToolError(ToolFailureReason.UNSAFE_CONFIGURATION, "timeout is invalid")
        spawned = self._execute(
            executable,
            argv,
            timeout_ms=timeout,
            cancel=cancel,
        )
        (
            stdout,
            stderr,
            exit_status,
            duration_us,
            timed_out,
            cancelled,
            attempts,
            out_cut,
            err_cut,
        ) = spawned
        stdout_status, stdout_kept = self._capture_status(
            stdout, self._policy.max_stdout_bytes, truncated=out_cut
        )
        stderr_status, stderr_kept = self._capture_status(
            stderr, self._policy.max_stderr_bytes, truncated=err_cut
        )
        result = ToolExecutionResult(
            logical_name=logical_name,
            policy_version=SUBPROCESS_POLICY_VERSION,
            duration_us=duration_us,
            exit_status=exit_status,
            stdout_status=stdout_status,
            stderr_status=stderr_status,
            stdout_bytes=len(stdout_kept),
            stderr_bytes=len(stderr_kept),
            stdout_sha256=hashlib.sha256(stdout_kept).hexdigest() if stdout_kept else None,
            stderr_sha256=hashlib.sha256(stderr_kept).hexdigest() if stderr_kept else None,
            timed_out=timed_out,
            cancelled=cancelled,
            launch_attempts=attempts,
        )
        captured = ToolRun(result=result, stdout=stdout_kept, stderr=stderr_kept)
        if cancelled:
            raise ToolError(ToolFailureReason.CANCELLATION, "cancelled")
        if timed_out:
            raise ToolError(ToolFailureReason.TIMEOUT, "media tool timed out")
        if stdout_status is CaptureStatus.TRUNCATED or stderr_status is CaptureStatus.TRUNCATED:
            raise ToolError(
                ToolFailureReason.OUTPUT_LIMIT_EXCEEDED,
                "media tool output exceeded the configured bound",
            )
        if exit_status is None:
            raise ToolError(
                ToolFailureReason.LAUNCH_FAILURE, "media tool did not report an exit status"
            )
        if exit_status != 0:
            raise ToolError(ToolFailureReason.NONZERO_EXIT, "media tool exited unsuccessfully")
        return captured

    @staticmethod
    def _capture_status(
        payload: bytes, limit: int, *, truncated: bool
    ) -> tuple[CaptureStatus, bytes]:
        kept = payload[:limit]
        if truncated:
            return CaptureStatus.TRUNCATED, kept
        if not kept:
            return CaptureStatus.EMPTY, b""
        return CaptureStatus.COMPLETE, kept

    def _resolve_all(self, executables: Mapping[str, str]) -> dict[ToolLogicalName, Path]:
        resolved: dict[ToolLogicalName, Path] = {}
        for raw_name, configured in executables.items():
            try:
                logical = ToolLogicalName(raw_name)
            except ValueError as exc:
                raise ToolError(
                    ToolFailureReason.UNSAFE_CONFIGURATION,
                    "tool logical name is not approved",
                ) from exc
            resolved[logical] = self._resolve_one(logical, configured)
        return resolved

    def _resolve_one(self, logical: ToolLogicalName, configured: str) -> Path:
        if not isinstance(configured, str) or not configured or len(configured) > 512:
            raise ToolError(
                ToolFailureReason.UNSAFE_CONFIGURATION, "executable configuration is invalid"
            )
        if _UNSAFE_EXECUTABLE.search(configured) is not None:
            raise ToolError(
                ToolFailureReason.UNSAFE_CONFIGURATION, "executable configuration is unsafe"
            )
        if os.sep in configured or (os.altsep is not None and os.altsep in configured):
            path = Path(configured)
            if not path.is_absolute() or ".." in path.parts:
                raise ToolError(
                    ToolFailureReason.UNSAFE_CONFIGURATION,
                    "configured executable path is unsafe",
                )
            candidate = path
        else:
            if configured != logical.value:
                raise ToolError(
                    ToolFailureReason.UNSAFE_CONFIGURATION,
                    "executable name is not approved",
                )
            found = shutil.which(configured)
            if found is None:
                raise ToolError(
                    ToolFailureReason.TOOL_MISSING, "configured media tool is not installed"
                )
            candidate = Path(found)
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            raise ToolError(
                ToolFailureReason.TOOL_MISSING, "configured media tool is not installed"
            ) from exc
        basename = resolved.name.lower()
        stem = resolved.stem.lower()
        if basename not in _ALLOWED_BASENAMES and stem not in _ALLOWED_BASENAMES:
            raise ToolError(
                ToolFailureReason.UNSAFE_CONFIGURATION,
                "resolved executable basename is not approved",
            )
        if not resolved.is_file():
            raise ToolError(
                ToolFailureReason.TOOL_MISSING, "configured media tool is not installed"
            )
        return resolved

    def _build_argv(self, arguments: Sequence[str]) -> list[str]:
        if not isinstance(arguments, Sequence) or isinstance(arguments, str | bytes):
            raise ToolError(ToolFailureReason.UNSAFE_CONFIGURATION, "argument list is invalid")
        if len(arguments) < 1 or len(arguments) > _MAX_ARGS:
            raise ToolError(ToolFailureReason.UNSAFE_CONFIGURATION, "argument list is invalid")
        cleaned: list[str] = []
        for item in arguments:
            if not isinstance(item, str) or not item or len(item) > _MAX_ARG_LEN or "\x00" in item:
                raise ToolError(ToolFailureReason.UNSAFE_CONFIGURATION, "argument is invalid")
            if "\n" in item or "\r" in item:
                raise ToolError(ToolFailureReason.UNSAFE_CONFIGURATION, "argument is invalid")
            cleaned.append(item)
        if cleaned[0] != "-nostdin":
            cleaned = ["-nostdin", *cleaned]
        return cleaned

    def _execute(
        self,
        executable: Path,
        argv: list[str],
        *,
        timeout_ms: int,
        cancel: CancellationToken | None,
    ) -> tuple[bytes, bytes, int | None, int, bool, bool, int, bool, bool]:
        attempts = 0
        last_error: OSError | None = None
        retries = self._policy.max_launch_retries
        while attempts <= retries:
            attempts += 1
            try:
                return self._spawn(
                    executable,
                    argv,
                    timeout_ms=timeout_ms,
                    cancel=cancel,
                    attempts=attempts,
                )
            except FileNotFoundError as exc:
                raise ToolError(
                    ToolFailureReason.TOOL_MISSING, "media tool could not be launched"
                ) from exc
            except OSError as exc:
                last_error = exc
                if attempts > retries:
                    break
        raise ToolError(
            ToolFailureReason.LAUNCH_FAILURE, "media tool could not be launched"
        ) from last_error

    def _spawn(
        self,
        executable: Path,
        argv: list[str],
        *,
        timeout_ms: int,
        cancel: CancellationToken | None,
        attempts: int,
    ) -> tuple[bytes, bytes, int | None, int, bool, bool, int, bool, bool]:
        command = [str(executable), *argv]
        start = time.monotonic_ns()
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(_ENV),
            shell=False,
            start_new_session=True,
        )
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        stdout_truncated = [False]
        stderr_truncated = [False]
        stdout_thread = threading.Thread(
            target=_bounded_read,
            args=(process.stdout, self._policy.max_stdout_bytes, stdout_chunks, stdout_truncated),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_bounded_read,
            args=(process.stderr, self._policy.max_stderr_bytes, stderr_chunks, stderr_truncated),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        timed_out = False
        cancelled = False
        deadline = start + timeout_ms * 1_000_000
        try:
            while process.poll() is None:
                if cancel is not None and cancel.is_cancelled():
                    cancelled = True
                    _ensure_stopped(
                        process,
                        grace_ms=self._policy.terminate_grace_ms,
                        kill_ms=self._policy.kill_timeout_ms,
                    )
                    break
                if time.monotonic_ns() >= deadline:
                    timed_out = True
                    _ensure_stopped(
                        process,
                        grace_ms=self._policy.terminate_grace_ms,
                        kill_ms=self._policy.kill_timeout_ms,
                    )
                    break
                time.sleep(_POLL_MS / 1000)
            if process.poll() is None:
                process.wait(timeout=max(0.05, self._policy.kill_timeout_ms / 1000))
        except ToolError:
            _close_pipes(process)
            raise
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            _stop_process(
                process,
                grace_ms=self._policy.terminate_grace_ms,
                kill_ms=self._policy.kill_timeout_ms,
            )
            _close_pipes(process)
            raise ToolError(
                ToolFailureReason.LAUNCH_FAILURE, "media tool execution failed"
            ) from exc
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        _close_pipes(process)
        duration_us = max(0, (time.monotonic_ns() - start) // 1000)
        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)
        if stdout_truncated[0]:
            stdout = stdout[: self._policy.max_stdout_bytes]
        if stderr_truncated[0]:
            stderr = stderr[: self._policy.max_stderr_bytes]
        code = process.returncode
        if code is not None and code < 0:
            code = None
        return (
            stdout,
            stderr,
            code,
            duration_us,
            timed_out,
            cancelled,
            attempts,
            stdout_truncated[0],
            stderr_truncated[0],
        )


def _bounded_read(
    pipe: object,
    limit: int,
    chunks: list[bytes],
    truncated: list[bool],
) -> None:
    if pipe is None:
        return
    remaining = limit
    try:
        while True:
            data = pipe.read(65536)  # type: ignore[attr-defined]
            if not data:
                return
            if remaining <= 0:
                truncated[0] = True
                continue
            if len(data) > remaining:
                chunks.append(data[:remaining])
                truncated[0] = True
                remaining = 0
                continue
            chunks.append(data)
            remaining -= len(data)
    except OSError:
        return


def _ensure_stopped(process: subprocess.Popen[bytes], *, grace_ms: int, kill_ms: int) -> None:
    if not _stop_process(process, grace_ms=grace_ms, kill_ms=kill_ms):
        raise ToolError(
            ToolFailureReason.PROCESS_UNSTOPPABLE,
            "media tool process could not be stopped",
        )


def _stop_process(process: subprocess.Popen[bytes], *, grace_ms: int, kill_ms: int) -> bool:
    if process.poll() is not None:
        return True
    pid = process.pid
    if pid is None or pid <= 1:
        return False
    try:
        if os.name == "posix":
            os.killpg(pid, signal.SIGTERM)
        else:
            process.terminate()
    except (ProcessLookupError, OSError):
        return process.poll() is not None
    if _wait(process, grace_ms):
        return True
    try:
        if os.name == "posix":
            os.killpg(pid, signal.SIGKILL)
        else:
            process.kill()
    except (ProcessLookupError, OSError):
        return process.poll() is not None
    return _wait(process, kill_ms)


def _wait(process: subprocess.Popen[bytes], timeout_ms: int) -> bool:
    try:
        process.wait(timeout=max(0.001, timeout_ms / 1000))
    except subprocess.TimeoutExpired:
        return process.poll() is not None
    return True


def _close_pipes(process: subprocess.Popen[bytes]) -> None:
    for pipe in (process.stdout, process.stderr):
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                continue
