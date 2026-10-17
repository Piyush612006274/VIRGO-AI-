"""Deterministic clarification, decomposition, and plan validation."""

from pathlib import PurePath

from virgo.contracts.errors import SecurityViolationError, ValidationError
from virgo.contracts.models.creation import (
    CreationAction,
    CreationOperation,
    CreationPlan,
    CreationRequest,
    MissingRequirement,
    ToolRiskLevel,
)


class CreationPlanner:
    """Prepare a minimal plan; generation providers remain outside this boundary."""

    def missing_requirements(
        self, request: CreationRequest
    ) -> tuple[MissingRequirement, ...]:
        missing: list[MissingRequirement] = []
        if not request.requested_paths:
            missing.append(
                MissingRequirement(
                    key="requested_paths",
                    question="Which workspace-relative files should Virgo inspect or change?",
                )
            )
        if not request.requirements:
            missing.append(
                MissingRequirement(
                    key="requirements",
                    question="What observable result must the creation task produce?",
                )
            )
        return tuple(missing)

    def create_plan(self, request: CreationRequest) -> CreationPlan:
        if self.missing_requirements(request):
            raise ValidationError(
                "Creation requirements are incomplete", source_module=__name__
            )
        operations = tuple(
            CreationOperation(
                action=CreationAction.INSPECT,
                target=target,
                summary=f"Inspect {target} before proposing any change",
                risk_level=ToolRiskLevel.READ_ONLY,
                tool_name="safe_workspace.inspect",
                reversible=True,
                requires_permission=False,
            )
            for target in request.requested_paths
        )
        plan = CreationPlan(
            request_id=request.request_id,
            operations=operations,
            validation_steps=("Validate workspace path containment",),
            test_steps=("Verify the proposed output before acceptance",),
        )
        self.validate(plan)
        return plan

    def validate(self, plan: CreationPlan) -> None:
        for operation in plan.operations:
            path = PurePath(operation.target)
            if path.is_absolute() or ".." in path.parts:
                raise SecurityViolationError(
                    "Creation plan target escapes the workspace",
                    source_module=__name__,
                )
            if operation.risk_level is ToolRiskLevel.PROHIBITED:
                raise SecurityViolationError(
                    "Creation plan contains a prohibited operation",
                    source_module=__name__,
                )
            if (
                operation.action is not CreationAction.INSPECT
                and not operation.requires_permission
            ):
                raise SecurityViolationError(
                    "Mutating creation operations require permission",
                    source_module=__name__,
                )
