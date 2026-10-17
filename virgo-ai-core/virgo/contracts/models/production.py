"""Immutable production lifecycle, backup, update, and automation contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.personal_runtime import PersonalCapability


class ProductionProviderStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True, kw_only=True)
class HardwareProfile:
    platform: str
    architecture: str
    cpu_count: int
    memory_bytes: int | None
    accelerator: ProductionProviderStatus

    def __post_init__(self) -> None:
        if not self.platform.strip() or not self.architecture.strip():
            raise ValueError("hardware platform metadata must not be empty")
        if self.cpu_count < 1:
            raise ValueError("cpu_count must be positive")
        if self.memory_bytes is not None and self.memory_bytes < 1:
            raise ValueError("memory_bytes must be positive when available")


@dataclass(frozen=True, slots=True, kw_only=True)
class BackupManifest:
    version: int
    created_at: datetime
    files: tuple[tuple[str, str, int], ...]

    def __post_init__(self) -> None:
        if self.version != 1 or self.created_at.utcoffset() != UTC.utcoffset(
            self.created_at
        ):
            raise ValueError("backup manifest version or timestamp is invalid")
        if any(len(digest) != 64 or size < 0 for _, digest, size in self.files):
            raise ValueError("backup file metadata is invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class BackupResult:
    archive_path: str
    manifest: BackupManifest
    archive_sha256: str


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateStatus:
    status: ProductionProviderStatus
    provider: str = "not_configured"
    automatic_install: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class AutomationDefinition:
    owner: str
    objective: str
    scope: str
    trigger: str
    capability_allowlist: tuple[PersonalCapability, ...]
    stop_conditions: tuple[str, ...]
    permission_required: bool = True
    enabled: bool = False
    automation_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.owner, self.objective, self.scope, self.trigger)
        ):
            raise ValueError("automation identity and scope must not be empty")
        if not self.capability_allowlist or not self.stop_conditions:
            raise ValueError("automation requires allowlist and stop conditions")
        if self.enabled:
            raise ValueError("automation cannot self-enable")


@dataclass(frozen=True, slots=True, kw_only=True)
class FailureRecord:
    subsystem: str
    category: str
    outcome: str
    recovered: bool
    task_id: str | None = None
    provider_or_tool: str | None = None
    failure_id: str = field(default_factory=new_correlation_id)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if any(
            not value.strip() for value in (self.subsystem, self.category, self.outcome)
        ):
            raise ValueError("failure metadata must not be empty")
