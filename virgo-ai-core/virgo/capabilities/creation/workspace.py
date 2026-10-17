"""Bounded, read-only project inspection."""

from hashlib import sha256
from pathlib import Path

from virgo.contracts.errors import SecurityViolationError, ValidationError
from virgo.contracts.models.creation import FileInspection, ProjectInspection
from virgo.infrastructure.filesystem import validate_workspace_path

DEFAULT_MAX_FILES = 1_000
DEFAULT_MAX_TOTAL_BYTES = 10 * 1024 * 1024
EXCLUDED_NAMES = {".git", ".venv", "__pycache__", "node_modules", "target"}
SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    "credentials.json",
    "secrets.json",
    "id_rsa",
    "id_ed25519",
}


class SafeWorkspace:
    """Inspect only existing files under one explicitly selected root."""

    def __init__(
        self,
        root: Path,
        *,
        max_files: int = DEFAULT_MAX_FILES,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    ) -> None:
        if not root.is_absolute() or not root.is_dir():
            raise ValidationError(
                "Workspace root must be an existing absolute directory",
                source_module=__name__,
            )
        if max_files < 1 or max_total_bytes < 1:
            raise ValidationError(
                "Workspace inspection limits must be positive", source_module=__name__
            )
        self._root = root.resolve(strict=True)
        self._max_files = max_files
        self._max_total_bytes = max_total_bytes

    @property
    def root(self) -> Path:
        return self._root

    def inspect(self, requested_paths: tuple[str, ...]) -> ProjectInspection:
        files: list[FileInspection] = []
        total_bytes = 0
        candidates = self._expand(requested_paths)
        for relative_path in candidates:
            path = validate_workspace_path(self._root, relative_path)
            size = path.stat().st_size
            total_bytes += size
            if len(files) >= self._max_files or total_bytes > self._max_total_bytes:
                raise SecurityViolationError(
                    "Workspace inspection exceeded its configured limits",
                    source_module=__name__,
                )
            files.append(
                FileInspection(
                    relative_path=path.relative_to(self._root).as_posix(),
                    size_bytes=size,
                    sha256=sha256(path.read_bytes()).hexdigest(),
                )
            )
        return ProjectInspection(
            workspace_root=str(self._root),
            files=tuple(files),
            total_bytes=total_bytes,
        )

    def read_text(self, relative_path: str) -> str:
        path = validate_workspace_path(self._root, relative_path)
        if path.stat().st_size > self._max_total_bytes:
            raise SecurityViolationError(
                "Requested file exceeds the workspace read limit",
                source_module=__name__,
            )
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ValidationError(
                "Creation preview requires UTF-8 text",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error

    def _expand(self, requested_paths: tuple[str, ...]) -> tuple[str, ...]:
        if not requested_paths:
            raise ValidationError(
                "Workspace inspection requires at least one path",
                source_module=__name__,
            )
        expanded: set[str] = set()
        for requested in requested_paths:
            path = validate_workspace_path(self._root, requested)
            if path.is_file():
                if path.name in SENSITIVE_FILE_NAMES:
                    raise SecurityViolationError(
                        "Sensitive files are excluded from creation inspection",
                        source_module=__name__,
                    )
                expanded.add(path.relative_to(self._root).as_posix())
                continue
            for child in path.rglob("*"):
                if (
                    any(part in EXCLUDED_NAMES for part in child.parts)
                    or child.name in SENSITIVE_FILE_NAMES
                    or not child.is_file()
                ):
                    continue
                expanded.add(child.relative_to(self._root).as_posix())
                if len(expanded) > self._max_files:
                    raise SecurityViolationError(
                        "Workspace inspection exceeded its file limit",
                        source_module=__name__,
                    )
        return tuple(sorted(expanded))
