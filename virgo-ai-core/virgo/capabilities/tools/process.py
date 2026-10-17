"""Rust-backed allowlisted validation process execution."""

from __future__ import annotations

import shutil
import sys
import tempfile
from importlib import import_module
from pathlib import Path
from threading import Event
from typing import Protocol, cast

from virgo.contracts.errors import (
    OperationTimeoutError,
    SecurityViolationError,
    ToolExecutionError,
)
from virgo.contracts.models import ProcessRequest, ProcessResult, ValidationStatus

TOOL_COMMANDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "python_compile": (sys.executable, ("-m", "compileall", "-q")),
    "pytest": (sys.executable, ("-m", "pytest")),
    "ruff": (sys.executable, ("-m", "ruff", "check")),
    "mypy": (sys.executable, ("-m", "mypy")),
    "black_check": (sys.executable, ("-m", "black", "--check")),
    "cargo_test": (shutil.which("cargo") or "", ("test", "--locked")),
    "git_head": (shutil.which("git") or "", ("rev-parse", "HEAD")),
    "git_status": (shutil.which("git") or "", ("status", "--porcelain")),
    "git_branch": (shutil.which("git") or "", ("switch", "-c")),
    "git_add": (shutil.which("git") or "", ("add", "--")),
    "git_commit": (shutil.which("git") or "", ("commit", "-m")),
}


class _RustProcessProtocol(Protocol):
    def run_validation_process(
        self,
        executable: str,
        arguments: list[str],
        working_directory: str,
        timeout_ms: int,
        cancellation_marker: str,
    ) -> tuple[int, str, str, bool, bool]: ...


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()
        self._marker = Path(tempfile.gettempdir()) / f"virgo-cancel-{id(self)}"
        self._marker.unlink(missing_ok=True)

    @property
    def marker(self) -> Path:
        return self._marker

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
        self._marker.touch(exist_ok=True)

    def close(self) -> None:
        self._marker.unlink(missing_ok=True)


class ValidationProcessTool:
    """Expose fixed validation commands, never raw shell strings."""

    def __init__(self, approved_workspace: Path) -> None:
        if not approved_workspace.is_absolute() or not approved_workspace.is_dir():
            raise SecurityViolationError(
                "Approved validation workspace is invalid", source_module=__name__
            )
        self._workspace = approved_workspace.resolve(strict=True)

    def run(
        self, request: ProcessRequest, cancellation: CancellationToken
    ) -> ProcessResult:
        if request.tool_name not in TOOL_COMMANDS:
            raise SecurityViolationError(
                "Validation command is not allowlisted", source_module=__name__
            )
        executable, prefix = TOOL_COMMANDS[request.tool_name]
        if not executable or not Path(executable).is_file():
            raise ToolExecutionError(
                "Allowlisted validation tool is unavailable", source_module=__name__
            )
        workspace = Path(request.working_directory)
        if not workspace.is_absolute() or not workspace.is_dir():
            raise SecurityViolationError(
                "Validation working directory is invalid", source_module=__name__
            )
        resolved_workspace = workspace.resolve(strict=True)
        if (
            resolved_workspace != self._workspace
            and self._workspace not in resolved_workspace.parents
        ):
            raise SecurityViolationError(
                "Validation working directory is outside the approved workspace",
                source_module=__name__,
            )
        if any(
            argument in {"|", ";", "&&", "||", ">", "<"}
            for argument in request.arguments
        ):
            raise SecurityViolationError(
                "Shell syntax is not accepted as a process argument",
                source_module=__name__,
            )
        if any(
            Path(argument).is_absolute() or ".." in Path(argument).parts
            for argument in request.arguments
        ):
            raise SecurityViolationError(
                "Validation arguments escape the approved workspace",
                source_module=__name__,
            )
        if cancellation.cancelled:
            return ProcessResult(
                request_id=request.request_id,
                exit_code=-1,
                stdout="",
                stderr="",
                status=ValidationStatus.CANCELLED,
            )
        try:
            core = cast(_RustProcessProtocol, import_module("virgo._rust_core"))
            code, stdout, stderr, timed_out, cancelled = core.run_validation_process(
                executable,
                [*prefix, *request.arguments],
                str(resolved_workspace),
                int(request.timeout_seconds * 1000),
                str(cancellation.marker),
            )
        except (ValueError, PermissionError, OSError) as error:
            raise ToolExecutionError(
                "Validation process could not run",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error
        if timed_out:
            raise OperationTimeoutError(
                "Validation process exceeded its timeout", source_module=__name__
            )
        status = (
            ValidationStatus.CANCELLED
            if cancelled
            else ValidationStatus.PASSED if code == 0 else ValidationStatus.FAILED
        )
        return ProcessResult(
            request_id=request.request_id,
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            status=status,
        )
