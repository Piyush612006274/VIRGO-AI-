"""Immutable contracts for authorized read-only security analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.creation import ToolRiskLevel


class SecurityTargetType(StrEnum):
    LOCAL_PROJECT = "local_project"
    LOCAL_FILE = "local_file"
    LOCAL_DIRECTORY = "local_directory"
    LOCAL_CONFIGURATION = "local_configuration"
    LOCAL_SYSTEM = "local_system"
    LOCAL_ENDPOINT = "local_endpoint"
    LAB = "lab"


class DefensiveObjective(StrEnum):
    SYSTEM_DIAGNOSTICS = "system_diagnostics"
    LOG_ANALYSIS = "log_analysis"
    NETWORK_VISIBILITY = "network_visibility"
    VULNERABILITY_ASSESSMENT = "vulnerability_assessment"
    CONFIGURATION_AUDIT = "configuration_audit"
    SECURE_CODE_REVIEW = "secure_code_review"
    MALWARE_INDICATOR_ANALYSIS = "malware_indicator_analysis"
    DEPENDENCY_ASSESSMENT = "dependency_assessment"
    WINDOWS_ADMINISTRATION_REVIEW = "windows_administration_review"
    LINUX_ADMINISTRATION_REVIEW = "linux_administration_review"
    LAB_SECURITY_ASSESSMENT = "lab_security_assessment"


class SecurityWorkflowStage(StrEnum):
    DEFINE_SCOPE = "define_scope"
    SELECT_OBJECTIVE = "select_objective"
    BUILD_PLAN = "build_plan"
    RISK_REVIEW = "risk_review"
    ASK_PERMISSION = "ask_permission"
    EXECUTE_SAFELY = "execute_safely"
    COLLECT_EVIDENCE = "collect_evidence"
    ANALYZE = "analyze"
    RECOMMEND_FIXES = "recommend_fixes"
    VERIFY_FIXES = "verify_fixes"
    PRODUCE_REPORT = "produce_report"


class SecurityVerificationStatus(StrEnum):
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNCHANGED = "unchanged"
    NEW_FINDING = "new_finding"
    VERIFICATION_FAILED = "verification_failed"


class SecurityOperation(StrEnum):
    READ_ONLY_ANALYSIS = "read_only_analysis"


class SecuritySeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityCategory(StrEnum):
    SECRET_EXPOSURE = "secret_exposure"
    INSECURE_CONFIGURATION = "insecure_configuration"
    DANGEROUS_CODE = "dangerous_code"
    PROJECT_METADATA = "project_metadata"
    DEPENDENCY_CONFIGURATION = "dependency_configuration"
    LOG_SECURITY = "log_security"
    MALWARE_INDICATOR = "malware_indicator"


class SecurityProviderStatus(StrEnum):
    AVAILABLE = "available"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityTarget:
    target_type: SecurityTargetType
    root: str

    def __post_init__(self) -> None:
        if not isinstance(self.target_type, SecurityTargetType):
            raise ValueError("target_type must be a SecurityTargetType")
        _text(self.root, "root")


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityScope:
    target: SecurityTarget
    operation: SecurityOperation = SecurityOperation.READ_ONLY_ANALYSIS
    ownership_confirmed: bool = False
    allow_file_reads: bool = True
    allow_metadata: bool = True
    allow_network: bool = False
    network_targets: tuple[str, ...] = ()
    network_ports: tuple[int, ...] = ()
    network_timeout_seconds: float = 1.0
    max_files: int = 1_000
    max_file_bytes: int = 1_048_576
    max_findings: int = 250
    max_depth: int = 20

    def __post_init__(self) -> None:
        if not isinstance(self.target, SecurityTarget):
            raise ValueError("target must be a SecurityTarget")
        if self.operation is not SecurityOperation.READ_ONLY_ANALYSIS:
            raise ValueError("Step 1 supports read-only analysis only")
        if self.allow_network:
            if not self.network_targets or not self.network_ports:
                raise ValueError(
                    "network authorization requires exact targets and ports"
                )
            if len(self.network_targets) > 2 or len(self.network_ports) > 8:
                raise ValueError("network target/port limits exceeded")
            if any(target != "127.0.0.1" for target in self.network_targets):
                raise ValueError("Stage 3 active visibility is localhost-only")
            if any(port < 1 or port > 65535 for port in self.network_ports):
                raise ValueError("network ports must be valid")
        elif self.network_targets or self.network_ports:
            raise ValueError("network targets require explicit network authorization")
        if not 0 < self.network_timeout_seconds <= 5:
            raise ValueError("network timeout must be between 0 and 5 seconds")
        if not self.ownership_confirmed:
            raise ValueError("target ownership must be explicitly confirmed")
        if not self.allow_file_reads or not self.allow_metadata:
            raise ValueError("local analysis requires authorized reads and metadata")
        for name in ("max_files", "max_file_bytes", "max_findings", "max_depth"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityPermissionRequirement:
    operation: SecurityOperation = SecurityOperation.READ_ONLY_ANALYSIS
    risk_level: ToolRiskLevel = ToolRiskLevel.READ_ONLY
    explicit_scope_required: bool = True
    ownership_confirmation_required: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityAnalysisRequest:
    scope: SecurityScope
    objective: DefensiveObjective = DefensiveObjective.SECURE_CODE_REVIEW
    requested_checks: tuple[str, ...] = ()
    selected_log_paths: tuple[str, ...] = ()
    request_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if (
            self.scope.allow_network
            and self.objective is not DefensiveObjective.NETWORK_VISIBILITY
        ):
            raise ValueError("network scope requires the network visibility objective")
        if len(self.selected_log_paths) != len(set(self.selected_log_paths)):
            raise ValueError("selected_log_paths must not contain duplicates")
        for path in self.selected_log_paths:
            _text(path, "selected_log_path")


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityAnalysisPlan:
    request_id: str
    check_ids: tuple[str, ...]
    permission: SecurityPermissionRequirement
    objective: DefensiveObjective = DefensiveObjective.SECURE_CODE_REVIEW
    stages: tuple[SecurityWorkflowStage, ...] = tuple(SecurityWorkflowStage)
    analysis_id: str = field(default_factory=new_correlation_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityEvidence:
    summary: str
    source_check_id: str
    line_number: int | None = None
    configuration_key: str | None = None

    def __post_init__(self) -> None:
        _text(self.summary, "summary")
        _text(self.source_check_id, "source_check_id")
        if self.line_number is not None and self.line_number < 1:
            raise ValueError("line_number must be positive")
        if self.configuration_key is not None:
            _text(self.configuration_key, "configuration_key")

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "source_check_id": self.source_check_id,
            "line_number": self.line_number,
            "configuration_key": self.configuration_key,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityRecommendation:
    summary: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityFinding:
    finding_id: str
    category: SecurityCategory
    title: str
    description: str
    severity: SecuritySeverity
    confidence: float
    affected_path: str
    evidence: tuple[SecurityEvidence, ...]
    recommendation: SecurityRecommendation
    source_check_id: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        for name in (
            "finding_id",
            "title",
            "description",
            "affected_path",
            "source_check_id",
        ):
            _text(getattr(self, name), name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "affected_path": self.affected_path,
            "evidence": [item.to_dict() for item in self.evidence],
            "recommendation": self.recommendation.summary,
            "source_check_id": self.source_check_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityProviderHealth:
    provider: str = "deterministic-local"
    available: bool = True
    network_used: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityIntelligenceStatus:
    provider: str
    status: SecurityProviderStatus
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityAnalysisResult:
    analysis_id: str
    target: SecurityTarget
    scope: SecurityScope
    checks_executed: tuple[str, ...]
    checks_skipped: tuple[str, ...]
    findings: tuple[SecurityFinding, ...]
    errors: tuple[str, ...]
    intelligence: tuple[SecurityIntelligenceStatus, ...] = ()
    objective: DefensiveObjective = DefensiveObjective.SECURE_CODE_REVIEW
    workflow_stages: tuple[SecurityWorkflowStage, ...] = tuple(SecurityWorkflowStage)
    cancelled: bool = False

    def to_dict(self) -> dict[str, Any]:
        counts = {severity.value: 0 for severity in SecuritySeverity}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        categories = {category.value: 0 for category in SecurityCategory}
        for finding in self.findings:
            categories[finding.category.value] += 1
        return {
            "analysis_id": self.analysis_id,
            "objective": self.objective.value,
            "workflow_stages": [stage.value for stage in self.workflow_stages],
            "target": {"type": self.target.target_type.value, "root": self.target.root},
            "scope": {
                "operation": self.scope.operation.value,
                "network_allowed": self.scope.allow_network,
                "network_targets": list(self.scope.network_targets),
                "network_ports": list(self.scope.network_ports),
                "file_reads_allowed": self.scope.allow_file_reads,
                "metadata_allowed": self.scope.allow_metadata,
                "limits": {
                    "max_files": self.scope.max_files,
                    "max_file_bytes": self.scope.max_file_bytes,
                    "max_findings": self.scope.max_findings,
                    "max_depth": self.scope.max_depth,
                },
            },
            "checks_executed": list(self.checks_executed),
            "checks_skipped": list(self.checks_skipped),
            "findings_by_severity": counts,
            "findings_by_category": categories,
            "high_confidence_findings": sum(
                finding.confidence >= 0.8 for finding in self.findings
            ),
            "findings": [finding.to_dict() for finding in self.findings],
            "errors": list(self.errors),
            "intelligence": [item.to_dict() for item in self.intelligence],
            "cancelled": self.cancelled,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemSecurityDiagnostics:
    platform_family: str
    architecture: str
    python_implementation: str
    safe_mode: bool = True
    mutated_system: bool = False
    unsupported_checks: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "platform_family": self.platform_family,
            "architecture": self.architecture,
            "python_implementation": self.python_implementation,
            "safe_mode": self.safe_mode,
            "mutated_system": self.mutated_system,
            "unsupported_checks": list(self.unsupported_checks),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkVisibilityResult:
    target: str
    port: int
    reachable: bool
    timed_out: bool
    cancelled: bool
    network_authorized: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SecurityToolStatus:
    tool_id: str
    status: SecurityProviderStatus
    purpose: str
    safe_mode: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class RemediationProposal:
    finding_id: str
    target: str
    proposed_change: str
    reason: str
    expected_improvement: str
    affected_paths: tuple[str, ...]
    risk_level: ToolRiskLevel = ToolRiskLevel.REVERSIBLE_WRITE
    reversible: bool = True
    validation_strategy: str = "Re-analyze the exact authorized workspace"
    rollback_available: bool = True


@dataclass(frozen=True, slots=True, kw_only=True)
class RemediationVerification:
    finding_id: str
    status: SecurityVerificationStatus
    before_count: int
    after_count: int


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
