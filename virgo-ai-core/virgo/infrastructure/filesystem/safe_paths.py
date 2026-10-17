"""Rust-backed path containment boundary."""

from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from virgo.contracts.errors import RustCoreError, SecurityViolationError


class _RustCoreProtocol(Protocol):
    def validate_workspace_path(
        self, workspace_root: str, relative_path: str
    ) -> str: ...


def validate_workspace_path(workspace_root: Path, relative_path: str) -> Path:
    """Return one canonical existing path contained by the workspace root."""
    try:
        core = cast(_RustCoreProtocol, import_module("virgo._rust_core"))
        resolved = core.validate_workspace_path(str(workspace_root), relative_path)
        if resolved.startswith("\\\\?\\UNC\\"):
            resolved = "\\\\" + resolved[8:]
        elif resolved.startswith("\\\\?\\"):
            resolved = resolved[4:]
        return Path(resolved)
    except ValueError as error:
        raise SecurityViolationError(
            "Workspace path validation blocked an unsafe path",
            technical_detail=str(error),
            source_module=__name__,
            cause=error,
        ) from error
    except (ImportError, AttributeError) as error:
        raise RustCoreError(
            "Rust filesystem safety boundary is unavailable",
            technical_detail=str(error),
            source_module=__name__,
            cause=error,
        ) from error
