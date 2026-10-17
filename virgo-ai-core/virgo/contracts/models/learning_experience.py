"""Typed contracts for bounded experience learning and self-inspection."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.learning import KnowledgeScope, PrivacyClassification


class TaskOutcomeStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"
    USER_REJECTED = "user_rejected"
    USER_CORRECTED = "user_corrected"
    VALIDATION_FAILED = "validation_failed"
    SECURITY_REJECTED = "security_rejected"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class FailureCategory(StrEnum):
    TRANSIENT = "transient"
    ENVIRONMENTAL = "environmental"
    USER_ERROR = "user_error"
    SYSTEM_DEFECT = "system_defect"
    KNOWLEDGE_GAP = "knowledge_gap"
    PROCESS_DEFECT = "process_defect"
    UNKNOWN = "unknown"


class CauseStatus(StrEnum):
    OBSERVED = "observed"
    SUPPORTED = "supported"
    UNVERIFIED = "unverified"
    REJECTED = "rejected"


class ValidationState(StrEnum):
    CANDIDATE = "candidate"
    VALIDATING = "validating"
    VALIDATED = "validated"
    ACCEPTED = "accepted"
    ACTIVE = "active"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


class SelfInspectionCategory(StrEnum):
    STATIC_ANALYSIS = "static_analysis"
    DEPENDENCY_REVIEW = "dependency_review"
    ARCHITECTURE_COMPLIANCE = "architecture_compliance"
    PERFORMANCE_REVIEW = "performance_review"
    SECURITY_REVIEW = "security_review"
    TEST_COVERAGE_REVIEW = "test_coverage_review"
    FAILURE_ANALYSIS = "failure_analysis"


class FindingSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvaluationType(StrEnum):
    EXACT_MATCH = "exact_match"
    CONTAINS_REQUIRED_FACT = "contains_required_fact"
    DOES_NOT_CONTAIN_FORBIDDEN_FACT = "does_not_contain_forbidden_fact"
    ROUTING_RESULT = "routing_result"
    VALIDATION_RESULT = "validation_result"
    SECURITY_PROPERTY = "security_property"
    PERMISSION_PROPERTY = "permission_property"
    WORKFLOW_OUTCOME = "workflow_outcome"


class ComparisonResult(StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskOutcome:
    task_id: str
    capability: str
    objective: str
    outcome: TaskOutcomeStatus
    validation_summary: str
    scope: KnowledgeScope
    scope_key: str
    failure_category: FailureCategory | None = None
    rollback_performed: bool = False
    user_feedback: str | None = None
    correlation_id: str = field(default_factory=new_correlation_id)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for value in (self.task_id, self.capability, self.objective, self.scope_key):
            _text(value)
        if _contains_secret(self.validation_summary) or (
            self.user_feedback and _contains_secret(self.user_feedback)
        ):
            raise ValueError("task outcome metadata must not contain secrets")


@dataclass(frozen=True, slots=True, kw_only=True)
class FailureCause:
    statement: str
    evidence_refs: tuple[str, ...]
    confidence: float
    status: CauseStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class FailureAnalysis:
    outcome_id: str
    category: FailureCategory
    facts: tuple[str, ...]
    inferences: tuple[str, ...]
    unknowns: tuple[str, ...]
    causes: tuple[FailureCause, ...]
    recommended_verification: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ReusableLesson:
    statement: str
    outcome_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    scope: KnowledgeScope
    scope_key: str
    confidence: float
    applicability: tuple[str, ...]
    limitations: tuple[str, ...]
    validation_status: ValidationState
    provenance: str
    version: int = 1
    lesson_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        _bounded_confidence(self.confidence)
        if not self.outcome_ids or not self.evidence_refs or self.version < 1:
            raise ValueError(
                "lesson requires outcomes, evidence, and a positive version"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredSkill:
    name: str
    objective: str
    applicability: tuple[str, ...]
    prerequisites: tuple[str, ...]
    guidance: tuple[str, ...]
    tool_references: tuple[str, ...]
    permission_requirements: tuple[str, ...]
    validation: tuple[str, ...]
    failure_conditions: tuple[str, ...]
    rollback_guidance: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    status: ValidationState = ValidationState.CANDIDATE
    version: int = 1
    skill_id: str = field(default_factory=new_correlation_id)
    executable: bool = False

    def __post_init__(self) -> None:
        if self.executable:
            raise ValueError("structured skills cannot contain executable authority")
        if not self.guidance or not self.permission_requirements or not self.validation:
            raise ValueError(
                "skill requires bounded guidance, permissions, and validation"
            )
        joined = " ".join((*self.guidance, *self.tool_references)).casefold()
        if any(
            item in joined
            for item in ("powershell", "cmd.exe", "bash -c", "permission override")
        ):
            raise ValueError(
                "skill contains prohibited executable or permission guidance"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationRecord:
    name: str
    evaluation_type: EvaluationType
    input_reference: str
    expected: str
    scope: KnowledgeScope
    scope_key: str
    provenance: str
    privacy: PrivacyClassification
    accepted: bool
    version: int = 1
    evaluation_id: str = field(default_factory=new_correlation_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationEvidence:
    evaluation_id: str
    baseline_passed: bool | None
    candidate_passed: bool | None
    detail: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EvaluationComparison:
    result: ComparisonResult
    evidence: tuple[EvaluationEvidence, ...]
    passed: int
    failed: int
    regression_detected: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfInspectionScope:
    repository_root: str
    categories: tuple[SelfInspectionCategory, ...]
    max_files: int = 300
    max_file_bytes: int = 200_000
    max_findings: int = 100
    max_duration_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.categories or not 1 <= self.max_files <= 1_000:
            raise ValueError("inspection scope categories/files are invalid")
        if (
            not 1 <= self.max_file_bytes <= 1_000_000
            or not 1 <= self.max_findings <= 200
        ):
            raise ValueError("inspection size/finding limits are invalid")
        if not 0 < self.max_duration_seconds <= 120:
            raise ValueError("inspection duration must be within 120 seconds")


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfInspectionRequest:
    objective: str
    scope: SelfInspectionScope
    authorization_confirmed: bool
    request_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        _text(self.objective)
        if not self.authorization_confirmed:
            raise ValueError("self-inspection requires explicit authorization")


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfInspectionPlan:
    request_id: str
    categories: tuple[SelfInspectionCategory, ...]
    read_only: bool = True
    mutation_allowed: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfInspectionEvidence:
    category: SelfInspectionCategory
    path: str
    summary: str
    content_hash: str | None = None
    evidence_id: str = field(default_factory=new_correlation_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfInspectionFinding:
    category: SelfInspectionCategory
    title: str
    description: str
    severity: FindingSeverity
    confidence: float
    evidence_ids: tuple[str, ...]
    finding_id: str = field(default_factory=new_correlation_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class ImprovementOpportunity:
    problem: str
    evidence_ids: tuple[str, ...]
    affected_subsystem: str
    severity: FindingSeverity
    confidence: float
    suggested_objective: str
    expected_benefit: str
    risk_category: str
    opportunity_id: str = field(default_factory=new_correlation_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class ImprovementProposal:
    opportunity_id: str
    problem: str
    evidence_ids: tuple[str, ...]
    proposed_change_concept: str
    target_subsystem: str
    expected_benefit: str
    risks: tuple[str, ...]
    estimated_scope: tuple[str, ...]
    validation_plan: tuple[str, ...]
    security_checks: tuple[str, ...]
    rollback_expectations: tuple[str, ...]
    evaluation_plan: tuple[str, ...]
    permission_required: bool = True
    mutation_performed: bool = False
    proposal_id: str = field(default_factory=new_correlation_id)
    version: int = 1


@dataclass(frozen=True, slots=True, kw_only=True)
class SelfInspectionResult:
    plan: SelfInspectionPlan
    evidence: tuple[SelfInspectionEvidence, ...]
    findings: tuple[SelfInspectionFinding, ...]
    opportunities: tuple[ImprovementOpportunity, ...]
    proposals: tuple[ImprovementProposal, ...]
    duration_seconds: float
    files_inspected: int
    coverage_status: str = "COVERAGE_PERCENTAGE_NOT_AVAILABLE"
    cancelled: bool = False
    mutation_performed: bool = False


def _text(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("required text must not be empty")


def _bounded_confidence(value: float) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0 <= value <= 1
    ):
        raise ValueError("confidence must be between zero and one")


def _contains_secret(value: str) -> bool:
    lowered = value.casefold()
    return any(
        item in lowered
        for item in ("api_key=", "password=", "token=", "authorization:")
    )
