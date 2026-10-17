"""Coordinate deterministic requirements, inspection, planning, and permission."""

from pathlib import Path

from virgo.capabilities.creation import SafeWorkspace
from virgo.contracts.errors import ValidationError
from virgo.contracts.events.creation import (
    CreationPermissionRequestedEvent,
    CreationPlanPreparedEvent,
)
from virgo.contracts.models.creation import (
    CreationOperation,
    CreationRequest,
    CreationReview,
    PermissionRequest,
)
from virgo.infrastructure.events import EventDispatcher
from virgo.intelligence.planner import CreationPlanner


class CreationCoordinator:
    """Stop at preview/permission; Step 1 never mutates the workspace."""

    def __init__(self, dispatcher: EventDispatcher, planner: CreationPlanner) -> None:
        if not isinstance(dispatcher, EventDispatcher) or not isinstance(
            planner, CreationPlanner
        ):
            raise ValidationError(
                "Creation coordinator dependencies are invalid", source_module=__name__
            )
        self._dispatcher = dispatcher
        self._planner = planner

    def review(self, request: CreationRequest) -> CreationReview:
        missing = self._planner.missing_requirements(request)
        if missing:
            return CreationReview(
                request=request,
                missing_requirements=missing,
                inspection=None,
                plan=None,
            )
        workspace = SafeWorkspace(Path(request.workspace_root))
        inspection = workspace.inspect(request.requested_paths)
        plan = self._planner.create_plan(request)
        self._dispatcher.publish(
            CreationPlanPreparedEvent(
                plan=plan,
                correlation_id=request.request_id,
                source_module=__name__,
            )
        )
        return CreationReview(
            request=request,
            missing_requirements=(),
            inspection=inspection,
            plan=plan,
        )

    def request_permission(
        self,
        task_id: str,
        operation: CreationOperation,
        *,
        reason: str,
        expected_result: str,
    ) -> PermissionRequest:
        if not operation.requires_permission:
            raise ValidationError(
                "Read-only operations do not require high-impact approval",
                source_module=__name__,
            )
        request = PermissionRequest(
            task_id=task_id,
            operation=operation,
            reason=reason,
            expected_result=expected_result,
            rollback_available=operation.reversible,
        )
        self._dispatcher.publish(
            CreationPermissionRequestedEvent(
                request=request,
                correlation_id=task_id,
                source_module=__name__,
            )
        )
        return request
