"""Instance-owned explicit permission records."""

from virgo.contracts.errors import PermissionDeniedError, ValidationError
from virgo.contracts.models.creation import (
    CreationOperation,
    PermissionDecision,
    PermissionRecord,
    PermissionRequest,
)
from virgo.contracts.models.learning import ResearchDecision, ResearchPermissionRequest


class PermissionGate:
    """Record explicit, scoped decisions without permanent sensitive grants."""

    def __init__(self) -> None:
        self._records: dict[str, PermissionRecord] = {}
        self._consumed_once: set[str] = set()

    def decide(
        self, request: PermissionRequest, decision: PermissionDecision
    ) -> PermissionRecord:
        if not isinstance(request, PermissionRequest):
            raise ValidationError(
                "Permission request is invalid", source_module=__name__
            )
        if decision is PermissionDecision.PENDING:
            raise ValidationError(
                "Permission decision must be explicit", source_module=__name__
            )
        record = PermissionRecord(request=request, decision=decision)
        self._records[request.permission_id] = record
        self._consumed_once.discard(request.permission_id)
        return record

    def require(
        self,
        permission_id: str,
        *,
        task_id: str,
        operation: CreationOperation,
    ) -> PermissionRecord:
        record = self._records.get(permission_id)
        if record is None or record.decision not in (
            PermissionDecision.ALLOW_ONCE,
            PermissionDecision.ALLOW_FOR_TASK,
        ):
            raise PermissionDeniedError(
                "Creation operation lacks explicit approval", source_module=__name__
            )
        if record.request.task_id != task_id or record.request.operation != operation:
            raise PermissionDeniedError(
                "Creation approval does not match the requested scope",
                source_module=__name__,
            )
        if (
            record.decision is PermissionDecision.ALLOW_ONCE
            and permission_id in self._consumed_once
        ):
            raise PermissionDeniedError(
                "One-time creation approval has already been used",
                source_module=__name__,
            )
        if record.decision is PermissionDecision.ALLOW_ONCE:
            self._consumed_once.add(permission_id)
        return record

    def get(self, permission_id: str) -> PermissionRecord | None:
        return self._records.get(permission_id)


class ResearchPermissionGate:
    """Separate, task-bound research grants with no permanent permission mode."""

    def __init__(self) -> None:
        self._records: dict[str, tuple[ResearchPermissionRequest, ResearchDecision]] = (
            {}
        )
        self._consumed_once: set[str] = set()

    def decide(
        self, request: ResearchPermissionRequest, decision: ResearchDecision
    ) -> None:
        if decision is ResearchDecision.MODIFY_SCOPE:
            raise ValidationError(
                "Modified research scope requires a new permission request",
                source_module=__name__,
            )
        self._records[request.permission_id] = (request, decision)

    def require(self, request: ResearchPermissionRequest) -> None:
        record = self._records.get(request.permission_id)
        if record is None or record[0] != request or record[1] is ResearchDecision.DENY:
            raise PermissionDeniedError(
                "Research lacks explicit task-bound approval", source_module=__name__
            )
        if (
            record[1] is ResearchDecision.ALLOW_ONCE
            and request.permission_id in self._consumed_once
        ):
            raise PermissionDeniedError(
                "One-time research approval has already been used",
                source_module=__name__,
            )
        if record[1] is ResearchDecision.ALLOW_ONCE:
            self._consumed_once.add(request.permission_id)
