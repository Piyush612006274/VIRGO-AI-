"""Immutable contracts for the Stage 2 creation workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from virgo.contracts.models.correlation import new_correlation_id


class CreationAction(StrEnum):
    """Operations understood by the preview-first creation core."""

    INSPECT = "inspect"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    DEPLOY = "deploy"
    PUBLISH = "publish"


class ToolRiskLevel(StrEnum):
    """Architecture-defined tool risk vocabulary."""

    READ_ONLY = "read_only"
    LOW_RISK_WRITE = "low_risk_write"
    REVERSIBLE_WRITE = "reversible_write"
    HIGH_IMPACT = "high_impact"
    PROHIBITED = "prohibited"


class PermissionDecision(StrEnum):
    """Explicit decisions available to the application permission boundary."""

    PENDING = "pending"
    ALLOW_ONCE = "allow_once"
    ALLOW_FOR_TASK = "allow_for_task"
    DENY = "deny"


@dataclass(frozen=True, slots=True, kw_only=True)
class CreationRequest:
    """Normalized user intent for one bounded creation task."""

    intent: str
    workspace_root: str
    requested_paths: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    request_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        _require_text(self.intent, "intent")
        _require_text(self.workspace_root, "workspace_root")
        _require_unique_text(self.requested_paths, "requested_paths")
        _require_unique_text(self.requirements, "requirements")
        _require_unique_text(self.constraints, "constraints")


@dataclass(frozen=True, slots=True, kw_only=True)
class MissingRequirement:
    """One material question that must be answered before planning."""

    key: str
    question: str

    def __post_init__(self) -> None:
        _require_text(self.key, "key")
        _require_text(self.question, "question")


@dataclass(frozen=True, slots=True, kw_only=True)
class CreationOperation:
    """One proposed, not-yet-executed creation operation."""

    action: CreationAction
    target: str
    summary: str
    risk_level: ToolRiskLevel
    tool_name: str
    reversible: bool
    requires_permission: bool
    operation_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if not isinstance(self.action, CreationAction):
            raise ValueError("action must be a CreationAction")
        if not isinstance(self.risk_level, ToolRiskLevel):
            raise ValueError("risk_level must be a ToolRiskLevel")
        _require_text(self.target, "target")
        _require_text(self.summary, "summary")
        _require_text(self.tool_name, "tool_name")


@dataclass(frozen=True, slots=True, kw_only=True)
class CreationPlan:
    """Deterministic, bounded plan awaiting permission before mutation."""

    request_id: str
    operations: tuple[CreationOperation, ...]
    validation_steps: tuple[str, ...]
    test_steps: tuple[str, ...]
    plan_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        _require_text(self.request_id, "request_id")
        if not self.operations:
            raise ValueError("operations must not be empty")
        if not all(isinstance(item, CreationOperation) for item in self.operations):
            raise ValueError("operations must contain CreationOperation values")
        _require_unique_text(self.validation_steps, "validation_steps")
        _require_unique_text(self.test_steps, "test_steps")


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionRequest:
    """User-facing permission facts for one proposed operation."""

    task_id: str
    operation: CreationOperation
    reason: str
    expected_result: str
    rollback_available: bool
    permission_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        _require_text(self.task_id, "task_id")
        if not isinstance(self.operation, CreationOperation):
            raise ValueError("operation must be a CreationOperation")
        _require_text(self.reason, "reason")
        _require_text(self.expected_result, "expected_result")
        if self.rollback_available and not self.operation.reversible:
            raise ValueError("rollback cannot be offered for an irreversible operation")


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionRecord:
    """Immutable result of one explicit permission decision."""

    request: PermissionRequest
    decision: PermissionDecision

    def __post_init__(self) -> None:
        if not isinstance(self.request, PermissionRequest):
            raise ValueError("request must be a PermissionRequest")
        if not isinstance(self.decision, PermissionDecision):
            raise ValueError("decision must be a PermissionDecision")
        if self.decision is PermissionDecision.PENDING:
            raise ValueError("a permission record cannot remain pending")


@dataclass(frozen=True, slots=True, kw_only=True)
class RollbackMetadata:
    """Metadata required to prove or restore a reversible future write."""

    target: str
    existed_before: bool
    previous_sha256: str | None
    backup_reference: str | None

    def __post_init__(self) -> None:
        _require_text(self.target, "target")
        if self.existed_before and self.previous_sha256 is None:
            raise ValueError("existing targets require a previous_sha256")
        if not self.existed_before and self.previous_sha256 is not None:
            raise ValueError("new targets cannot have a previous_sha256")
        if self.previous_sha256 is not None and (
            len(self.previous_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.previous_sha256
            )
        ):
            raise ValueError("previous_sha256 must be a lowercase SHA-256 digest")
        if self.backup_reference is not None:
            _require_text(self.backup_reference, "backup_reference")


@dataclass(frozen=True, slots=True, kw_only=True)
class FileInspection:
    """Safe metadata returned by read-only project inspection."""

    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _require_text(self.relative_path, "relative_path")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a SHA-256 digest")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectInspection:
    """Bounded read-only inventory of a creation workspace."""

    workspace_root: str
    files: tuple[FileInspection, ...]
    total_bytes: int

    def __post_init__(self) -> None:
        _require_text(self.workspace_root, "workspace_root")
        if self.total_bytes < 0 or self.total_bytes != sum(
            item.size_bytes for item in self.files
        ):
            raise ValueError("total_bytes must equal inspected file sizes")


@dataclass(frozen=True, slots=True, kw_only=True)
class ChangePreview:
    """A deterministic text diff that has not been applied."""

    target: str
    unified_diff: str
    rollback: RollbackMetadata

    def __post_init__(self) -> None:
        _require_text(self.target, "target")
        _require_text(self.unified_diff, "unified_diff")
        if self.rollback.target != self.target:
            raise ValueError("preview and rollback targets must match")


@dataclass(frozen=True, slots=True, kw_only=True)
class CreationReview:
    """Creation Core output: clarify, or inspect and propose a safe plan."""

    request: CreationRequest
    missing_requirements: tuple[MissingRequirement, ...]
    inspection: ProjectInspection | None
    plan: CreationPlan | None

    def __post_init__(self) -> None:
        if self.missing_requirements and self.plan is not None:
            raise ValueError("a plan cannot exist while requirements are missing")
        if not self.missing_requirements and self.plan is None:
            raise ValueError("complete requirements must produce a plan")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _require_unique_text(values: tuple[str, ...], name: str) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise ValueError(f"{name} must contain non-empty text")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates")
