"""Final Stage 3 safe diagnostics, visibility, workflow, and remediation."""

from __future__ import annotations

import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from virgo.application import ApplicationStateStore
from virgo.application.permissions import PermissionGate
from virgo.application.tasks import ControlledCreationWorkflow, CreationCoordinator
from virgo.capabilities.security.engine import SecurityAnalysisCoordinator
from virgo.contracts.errors import PermissionDeniedError, ValidationError
from virgo.contracts.models import (
    CreationAction,
    CreationOperation,
    CreationRequest,
    DefensiveObjective,
    GeneratedFileProposal,
    NetworkVisibilityResult,
    PermissionRequest,
    RemediationProposal,
    RemediationVerification,
    SecurityAnalysisRequest,
    SecurityAnalysisResult,
    SecurityProviderStatus,
    SecurityScope,
    SecurityTargetType,
    SecurityToolStatus,
    SecurityVerificationStatus,
    SystemSecurityDiagnostics,
    ToolRiskLevel,
    new_correlation_id,
)
from virgo.infrastructure.events import EventDispatcher
from virgo.infrastructure.security_network import localhost_tcp_reachable
from virgo.intelligence.planner import CreationPlanner


@dataclass(frozen=True, slots=True)
class NetworkVisibilityPlan:
    scope: SecurityScope
    operation: CreationOperation
    permission: PermissionRequest


class SystemSecurityDiagnosticService:
    """Return bounded platform metadata without commands, elevation, or mutation."""

    def inspect(self, scope: SecurityScope) -> SystemSecurityDiagnostics:
        if scope.target.target_type is not SecurityTargetType.LOCAL_SYSTEM:
            raise ValidationError(
                "System diagnostics require a local-system target",
                source_module=__name__,
            )
        if scope.allow_network:
            raise ValidationError(
                "System diagnostics do not require network access",
                source_module=__name__,
            )
        family = platform.system() or "unknown"
        unsupported = (
            "firewall-profile-status:not_configured",
            "service-status:not_configured",
            "privileged-administration:recommendation_only",
        )
        return SystemSecurityDiagnostics(
            platform_family=family,
            architecture=platform.machine() or "unknown",
            python_implementation=platform.python_implementation(),
            unsupported_checks=unsupported,
        )


class OptionalSecurityToolRegistry:
    """Health-only declarations; discovery never starts a tool or scan."""

    def statuses(self) -> tuple[SecurityToolStatus, ...]:
        return (
            self._status("nmap", "Bounded defensive network metadata"),
            self._status("tshark", "Explicit packet-capture analysis"),
            SecurityToolStatus(
                tool_id="credential-audit",
                status=SecurityProviderStatus.NOT_CONFIGURED,
                purpose="Future explicitly approved high-risk credential audit",
            ),
        )

    @staticmethod
    def _status(tool: str, purpose: str) -> SecurityToolStatus:
        return SecurityToolStatus(
            tool_id=tool,
            status=(
                SecurityProviderStatus.AVAILABLE
                if shutil.which(tool) is not None
                else SecurityProviderStatus.NOT_CONFIGURED
            ),
            purpose=purpose,
        )


class AuthorizedAssessmentWorkflow:
    """Safe-mode orchestration for project and explicitly declared lab assessments."""

    def __init__(self, analyzer: SecurityAnalysisCoordinator) -> None:
        self.analyzer = analyzer

    def assess(
        self, request: SecurityAnalysisRequest, cancellation: Event | None = None
    ) -> SecurityAnalysisResult:
        if request.objective is DefensiveObjective.LAB_SECURITY_ASSESSMENT:
            if request.scope.target.target_type is not SecurityTargetType.LAB:
                raise ValidationError(
                    "Lab assessment requires an explicit LAB target",
                    source_module=__name__,
                )
        elif request.scope.target.target_type is SecurityTargetType.LAB:
            raise ValidationError(
                "LAB targets require the lab assessment objective",
                source_module=__name__,
            )
        if request.scope.allow_network:
            raise ValidationError(
                "Active network visibility uses its dedicated permission workflow",
                source_module=__name__,
            )
        return self.analyzer.analyze(request, cancellation)


class LocalhostNetworkVisibilityService:
    """One explicitly approved TCP reachability check; never scans ranges."""

    def plan(
        self, scope: SecurityScope, coordinator: CreationCoordinator
    ) -> NetworkVisibilityPlan:
        if (
            not scope.allow_network
            or scope.target.target_type is not SecurityTargetType.LOCAL_ENDPOINT
        ):
            raise PermissionDeniedError(
                "Network visibility is not explicitly authorized",
                source_module=__name__,
            )
        if len(scope.network_targets) != 1 or len(scope.network_ports) != 1:
            raise ValidationError(
                "Active visibility requires exactly one target and port",
                source_module=__name__,
            )
        target = f"{scope.network_targets[0]}:{scope.network_ports[0]}"
        operation = CreationOperation(
            action=CreationAction.EXECUTE,
            target=target,
            summary="Check one approved localhost TCP endpoint",
            risk_level=ToolRiskLevel.HIGH_IMPACT,
            tool_name="security_localhost_reachability",
            reversible=False,
            requires_permission=True,
        )
        task_id = new_correlation_id()
        permission = coordinator.request_permission(
            task_id,
            operation,
            reason="Verify defensive reachability of the exact authorized localhost endpoint",
            expected_result="Reachability metadata only; no payload or authentication",
        )
        return NetworkVisibilityPlan(scope, operation, permission)

    def check(
        self,
        plan: NetworkVisibilityPlan,
        gate: PermissionGate,
        cancellation: Event | None = None,
    ) -> NetworkVisibilityResult:
        cancellation = cancellation or Event()
        gate.require(
            plan.permission.permission_id,
            task_id=plan.permission.task_id,
            operation=plan.operation,
        )
        target = plan.scope.network_targets[0]
        port = plan.scope.network_ports[0]
        if cancellation.is_set():
            return NetworkVisibilityResult(
                target=target,
                port=port,
                reachable=False,
                timed_out=False,
                cancelled=True,
                network_authorized=True,
            )
        timed_out = False
        reachable = False
        try:
            reachable = localhost_tcp_reachable(
                target, port, plan.scope.network_timeout_seconds
            )
        except TimeoutError:
            timed_out = True
        except OSError:
            reachable = False
        return NetworkVisibilityResult(
            target=target,
            port=port,
            reachable=reachable,
            timed_out=timed_out,
            cancelled=cancellation.is_set(),
            network_authorized=True,
        )


class SecurityRemediationWorkflow:
    """Wrap the existing Stage 2 workflow and verify with the real security engine."""

    def __init__(
        self,
        proposal: RemediationProposal,
        creation: ControlledCreationWorkflow,
        analyzer: SecurityAnalysisCoordinator,
        request: SecurityAnalysisRequest,
        before: SecurityAnalysisResult,
    ) -> None:
        self.proposal = proposal
        self.creation = creation
        self.analyzer = analyzer
        self.request = request
        self.before = before

    @classmethod
    def prepare(
        cls,
        finding_id: str,
        result: SecurityAnalysisResult,
        request: SecurityAnalysisRequest,
        dispatcher: EventDispatcher,
        state_store: ApplicationStateStore,
        journal_root: Path,
    ) -> SecurityRemediationWorkflow:
        finding = next(
            (item for item in result.findings if item.finding_id == finding_id), None
        )
        if finding is None or finding.title not in {
            "Debug mode appears enabled",
            "TLS verification disabled",
        }:
            raise ValidationError(
                "Finding has no safe deterministic remediation", source_module=__name__
            )
        root = Path(request.scope.target.root)
        target = root / finding.affected_path
        current = target.read_text(encoding="utf-8")
        if finding.title == "Debug mode appears enabled":
            proposed = re.sub(
                r"(?im)(DEBUG\s*[:=]\s*)(?:true|1)\b", r"\1false", current, count=1
            )
        else:
            proposed = re.sub(
                r"(?i)verify\s*=\s*False", "verify=True", current, count=1
            )
        remediation = RemediationProposal(
            finding_id=finding.finding_id,
            target=finding.affected_path,
            proposed_change="Apply the deterministic safe configuration replacement shown in preview",
            reason=finding.description,
            expected_improvement=finding.recommendation.summary,
            affected_paths=(finding.affected_path,),
        )
        operation = CreationOperation(
            action=CreationAction.UPDATE,
            target=finding.affected_path,
            summary=f"Remediate {finding.title}",
            risk_level=ToolRiskLevel.REVERSIBLE_WRITE,
            tool_name="edit_text_file",
            reversible=True,
            requires_permission=True,
        )
        creation_request = CreationRequest(
            intent=f"Approved security remediation for {finding.finding_id}",
            workspace_root=str(root),
            requested_paths=(finding.affected_path,),
            requirements=("Preview, permission, validation, verification, rollback",),
            constraints=("Exact local target only",),
        )
        creation = ControlledCreationWorkflow(
            creation_request,
            (
                GeneratedFileProposal(
                    operation=operation,
                    proposed_content=proposed,
                    provider_name="deterministic-local",
                    model_name="security-remediation-v1",
                ),
            ),
            CreationCoordinator(dispatcher, CreationPlanner()),
            PermissionGate(),
            journal_root,
        )
        return cls(
            remediation,
            creation,
            SecurityAnalysisCoordinator(dispatcher, state_store),
            request,
            result,
        )

    def approve(self) -> None:
        self.creation.approve()

    def apply_and_verify(self) -> RemediationVerification:
        self.creation.apply()
        after = self.analyzer.analyze(self.request)
        before_count = sum(
            item.finding_id == self.proposal.finding_id for item in self.before.findings
        )
        after_count = sum(
            item.finding_id == self.proposal.finding_id for item in after.findings
        )
        status = (
            SecurityVerificationStatus.RESOLVED
            if before_count and not after_count
            else SecurityVerificationStatus.UNCHANGED
        )
        return RemediationVerification(
            finding_id=self.proposal.finding_id,
            status=status,
            before_count=before_count,
            after_count=after_count,
        )

    def rollback(self) -> None:
        self.creation.rollback()
