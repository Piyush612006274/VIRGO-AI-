"""End-to-end controlled local creation lifecycle."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from virgo.application.permissions import PermissionGate
from virgo.application.tasks.creation_coordinator import CreationCoordinator
from virgo.application.tasks.state import CreationTaskState
from virgo.capabilities.creation import (
    ControlledMutationService,
    SafeWorkspace,
    build_change_preview,
    validate_content,
)
from virgo.capabilities.tools import CancellationToken, ValidationProcessTool
from virgo.contracts.errors import ValidationError
from virgo.contracts.models import (
    ChangePreview,
    CreationAction,
    CreationAuditReport,
    CreationOperation,
    CreationRequest,
    CreationTaskStatus,
    GeneratedFileProposal,
    PermissionDecision,
    PermissionRequest,
    ProcessRequest,
    ProcessResult,
    ToolRiskLevel,
    ValidationResult,
    ValidationStatus,
    new_correlation_id,
)


class ControlledCreationWorkflow:
    """Own one task from preview through explicit accept or rollback."""

    def __init__(
        self,
        request: CreationRequest,
        proposals: tuple[GeneratedFileProposal, ...],
        coordinator: CreationCoordinator,
        permission_gate: PermissionGate,
        journal_root: Path,
        *,
        task_id: str | None = None,
        process_tool: ValidationProcessTool | None = None,
        normalized_intent: str | None = None,
        capability: str | None = None,
        provider_explanation: str | None = None,
    ) -> None:
        if not proposals:
            raise ValidationError(
                "Creation workflow requires proposals", source_module=__name__
            )
        self.request = request
        self.task_id = task_id or new_correlation_id()
        self.state = CreationTaskState(self.task_id)
        self.coordinator = coordinator
        self.permission_gate = permission_gate
        self.workspace = SafeWorkspace(Path(request.workspace_root))
        self.mutations = ControlledMutationService(
            self.workspace.root,
            self.task_id,
            permission_gate,
            journal_root,
        )
        self.process_tool = process_tool or ValidationProcessTool(self.workspace.root)
        self.normalized_intent = normalized_intent
        self.capability = capability
        self.provider_explanation = provider_explanation
        self.proposals: tuple[GeneratedFileProposal, ...] = ()
        self.previews: tuple[ChangePreview, ...] = ()
        self.permission_requests: tuple[PermissionRequest, ...] = ()
        self.validation_results: tuple[ValidationResult, ...] = ()
        self.test_results: tuple[ProcessResult, ...] = ()
        self.errors: list[str] = []
        self._prepare(proposals)

    def _prepare(self, proposals: tuple[GeneratedFileProposal, ...]) -> None:
        approved_paths = set(self.request.requested_paths)
        if {proposal.operation.target for proposal in proposals} != approved_paths:
            raise ValidationError(
                "Proposal paths must exactly match the requested scope",
                source_module=__name__,
            )
        validated: list[GeneratedFileProposal] = []
        previews: list[ChangePreview] = []
        validation_results: list[ValidationResult] = []
        for proposal in proposals:
            result = validate_content(
                proposal.operation.target, proposal.proposed_content
            )
            validation_results.append(result)
            if result.status is not ValidationStatus.PASSED:
                raise ValidationError(
                    f"Proposal validation failed for {proposal.operation.target}",
                    technical_detail=result.message,
                    source_module=__name__,
                )
            if proposal.operation.action is CreationAction.CREATE:
                previous = None
                if (self.workspace.root / proposal.operation.target).exists():
                    raise ValidationError(
                        f"Create target already exists: {proposal.operation.target}",
                        source_module=__name__,
                    )
            else:
                previous = self.workspace.read_text(proposal.operation.target)
            current = replace(proposal, validated=True)
            validated.append(current)
            previews.append(
                build_change_preview(
                    proposal.operation.target,
                    previous,
                    proposal.proposed_content,
                )
            )
        self.proposals = tuple(validated)
        self.previews = tuple(previews)
        self.validation_results = tuple(validation_results)

    def approve(self) -> tuple[PermissionRequest, ...]:
        if self.state.status is not CreationTaskStatus.PREVIEW_READY:
            raise ValidationError(
                "Creation task is not awaiting approval", source_module=__name__
            )
        requests = tuple(
            self.coordinator.request_permission(
                self.task_id,
                proposal.operation,
                reason=proposal.operation.summary,
                expected_result=f"Apply the previewed change to {proposal.operation.target}",
            )
            for proposal in self.proposals
        )
        for request in requests:
            self.permission_gate.decide(request, PermissionDecision.ALLOW_ONCE)
        self.permission_requests = requests
        self.state.transition(CreationTaskStatus.APPROVED)
        return requests

    def apply(self) -> None:
        if self.state.status is not CreationTaskStatus.APPROVED:
            raise ValidationError(
                "Creation task has not been approved", source_module=__name__
            )
        self.state.transition(CreationTaskStatus.APPLYING)
        try:
            for proposal, preview, permission in zip(
                self.proposals,
                self.previews,
                self.permission_requests,
                strict=True,
            ):
                self.mutations.apply(proposal, preview, permission.permission_id)
            self.state.transition(CreationTaskStatus.VALIDATING)
            self._validate_applied_files()
            self.state.transition(CreationTaskStatus.AWAITING_ACCEPTANCE)
        except Exception as error:
            self.errors.append(str(error))
            if self.mutations.journal.entries:
                self.state.transition(CreationTaskStatus.ROLLING_BACK)
                self.mutations.rollback()
                self.state.transition(CreationTaskStatus.ROLLED_BACK)
            else:
                self.state.transition(CreationTaskStatus.FAILED)
            raise

    def run_test(
        self,
        request: ProcessRequest,
        cancellation: CancellationToken,
        permission: PermissionRequest,
    ) -> ProcessResult:
        if self.state.status is not CreationTaskStatus.AWAITING_ACCEPTANCE:
            raise ValidationError(
                "Creation task is not ready for testing", source_module=__name__
            )
        self.permission_gate.require(
            permission.permission_id,
            task_id=self.task_id,
            operation=permission.operation,
        )
        if (
            permission.operation.action is not CreationAction.EXECUTE
            or permission.operation.target != request.tool_name
        ):
            raise ValidationError(
                "Validation command approval does not match the request",
                source_module=__name__,
            )
        self.state.transition(CreationTaskStatus.TESTING)
        result = self.process_tool.run(request, cancellation)
        self.test_results = (*self.test_results, result)
        if result.status is not ValidationStatus.PASSED:
            self.state.transition(CreationTaskStatus.ROLLING_BACK)
            self.mutations.rollback()
            self.state.transition(CreationTaskStatus.ROLLED_BACK)
            return result
        self.state.transition(CreationTaskStatus.AWAITING_ACCEPTANCE)
        return result

    def approve_test(self, request: ProcessRequest) -> PermissionRequest:
        operation = CreationOperation(
            action=CreationAction.EXECUTE,
            target=request.tool_name,
            summary=f"Run approved validation tool {request.tool_name}",
            risk_level=ToolRiskLevel.HIGH_IMPACT,
            tool_name="run_validation_test",
            reversible=False,
            requires_permission=True,
        )
        permission = self.coordinator.request_permission(
            self.task_id,
            operation,
            reason="Run the explicitly selected bounded project validation",
            expected_result="A timed, cancellable validation result",
        )
        self.permission_gate.decide(permission, PermissionDecision.ALLOW_ONCE)
        return permission

    def accept(self) -> CreationAuditReport:
        if self.state.status is not CreationTaskStatus.AWAITING_ACCEPTANCE:
            raise ValidationError(
                "Creation task is not awaiting acceptance", source_module=__name__
            )
        self.mutations.accept()
        self.state.transition(CreationTaskStatus.ACCEPTED)
        return self.report()

    def rollback(self) -> CreationAuditReport:
        if self.state.status not in (
            CreationTaskStatus.APPROVED,
            CreationTaskStatus.AWAITING_ACCEPTANCE,
            CreationTaskStatus.FAILED,
            CreationTaskStatus.CANCELLED,
        ):
            raise ValidationError(
                "Creation task cannot be rolled back now", source_module=__name__
            )
        self.state.transition(CreationTaskStatus.ROLLING_BACK)
        self.mutations.rollback()
        self.state.transition(CreationTaskStatus.ROLLED_BACK)
        return self.report()

    def report(self) -> CreationAuditReport:
        entries = self.mutations.journal.entries
        provider = self.proposals[0].provider_name if self.proposals else None
        model = self.proposals[0].model_name if self.proposals else None
        return CreationAuditReport(
            task_id=self.task_id,
            request_summary=self.request.intent,
            approved_paths=tuple(
                proposal.operation.target for proposal in self.proposals
            ),
            changed_paths=tuple(entry.operation.target for entry in entries),
            tools_used=tuple(
                dict.fromkeys(entry.operation.tool_name for entry in entries)
            ),
            provider_name=provider,
            model_name=model,
            validation_results=self.validation_results,
            test_results=self.test_results,
            task_status=self.state.status,
            rollback_result=(
                "verified"
                if self.state.status is CreationTaskStatus.ROLLED_BACK
                else None
            ),
            errors=tuple(self.errors),
            normalized_intent=self.normalized_intent,
            capability=self.capability,
            provider_explanation=self.provider_explanation,
            plan_steps=tuple(proposal.operation.summary for proposal in self.proposals),
            operations_performed=tuple(
                entry.operation.action.value for entry in entries
            ),
            permission_decisions=tuple("allow_once" for _ in self.permission_requests),
            acceptance=(
                "accepted" if self.state.status is CreationTaskStatus.ACCEPTED else None
            ),
        )

    def _validate_applied_files(self) -> None:
        results: list[ValidationResult] = []
        for proposal in self.proposals:
            content = self.workspace.read_text(proposal.operation.target)
            result = validate_content(proposal.operation.target, content)
            results.append(result)
            self.mutations.set_validation(
                proposal.operation.operation_id, result.status
            )
            if result.status is not ValidationStatus.PASSED:
                raise ValidationError(
                    f"Applied file validation failed: {proposal.operation.target}",
                    source_module=__name__,
                )
        self.validation_results = tuple(results)
