"""Immutable contracts for one controlled self-improvement cycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256

from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.creation import ChangePreview
from virgo.contracts.models.creation_execution import ValidationStatus
from virgo.contracts.models.learning_experience import (
    EvaluationComparison,
    EvaluationRecord,
    ImprovementProposal,
)


class SelfImprovementRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SelfImprovementDecision(StrEnum):
    ACCEPT = "accept"
    ROLLBACK = "rollback"


class SelfImprovementStatus(StrEnum):
    APPROVAL_REQUIRED = "approval_required"
    DENIED = "denied"
    PROTECTED_TARGET = "protected_target"
    PREVIEW_READY = "preview_ready"
    APPLIED = "applied"
    TEST_FAILED = "test_failed"
    SECURITY_FAILED = "security_failed"
    REGRESSED = "regressed"
    AWAITING_DECISION = "awaiting_decision"
    ACCEPTED = "accepted"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementScope:
    repository_root: str
    target_files: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.repository_root.strip() or not self.target_files:
            raise ValueError("self-improvement scope must be exact and non-empty")
        if len(self.target_files) != len(set(self.target_files)):
            raise ValueError("self-improvement targets must be unique")
        if any(not item.strip() or "*" in item for item in self.target_files):
            raise ValueError("wildcard or empty self-improvement targets are forbidden")


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementValidationPlan:
    focused_test_tools: tuple[str, ...]
    security_checks: tuple[str, ...]
    evaluations: tuple[EvaluationRecord, ...]
    rollback_steps: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.focused_test_tools or not self.security_checks:
            raise ValueError("tests and security checks are mandatory before mutation")
        if not self.evaluations or not self.rollback_steps:
            raise ValueError("evaluation and rollback plans are mandatory")


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementRequest:
    proposal: ImprovementProposal
    scope: SelfImprovementScope
    baseline_head: str
    change_concept: str
    expected_benefit: str
    validation_plan: SelfImprovementValidationPlan
    correlation_id: str = field(default_factory=new_correlation_id)
    task_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if not self.baseline_head.strip() or not self.change_concept.strip():
            raise ValueError("baseline and exact change concept are required")
        if not self.expected_benefit.strip() or not self.proposal.permission_required:
            raise ValueError("benefit and explicit permission requirement are required")


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementRisk:
    level: SelfImprovementRiskLevel
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementChange:
    target: str
    before_sha256: str | None
    proposed_content: str
    reason: str

    @property
    def after_sha256(self) -> str:
        return sha256(self.proposed_content.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementChangeSet:
    changes: tuple[SelfImprovementChange, ...]
    previews: tuple[ChangePreview, ...]

    def __post_init__(self) -> None:
        if not self.changes or len(self.changes) != len(self.previews):
            raise ValueError("change set and previews must be complete")


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementPermissionRequest:
    task_id: str
    baseline_head: str
    target_files: tuple[str, ...]
    scope_fingerprint: str
    problem: str
    evidence_ids: tuple[str, ...]
    change_concept: str
    expected_benefit: str
    risk: SelfImprovementRisk
    validation_plan: SelfImprovementValidationPlan


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementApproval:
    task_id: str
    baseline_head: str
    target_files: tuple[str, ...]
    scope_fingerprint: str
    approved: bool
    approved_by: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementPlan:
    request: SelfImprovementRequest
    risk: SelfImprovementRisk
    change_set: SelfImprovementChangeSet
    permission: SelfImprovementPermissionRequest
    branch_name: str
    original_hashes: tuple[tuple[str, str | None], ...]
    baseline_evaluation: EvaluationComparison
    baseline_test_statuses: tuple[ValidationStatus, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementEvaluationResult:
    comparison: EvaluationComparison
    test_statuses: tuple[ValidationStatus, ...]
    security_findings_before: int
    security_findings_after: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfImprovementResult:
    task_id: str
    status: SelfImprovementStatus
    branch_name: str | None
    changed_files: tuple[str, ...]
    before_hashes: tuple[tuple[str, str | None], ...]
    after_hashes: tuple[tuple[str, str | None], ...]
    evaluation: SelfImprovementEvaluationResult | None
    rollback_verified: bool
    commit_hash: str | None = None
    message: str = ""
