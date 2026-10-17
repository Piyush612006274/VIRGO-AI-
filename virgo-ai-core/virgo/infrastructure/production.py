"""Small standard-library production hardening services."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from virgo.contracts.errors import StorageError, ValidationError
from virgo.contracts.models.production import (
    BackupManifest,
    BackupResult,
    HardwareProfile,
    ProductionProviderStatus,
    UpdateStatus,
)

MAX_BACKUP_FILES = 20
MAX_BACKUP_BYTES = 100 * 1024 * 1024
ALLOWED_DATA_DIRECTORIES = frozenset({"sessions", "memory"})
ALLOWED_DATABASE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})


class ProductionRuntimeService:
    @staticmethod
    def hardware_profile() -> HardwareProfile:
        return HardwareProfile(
            platform=platform.system() or "unknown",
            architecture=platform.machine() or "unknown",
            cpu_count=os.cpu_count() or 1,
            memory_bytes=_physical_memory(),
            accelerator=ProductionProviderStatus.NOT_CONFIGURED,
        )

    @staticmethod
    def update_status() -> UpdateStatus:
        """Updates stay explicit until a signed provider is configured."""
        return UpdateStatus(status=ProductionProviderStatus.NOT_CONFIGURED)


class DataBackupService:
    """Back up only Virgo session/memory databases and restore via directory swap."""

    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory.resolve()

    def create(self, archive_path: Path) -> BackupResult:
        archive = archive_path.resolve()
        if self.data_directory == archive or self.data_directory in archive.parents:
            raise ValidationError(
                "Backup archive must be outside the Virgo data directory",
                source_module=__name__,
            )
        files = self._files()
        manifest = BackupManifest(
            version=1,
            created_at=datetime.now(UTC),
            files=tuple(
                (
                    path.relative_to(self.data_directory).as_posix(),
                    _digest(path),
                    path.stat().st_size,
                )
                for path in files
            ),
        )
        try:
            archive.parent.mkdir(parents=True, exist_ok=True)
            temporary = archive.with_suffix(archive.suffix + ".tmp")
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED
            ) as output:
                output.writestr("manifest.json", _manifest_json(manifest))
                for path in files:
                    output.write(
                        path,
                        f"data/{path.relative_to(self.data_directory).as_posix()}",
                    )
            os.replace(temporary, archive)
        except (OSError, zipfile.BadZipFile) as error:
            raise StorageError(
                "Virgo data backup failed", source_module=__name__, cause=error
            ) from error
        return BackupResult(
            archive_path=str(archive),
            manifest=manifest,
            archive_sha256=_digest(archive),
        )

    def restore(self, archive_path: Path) -> BackupManifest:
        archive = archive_path.resolve()
        staging_parent = self.data_directory.parent
        staging = Path(tempfile.mkdtemp(prefix="virgo-restore-", dir=staging_parent))
        previous = self.data_directory.with_name(self.data_directory.name + ".previous")
        swapped = False
        try:
            manifest = self._extract_validated(archive, staging)
            if previous.exists():
                raise StorageError(
                    "A previous recovery directory already exists",
                    source_module=__name__,
                )
            if self.data_directory.exists():
                os.replace(self.data_directory, previous)
            os.replace(staging, self.data_directory)
            swapped = True
            if previous.exists():
                shutil.rmtree(previous)
            return manifest
        except Exception as error:
            if swapped and self.data_directory.exists():
                shutil.rmtree(self.data_directory)
            if previous.exists() and not self.data_directory.exists():
                os.replace(previous, self.data_directory)
            if isinstance(error, (StorageError, ValidationError)):
                raise
            raise StorageError(
                "Virgo data restore failed", source_module=__name__, cause=error
            ) from error
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def _files(self) -> tuple[Path, ...]:
        values: list[Path] = []
        total = 0
        for directory in ALLOWED_DATA_DIRECTORIES:
            root = self.data_directory / directory
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_symlink():
                    raise ValidationError(
                        "Backup does not follow symbolic links", source_module=__name__
                    )
                if (
                    not path.is_file()
                    or path.suffix.casefold() not in ALLOWED_DATABASE_SUFFIXES
                ):
                    continue
                total += path.stat().st_size
                values.append(path)
        if len(values) > MAX_BACKUP_FILES or total > MAX_BACKUP_BYTES:
            raise ValidationError(
                "Backup exceeds production limits", source_module=__name__
            )
        return tuple(values)

    def _extract_validated(self, archive: Path, staging: Path) -> BackupManifest:
        try:
            with zipfile.ZipFile(archive) as source:
                names = source.namelist()
                if (
                    "manifest.json" not in names
                    or len(names) != len(set(names))
                    or len(names) > MAX_BACKUP_FILES + 1
                    or sum(item.file_size for item in source.infolist())
                    > MAX_BACKUP_BYTES
                ):
                    raise ValidationError(
                        "Backup archive layout is invalid", source_module=__name__
                    )
                manifest = _parse_manifest(source.read("manifest.json"))
                expected = {
                    f"data/{name}": (digest, size)
                    for name, digest, size in manifest.files
                }
                if set(names) != {"manifest.json", *expected}:
                    raise ValidationError(
                        "Backup manifest does not match archive", source_module=__name__
                    )
                for name, (digest, size) in expected.items():
                    relative = PurePosixPath(name).relative_to("data")
                    if (
                        relative.parts[0] not in ALLOWED_DATA_DIRECTORIES
                        or ".." in relative.parts
                    ):
                        raise ValidationError(
                            "Backup path is outside allowed data",
                            source_module=__name__,
                        )
                    payload = source.read(name)
                    if (
                        len(payload) != size
                        or hashlib.sha256(payload).hexdigest() != digest
                    ):
                        raise ValidationError(
                            "Backup content validation failed", source_module=__name__
                        )
                    target = staging.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(payload)
                return manifest
        except (
            OSError,
            zipfile.BadZipFile,
            KeyError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise StorageError(
                "Backup archive could not be validated",
                source_module=__name__,
                cause=error,
            ) from error


def _manifest_json(manifest: BackupManifest) -> str:
    return json.dumps(
        {
            "version": manifest.version,
            "created_at": manifest.created_at.isoformat(),
            "files": manifest.files,
        },
        sort_keys=True,
    )


def _parse_manifest(payload: bytes) -> BackupManifest:
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        raise ValueError("invalid manifest")
    files = tuple((str(item[0]), str(item[1]), int(item[2])) for item in value["files"])
    return BackupManifest(
        version=int(value["version"]),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        files=files,
    )


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _physical_memory() -> int | None:
    if hasattr(os, "sysconf"):
        try:
            return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
        except (ValueError, OSError):
            pass
    return None
