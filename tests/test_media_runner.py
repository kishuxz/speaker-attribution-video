"""Safe media-tool runner tests. Stub executables only; not FFmpeg integration."""

from __future__ import annotations

import stat
import sys
import threading
from pathlib import Path

import pytest

from speaker_attribution_video.backends.contracts import CancellationToken
from speaker_attribution_video.media.enums import CaptureStatus, ToolFailureReason, ToolLogicalName
from speaker_attribution_video.media.errors import MediaContractError, ToolError
from speaker_attribution_video.media.policy import SubprocessPolicy
from speaker_attribution_video.media.runner import MediaToolRunner
from speaker_attribution_video.media.workspace import TemporaryWorkspace

pytestmark = pytest.mark.unit

_VERSION_SCRIPT = """\
import sys
name = {name!r}
sys.stdout.write(f"{{name}} version 0.0-test Copyright (c) test\\n")
"""

_ECHO_SCRIPT = """\
import sys
sys.stdout.buffer.write(b"ok-stdout")
sys.stderr.buffer.write(b"ok-stderr")
"""

_SLEEP_SCRIPT = """\
import time
time.sleep(8)
"""

_HUGE_SCRIPT = """\
import sys
sys.stdout.buffer.write(b"A" * 20000)
"""

_FAIL_SCRIPT = """\
import sys
sys.exit(3)
"""


def _write_tool(root: Path, logical: str, body: str) -> Path:
    path = root / logical
    path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _runner(
    tmp_path: Path, *, ffprobe_body: str, ffmpeg_body: str | None = None
) -> MediaToolRunner:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    ffprobe = _write_tool(bindir, "ffprobe", ffprobe_body)
    ffmpeg = _write_tool(
        bindir,
        "ffmpeg",
        ffmpeg_body if ffmpeg_body is not None else _VERSION_SCRIPT.format(name="ffmpeg"),
    )
    return MediaToolRunner(
        executables={"ffprobe": str(ffprobe), "ffmpeg": str(ffmpeg)},
        policy=SubprocessPolicy(timeout_ms=2000, max_stdout_bytes=1024, max_stderr_bytes=1024),
    )


def test_runner_source_does_not_invoke_a_shell() -> None:
    from speaker_attribution_video.media import runner as runner_mod

    text = Path(runner_mod.__file__).read_text(encoding="utf-8")
    assert "shell=True" not in text
    assert "shell=False" in text


def test_version_probe_records_identity_without_paths(tmp_path: Path) -> None:
    runner = _runner(tmp_path, ffprobe_body=_VERSION_SCRIPT.format(name="ffprobe"))
    identity = runner.identity_for(ToolLogicalName.FFPROBE)
    assert identity.logical_name is ToolLogicalName.FFPROBE
    assert identity.version == "0.0-test"
    encoded = str(identity.to_dict())
    assert str(tmp_path) not in encoded
    assert "ffprobe" in encoded


def test_successful_run_redacts_stdio_and_is_bounded(tmp_path: Path) -> None:
    runner = _runner(tmp_path, ffprobe_body=_ECHO_SCRIPT)
    captured = runner.run(ToolLogicalName.FFPROBE, ("-show_format",))
    assert captured.stdout == b"ok-stdout"
    public = captured.result.identity_dict()
    assert b"ok-stdout" not in str(public).encode()
    assert public["stdout_status"] == CaptureStatus.COMPLETE.value
    assert public["exit_status"] == 0
    assert "argv" not in public


def test_timeout_is_typed_and_cleans_workspace(tmp_path: Path) -> None:
    runner = _runner(
        tmp_path,
        ffprobe_body=_SLEEP_SCRIPT,
        ffmpeg_body=_SLEEP_SCRIPT,
    )
    workspace = TemporaryWorkspace(tmp_path / "work")
    allocated = workspace.allocate(suffix=".tmp")
    allocated.write_bytes(b"scratch")
    with pytest.raises(ToolError) as exc:
        runner.run(ToolLogicalName.FFPROBE, ("-show_format",), timeout_ms=150)
    assert exc.value.reason is ToolFailureReason.TIMEOUT
    assert str(tmp_path) not in str(exc.value)
    workspace.close()
    assert not allocated.exists()
    assert not workspace.root.exists()


def test_pre_cancelled_run_does_not_start(tmp_path: Path) -> None:
    runner = _runner(tmp_path, ffprobe_body=_SLEEP_SCRIPT)
    token = CancellationToken()
    token.cancel()
    with pytest.raises(ToolError) as exc:
        runner.run(ToolLogicalName.FFPROBE, ("-show_format",), cancel=token)
    assert exc.value.reason is ToolFailureReason.CANCELLATION


def test_mid_run_cancellation(tmp_path: Path) -> None:
    runner = _runner(tmp_path, ffprobe_body=_SLEEP_SCRIPT)
    token = CancellationToken()

    def _cancel() -> None:
        token.cancel()

    timer = threading.Timer(0.05, _cancel)
    timer.start()
    with pytest.raises(ToolError) as exc:
        runner.run(ToolLogicalName.FFPROBE, ("-show_format",), timeout_ms=2000, cancel=token)
    timer.cancel()
    assert exc.value.reason is ToolFailureReason.CANCELLATION


def test_truncated_output_fails_closed(tmp_path: Path) -> None:
    runner = _runner(tmp_path, ffprobe_body=_HUGE_SCRIPT)
    with pytest.raises(ToolError) as exc:
        runner.run(ToolLogicalName.FFPROBE, ("-show_format",))
    assert exc.value.reason is ToolFailureReason.OUTPUT_LIMIT_EXCEEDED


def test_nonzero_exit_is_typed(tmp_path: Path) -> None:
    runner = _runner(tmp_path, ffprobe_body=_FAIL_SCRIPT)
    with pytest.raises(ToolError) as exc:
        runner.run(ToolLogicalName.FFPROBE, ("-show_format",))
    assert exc.value.reason is ToolFailureReason.NONZERO_EXIT


def test_shell_metacharacters_in_executable_are_rejected() -> None:
    with pytest.raises(ToolError) as exc:
        MediaToolRunner(executables={"ffprobe": "ffprobe;true", "ffmpeg": "ffmpeg"})
    assert exc.value.reason is ToolFailureReason.UNSAFE_CONFIGURATION
    assert "ffprobe;true" not in str(exc.value)


def test_unapproved_basename_is_rejected(tmp_path: Path) -> None:
    other = tmp_path / "python-tool"
    other.write_text(f"#!{sys.executable}\nprint('no')\n", encoding="utf-8")
    other.chmod(other.stat().st_mode | stat.S_IXUSR)
    with pytest.raises(ToolError) as exc:
        MediaToolRunner(executables={"ffprobe": str(other), "ffmpeg": str(other)})
    assert exc.value.reason is ToolFailureReason.UNSAFE_CONFIGURATION


def test_missing_tool_is_typed(tmp_path: Path) -> None:
    missing = tmp_path / "ffprobe"
    ffmpeg = _write_tool(tmp_path, "ffmpeg", _VERSION_SCRIPT.format(name="ffmpeg"))
    with pytest.raises(ToolError) as exc:
        MediaToolRunner(executables={"ffprobe": str(missing), "ffmpeg": str(ffmpeg)})
    assert exc.value.reason is ToolFailureReason.TOOL_MISSING
    assert str(missing) not in str(exc.value)


def test_relative_executable_path_is_rejected() -> None:
    with pytest.raises(ToolError) as exc:
        MediaToolRunner(executables={"ffprobe": "bin/ffprobe", "ffmpeg": "ffmpeg"})
    assert exc.value.reason is ToolFailureReason.UNSAFE_CONFIGURATION


def test_unconfigured_tool_and_invalid_args(tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    ffprobe = _write_tool(bindir, "ffprobe", _ECHO_SCRIPT)
    ffmpeg = _write_tool(bindir, "ffmpeg", _VERSION_SCRIPT.format(name="ffmpeg"))
    runner = MediaToolRunner(executables={"ffprobe": str(ffprobe), "ffmpeg": str(ffmpeg)})
    runner.close()
    with pytest.raises(ToolError) as exc:
        runner.run(ToolLogicalName.FFPROBE, ())
    assert exc.value.reason is ToolFailureReason.UNSAFE_CONFIGURATION
    with pytest.raises(ToolError):
        runner.run(ToolLogicalName.FFPROBE, ("-show\nformat",))
    with pytest.raises(ToolError):
        runner.run(ToolLogicalName.FFPROBE, ("-show_format",), timeout_ms=0)


def test_malformed_version_probe(tmp_path: Path) -> None:
    runner = _runner(tmp_path, ffprobe_body=_ECHO_SCRIPT)
    with pytest.raises(ToolError) as exc:
        runner.identity_for(ToolLogicalName.FFPROBE)
    assert exc.value.reason is ToolFailureReason.UNSUPPORTED_VERSION


def test_workspace_rejects_unsafe_use(tmp_path: Path) -> None:
    with pytest.raises(MediaContractError):
        TemporaryWorkspace("not-a-path")  # type: ignore[arg-type]
    workspace = TemporaryWorkspace(tmp_path / "work")
    with pytest.raises(MediaContractError):
        workspace.allocate(suffix=".exe")
    path = workspace.allocate(suffix=".wav")
    path.write_bytes(b"x")
    with workspace:
        pass
    assert not workspace.root.exists()
    with pytest.raises(ToolError):
        workspace.allocate()
    workspace.close()
