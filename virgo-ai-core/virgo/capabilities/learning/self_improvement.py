"""One-cycle coordinator for permissioned, verified self-improvement."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from virgo.application import ApplicationStateStore
from virgo.application.permissions import PermissionGate
from virgo.application.tasks import ControlledCreationWorkflow, CreationCoordinator
from virgo.capabilities.creation import SafeWorkspace
from virgo.capabilities.learning.experience import EvaluationEngine
from virgo.capabilities.security import SecurityAnalysisCoordinator
from virgo.capabilities.tools import CancellationToken, ValidationProcessTool
from virgo.contracts.errors import (
    PermissionDeniedError,
    SecurityViolationError,
    ValidationError,
)
from virgo.contracts.events import ApplicationState
from virgo.contracts.events.learning import (
    SelfImprovementAcceptedEvent,
    SelfImprovementAppliedEvent,
    SelfImprovementApprovalRequiredEvent,
    SelfImprovementRolledBackEvent,
)
from virgo.contracts.models import (
    ComparisonResult,
    CreationAction,
    CreationOperation,
    CreationRequest,
    DefensiveObjective,
    GeneratedFileProposal,
    PermissionDecision,
    ProcessRequest,
    SecurityAnalysisRequest,
    SecurityFinding,
    SecurityScope,
    SecurityTarget,
    SecurityTargetType,
    SelfImprovementApproval,
    SelfImprovementChange,
    SelfImprovementChangeSet,
    SelfImprovementDecision,
    SelfImprovementEvaluationResult,
    SelfImprovementPermissionRequest,
    SelfImprovementPlan,
    SelfImprovementRequest,
    SelfImprovementResult,
    SelfImprovementRisk,
    SelfImprovementRiskLevel,
    SelfImprovementStatus,
    TaskOutcome,
    TaskOutcomeStatus,
    ToolRiskLevel,
    ValidationStatus,
)
from virgo.infrastructure.events import EventDispatcher

PROTECTED_TARGETS = (
    "MASTER_ARCHITECTURE.md",
    "virgo/application/permissions/",
    "virgo/infrastructure/logging/",
    "virgo/infrastructure/storage/mutation_journal.py",
    "virgo/capabilities/creation/mutation.py",
    "virgo/capabilities/security/",
    "virgo/capabilities/tools/process.py",
    "virgo/capabilities/learning/self_improvement.py",
)


class SelfImprovementCoordinator:
    """Coordinate exactly one approved cycle using existing safety services."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        state_store: ApplicationStateStore,
        permission_gate: PermissionGate,
        creation_coordinator: CreationCoordinator,
        evaluation_engine: EvaluationEngine,
        journal_root: Path,
    ) -> None:
        self.dispatcher = dispatcher
        self.state_store = state_store
        self.permission_gate = permission_gate
        self.creation_coordinator = creation_coordinator
        self.evaluation_engine = evaluation_engine
        self.journal_root = journal_root
        self.plan: SelfImprovementPlan | None = None
        self.approval: SelfImprovementApproval | None = None
        self.workflow: ControlledCreationWorkflow | None = None
        self.evaluation: SelfImprovementEvaluationResult | None = None
        self._security_before = 0
        self._security_before_keys: frozenset[tuple[str, str, str, str]] = frozenset()
        self._baseline_contents: dict[str, str] = {}
        self._process: ValidationProcessTool | None = None
        self._token: CancellationToken | None = None
        self._repository_root: str | None = None

    def prepare(
        self,
        request: SelfImprovementRequest,
        proposed_contents: dict[str, str],
    ) -> SelfImprovementPlan:
        if self.plan is not None:
            raise ValidationError(
                "Only one self-improvement cycle is allowed", source_module=__name__
            )
        root = Path(request.scope.repository_root)
        if (
            not root.is_absolute()
            or not root.is_dir()
            or str(root.resolve()) != str(root)
        ):
            raise SecurityViolationError(
                "Repository root must be exact and canonical", source_module=__name__
            )
        targets = request.scope.target_files
        if tuple(proposed_contents) != targets:
            raise SecurityViolationError(
                "Proposed files do not exactly match scope", source_module=__name__
            )
        protected = tuple(item for item in targets if self._protected(item))
        if protected:
            raise SecurityViolationError(
                "PROTECTED_TARGET / HUMAN_REVIEW_REQUIRED", source_module=__name__
            )
        self._process = ValidationProcessTool(root)
        self._token = CancellationToken()
        self._repository_root = str(root)
        if self._git("git_head").stdout.strip() != request.baseline_head:
            raise SecurityViolationError(
                "Verified baseline HEAD changed", source_module=__name__
            )
        if self._git("git_status").stdout.strip():
            raise SecurityViolationError(
                "Self-improvement baseline must be clean", source_module=__name__
            )
        workspace = SafeWorkspace(root)
        changes: list[SelfImprovementChange] = []
        proposals: list[GeneratedFileProposal] = []
        for target in targets:
            previous = (
                workspace.read_text(target) if (root / target).is_file() else None
            )
            operation = CreationOperation(
                action=(
                    CreationAction.UPDATE
                    if previous is not None
                    else CreationAction.CREATE
                ),
                target=target,
                summary=request.change_concept,
                risk_level=ToolRiskLevel.REVERSIBLE_WRITE,
                tool_name=(
                    "edit_text_file" if previous is not None else "create_text_file"
                ),
                reversible=True,
                requires_permission=True,
            )
            changes.append(
                SelfImprovementChange(
                    target=target,
                    before_sha256=self._hash(root / target),
                    proposed_content=proposed_contents[target],
                    reason=request.change_concept,
                )
            )
            proposals.append(
                GeneratedFileProposal(
                    operation=operation,
                    proposed_content=proposed_contents[target],
                    provider_name="controlled-self-improvement",
                    model_name="explicit-proposal",
                )
            )
        workflow = ControlledCreationWorkflow(
            CreationRequest(
                intent=request.change_concept,
                workspace_root=str(root),
                requested_paths=targets,
                requirements=("explicit approved self-improvement",),
                constraints=("exact scope",),
            ),
            tuple(proposals),
            self.creation_coordinator,
            self.permission_gate,
            self.journal_root,
            task_id=request.task_id,
        )
        change_set = SelfImprovementChangeSet(
            changes=tuple(changes), previews=workflow.previews
        )
        risk = self._risk(targets)
        fingerprint = self._fingerprint(request, change_set)
        permission = SelfImprovementPermissionRequest(
            task_id=request.task_id,
            baseline_head=request.baseline_head,
            target_files=targets,
            scope_fingerprint=fingerprint,
            problem=request.proposal.problem,
            evidence_ids=request.proposal.evidence_ids,
            change_concept=request.change_concept,
            expected_benefit=request.expected_benefit,
            risk=risk,
            validation_plan=request.validation_plan,
        )
        self._baseline_contents = {
            item: workspace.read_text(item) if (root / item).is_file() else ""
            for item in targets
        }
        baseline_values = {
            item.input_reference: self._baseline_contents.get(item.input_reference, "")
            for item in request.validation_plan.evaluations
        }
        baseline_evaluation = self.evaluation_engine.compare(
            request.validation_plan.evaluations, baseline_values, baseline_values
        )
        security_before = self._security(root, request.correlation_id)
        self._security_before = len(security_before.findings)
        self._security_before_keys = self._finding_keys(security_before.findings)
        branch = f"self-improve/{request.task_id[:12]}-candidate"
        self.workflow = workflow
        self.plan = SelfImprovementPlan(
            request=request,
            risk=risk,
            change_set=change_set,
            permission=permission,
            branch_name=branch,
            original_hashes=tuple(
                (item.target, item.before_sha256) for item in changes
            ),
            baseline_evaluation=baseline_evaluation,
        )
        self.dispatcher.publish(
            SelfImprovementApprovalRequiredEvent(
                correlation_id=request.correlation_id,
                task_id=request.task_id,
                risk=risk.level.value,
                target_count=len(targets),
            )
        )
        return self.plan

    def decide_permission(self, approval: SelfImprovementApproval) -> None:
        plan = self._plan()
        expected = plan.permission
        if (
            approval.task_id,
            approval.baseline_head,
            approval.target_files,
            approval.scope_fingerprint,
        ) != (
            expected.task_id,
            expected.baseline_head,
            expected.target_files,
            expected.scope_fingerprint,
        ):
            raise PermissionDeniedError(
                "Self-improvement approval scope changed", source_module=__name__
            )
        self.approval = approval
        if not approval.approved:
            return
        self.workflow.approve()  # type: ignore[union-attr]

    def apply_and_verify(self) -> SelfImprovementResult:
        plan = self._plan()
        if self.approval is None or not self.approval.approved:
            raise PermissionDeniedError(
                "Explicit self-improvement approval is required", source_module=__name__
            )
        root = Path(plan.request.scope.repository_root)
        baseline_statuses = self._tests(plan)
        if any(item is not ValidationStatus.PASSED for item in baseline_statuses):
            raise ValidationError(
                "Focused baseline tests must pass before mutation",
                source_module=__name__,
            )
        plan = replace(plan, baseline_test_statuses=baseline_statuses)
        self.plan = plan
        self._git("git_branch", (plan.branch_name,))
        self.state_store.transition(
            ApplicationState.THINKING,
            status_message="TESTING",
            correlation_id=plan.request.correlation_id,
        )
        try:
            self.workflow.apply()  # type: ignore[union-attr]
            self.dispatcher.publish(
                SelfImprovementAppliedEvent(
                    correlation_id=plan.request.correlation_id,
                    task_id=plan.request.task_id,
                    branch=plan.branch_name,
                    target_count=len(plan.request.scope.target_files),
                )
            )
            statuses = self._tests(plan)
            if any(item is not ValidationStatus.PASSED for item in statuses):
                return self._rollback(
                    SelfImprovementStatus.TEST_FAILED, "Focused test failed"
                )
            security_result = self._security(root, plan.request.correlation_id)
            security_after = len(security_result.findings)
            if (
                self._finding_keys(security_result.findings)
                - self._security_before_keys
            ):
                return self._rollback(
                    SelfImprovementStatus.SECURITY_FAILED,
                    "Security regression detected",
                )
            baseline = {
                item.input_reference: self._baseline_contents.get(
                    item.input_reference, ""
                )
                for item in plan.request.validation_plan.evaluations
            }
            candidate = {
                item.input_reference: (
                    (root / item.input_reference).read_text(encoding="utf-8")
                    if (root / item.input_reference).is_file()
                    else ""
                )
                for item in plan.request.validation_plan.evaluations
            }
            comparison = self.evaluation_engine.compare(
                plan.request.validation_plan.evaluations, baseline, candidate
            )
            self.evaluation = SelfImprovementEvaluationResult(
                comparison=comparison,
                test_statuses=statuses,
                security_findings_before=self._security_before,
                security_findings_after=security_after,
            )
            if comparison.result in (
                ComparisonResult.REGRESSED,
                ComparisonResult.INCONCLUSIVE,
            ):
                return self._rollback(
                    SelfImprovementStatus.REGRESSED,
                    "Candidate evaluation regressed or was inconclusive",
                )
            return self._result(
                SelfImprovementStatus.AWAITING_DECISION,
                "Candidate verified; explicit accept or rollback required",
            )
        finally:
            self.state_store.transition(
                ApplicationState.IDLE, correlation_id=plan.request.correlation_id
            )

    def finish(self, decision: SelfImprovementDecision) -> SelfImprovementResult:
        plan = self._plan()
        if decision is SelfImprovementDecision.ROLLBACK:
            return self._rollback(
                SelfImprovementStatus.ROLLED_BACK, "User selected rollback"
            )
        if self.evaluation is None or self.evaluation.comparison.result not in (
            ComparisonResult.IMPROVED,
            ComparisonResult.UNCHANGED,
        ):
            raise ValidationError(
                "Unverified or regressed candidate cannot be accepted",
                source_module=__name__,
            )
        self.workflow.accept()  # type: ignore[union-attr]
        self._git("git_add", plan.request.scope.target_files)
        commit = self._git("git_commit", (f"self-improve: {plan.request.task_id}",))
        head = self._git("git_head").stdout.strip()
        self.dispatcher.publish(
            SelfImprovementAcceptedEvent(
                correlation_id=plan.request.correlation_id,
                task_id=plan.request.task_id,
                commit_hash=head,
            )
        )
        return replace(
            self._result(SelfImprovementStatus.ACCEPTED, commit.stdout.strip()),
            commit_hash=head,
        )

    def outcome(self, result: SelfImprovementResult) -> TaskOutcome:
        evaluation = self._plan().request.validation_plan.evaluations[0]
        return TaskOutcome(
            task_id=result.task_id,
            capability="learning",
            objective="controlled self-improvement",
            outcome=(
                TaskOutcomeStatus.SUCCESS
                if result.status is SelfImprovementStatus.ACCEPTED
                else TaskOutcomeStatus.ROLLED_BACK
            ),
            validation_summary=result.message,
            rollback_performed=result.rollback_verified,
            scope=evaluation.scope,
            scope_key=evaluation.scope_key,
        )

    def cancel(self) -> None:
        """Request cancellation at the next safe process boundary."""
        if self._token is not None:
            self._token.cancel()

    def _tests(self, plan: SelfImprovementPlan) -> tuple[ValidationStatus, ...]:
        return self._run_tools(
            plan.request.validation_plan.focused_test_tools,
            plan.request.scope.target_files,
            plan.request.scope.repository_root,
            plan.request.task_id,
        )

    def _run_tools(
        self,
        tools: tuple[str, ...],
        targets: tuple[str, ...],
        repository_root: str,
        task_id: str,
    ) -> tuple[ValidationStatus, ...]:
        assert self._process is not None and self._token is not None
        statuses: list[ValidationStatus] = []
        for tool in tools:
            request = ProcessRequest(
                tool_name=tool,
                arguments=targets if tool == "python_compile" else (),
                working_directory=repository_root,
            )
            operation = CreationOperation(
                action=CreationAction.EXECUTE,
                target=tool,
                summary=f"Run {tool}",
                risk_level=ToolRiskLevel.HIGH_IMPACT,
                tool_name="run_validation_test",
                reversible=False,
                requires_permission=True,
            )
            permission = self.creation_coordinator.request_permission(
                task_id,
                operation,
                reason="Run approved focused verification",
                expected_result="Bounded validation result",
            )
            self.permission_gate.decide(permission, PermissionDecision.ALLOW_ONCE)
            self.permission_gate.require(
                permission.permission_id,
                task_id=task_id,
                operation=operation,
            )
            statuses.append(self._process.run(request, self._token).status)
        return tuple(statuses)

    def _security(self, root: Path, correlation_id: str):  # type: ignore[no-untyped-def]
        return SecurityAnalysisCoordinator(self.dispatcher, self.state_store).analyze(
            SecurityAnalysisRequest(
                scope=SecurityScope(
                    target=SecurityTarget(
                        target_type=SecurityTargetType.LOCAL_PROJECT, root=str(root)
                    ),
                    ownership_confirmed=True,
                ),
                objective=DefensiveObjective.SECURE_CODE_REVIEW,
                request_id=correlation_id,
            )
        )

    def _rollback(
        self, status: SelfImprovementStatus, message: str
    ) -> SelfImprovementResult:
        self.workflow.rollback()  # type: ignore[union-attr]
        result = self._result(status, message, rollback=True)
        self.dispatcher.publish(
            SelfImprovementRolledBackEvent(
                correlation_id=self._plan().request.correlation_id,
                task_id=result.task_id,
                reason=message,
                hashes_restored=True,
            )
        )
        return result

    def _result(
        self, status: SelfImprovementStatus, message: str, rollback: bool = False
    ) -> SelfImprovementResult:
        plan = self._plan()
        root = Path(plan.request.scope.repository_root)
        return SelfImprovementResult(
            task_id=plan.request.task_id,
            status=status,
            branch_name=plan.branch_name,
            changed_files=plan.request.scope.target_files,
            before_hashes=plan.original_hashes,
            after_hashes=tuple(
                (item, self._hash(root / item))
                for item in plan.request.scope.target_files
            ),
            evaluation=self.evaluation,
            rollback_verified=rollback
            and plan.original_hashes
            == tuple(
                (item, self._hash(root / item))
                for item in plan.request.scope.target_files
            ),
            message=message,
        )

    def _git(self, tool: str, arguments: tuple[str, ...] = ()):  # type: ignore[no-untyped-def]
        assert self._process is not None and self._token is not None
        if self._repository_root is None:
            raise ValidationError(
                "Self-improvement repository is not prepared", source_module=__name__
            )
        result = self._process.run(
            ProcessRequest(
                tool_name=tool,
                arguments=arguments,
                working_directory=self._repository_root,
                timeout_seconds=30,
            ),
            self._token,
        )
        if result.status is not ValidationStatus.PASSED:
            raise ValidationError(
                f"Controlled Git operation failed: {tool}",
                technical_detail=result.stderr,
                source_module=__name__,
            )
        return result

    def _plan(self) -> SelfImprovementPlan:
        if self.plan is None:
            raise ValidationError(
                "Self-improvement task is not prepared", source_module=__name__
            )
        return self.plan

    @staticmethod
    def _protected(target: str) -> bool:
        normalized = target.replace("\\", "/")
        return any(
            normalized == item.rstrip("/") or normalized.startswith(item)
            for item in PROTECTED_TARGETS
        )

    @staticmethod
    def _risk(targets: tuple[str, ...]) -> SelfImprovementRisk:
        reasons = [f"{len(targets)} explicitly scoped file(s)"]
        level = SelfImprovementRiskLevel.LOW
        if len(targets) > 1:
            level = SelfImprovementRiskLevel.MEDIUM
        if any(item.startswith(("virgo/", "apps/")) for item in targets):
            level = SelfImprovementRiskLevel.HIGH
            reasons.append("production subsystem target")
        if any(
            Path(item).name in {"pyproject.toml", "Cargo.toml", "Cargo.lock"}
            for item in targets
        ):
            level = SelfImprovementRiskLevel.CRITICAL
            reasons.append("dependency or build impact")
        return SelfImprovementRisk(level=level, reasons=tuple(reasons))

    @staticmethod
    def _fingerprint(
        request: SelfImprovementRequest, changes: SelfImprovementChangeSet
    ) -> str:
        value = "\n".join(
            (
                request.task_id,
                request.baseline_head,
                request.change_concept,
                *(
                    f"{item.target}:{item.before_sha256}:{item.after_sha256}"
                    for item in changes.changes
                ),
            )
        )
        return sha256(value.encode()).hexdigest()

    @staticmethod
    def _hash(path: Path) -> str | None:
        return sha256(path.read_bytes()).hexdigest() if path.is_file() else None

    @staticmethod
    def _finding_keys(
        findings: tuple[SecurityFinding, ...],
    ) -> frozenset[tuple[str, str, str, str]]:
        return frozenset(
            (
                item.category.value,
                item.affected_path,
                item.title,
                item.severity.value,
            )
            for item in findings
        )
