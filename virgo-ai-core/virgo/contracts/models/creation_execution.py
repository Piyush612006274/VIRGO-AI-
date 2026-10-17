"""Typed contracts for controlled Stage 2 creation execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.creation import CreationAction, CreationOperation


class CreationTaskStatus(StrEnum):
    PREVIEW_READY = "preview_ready"
    APPROVED = "approved"
    APPLYING = "applying"
    VALIDATING = "validating"
    TESTING = "testing"
    AWAITING_ACCEPTANCE = "awaiting_acceptance"
    ACCEPTED = "accepted"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MutationStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    ACCEPTED = "accepted"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class ValidationStatus(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True, kw_only=True)
class GeneratedFileProposal:
    operation: CreationOperation
    proposed_content: str
    provider_name: str
    model_name: str
    validated: bool = False

    def __post_init__(self) -> None:
        if self.operation.action not in (CreationAction.CREATE, CreationAction.UPDATE):
            raise ValueError("generated proposals require a create or update operation")
        if not isinstance(self.proposed_content, str):
            raise ValueError("proposed_content must be text")
        for value, name in (
            (self.provider_name, "provider_name"),
            (self.model_name, "model_name"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True, kw_only=True)
class MutationJournalEntry:
    task_id: str
    operation: CreationOperation
    existed_before: bool
    before_sha256: str | None
    backup_reference: str | None
    after_sha256: str | None
    apply_status: MutationStatus
    validation_status: ValidationStatus = ValidationStatus.NOT_RUN
    rollback_status: MutationStatus = MutationStatus.PENDING

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id must not be empty")
        if self.existed_before != (self.before_sha256 is not None):
            raise ValueError("before hash must match prior existence")
        for digest in (self.before_sha256, self.after_sha256):
            if digest is not None and (
                len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ValueError("journal hashes must be lowercase SHA-256 digests")


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisteredTool:
    name: str
    description: str
    permission_level: str
    risk_level: str
    timeout_seconds: float
    cancellation_supported: bool
    validation: str
    audit_logged: bool
    rollback_supported: bool

    def __post_init__(self) -> None:
        for value in (
            self.name,
            self.description,
            self.permission_level,
            self.risk_level,
            self.validation,
        ):
            if not value.strip():
                raise ValueError("registered tool text fields must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("tool timeout must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationResult:
    target: str
    validator: str
    status: ValidationStatus
    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessRequest:
    tool_name: str
    arguments: tuple[str, ...]
    working_directory: str
    timeout_seconds: float = 30.0
    request_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if not self.tool_name.strip() or not self.working_directory.strip():
            raise ValueError("process tool and working directory are required")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise ValueError("process timeout must be between 0 and 300 seconds")
        if any(not argument or "\x00" in argument for argument in self.arguments):
            raise ValueError("process arguments must be non-empty and null-free")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessResult:
    request_id: str
    exit_code: int
    stdout: str
    stderr: str
    status: ValidationStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class CreationAuditReport:
    task_id: str
    request_summary: str
    approved_paths: tuple[str, ...]
    changed_paths: tuple[str, ...]
    tools_used: tuple[str, ...]
    provider_name: str | None
    model_name: str | None
    validation_results: tuple[ValidationResult, ...]
    test_results: tuple[ProcessResult, ...]
    task_status: CreationTaskStatus
    rollback_result: str | None
    errors: tuple[str, ...]
    normalized_intent: str | None = None
    capability: str | None = None
    provider_explanation: str | None = None
    plan_steps: tuple[str, ...] = ()
    operations_performed: tuple[str, ...] = ()
    permission_decisions: tuple[str, ...] = ()
    acceptance: str | None = None
    timings_seconds: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.request_summary.strip():
            raise ValueError("audit task and request summary are required")
