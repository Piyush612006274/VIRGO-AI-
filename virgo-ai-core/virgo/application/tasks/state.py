"""Task-local creation lifecycle; this does not replace application state."""

from virgo.contracts.errors import ValidationError
from virgo.contracts.models import CreationTaskStatus

ALLOWED_TRANSITIONS: dict[CreationTaskStatus, tuple[CreationTaskStatus, ...]] = {
    CreationTaskStatus.PREVIEW_READY: (CreationTaskStatus.APPROVED,),
    CreationTaskStatus.APPROVED: (
        CreationTaskStatus.APPLYING,
        CreationTaskStatus.ROLLING_BACK,
    ),
    CreationTaskStatus.APPLYING: (
        CreationTaskStatus.VALIDATING,
        CreationTaskStatus.ROLLING_BACK,
        CreationTaskStatus.FAILED,
        CreationTaskStatus.CANCELLED,
    ),
    CreationTaskStatus.VALIDATING: (
        CreationTaskStatus.TESTING,
        CreationTaskStatus.AWAITING_ACCEPTANCE,
        CreationTaskStatus.ROLLING_BACK,
        CreationTaskStatus.FAILED,
    ),
    CreationTaskStatus.TESTING: (
        CreationTaskStatus.AWAITING_ACCEPTANCE,
        CreationTaskStatus.ROLLING_BACK,
        CreationTaskStatus.FAILED,
        CreationTaskStatus.CANCELLED,
    ),
    CreationTaskStatus.AWAITING_ACCEPTANCE: (
        CreationTaskStatus.TESTING,
        CreationTaskStatus.ACCEPTED,
        CreationTaskStatus.ROLLING_BACK,
    ),
    CreationTaskStatus.ROLLING_BACK: (
        CreationTaskStatus.ROLLED_BACK,
        CreationTaskStatus.FAILED,
    ),
    CreationTaskStatus.ACCEPTED: (),
    CreationTaskStatus.ROLLED_BACK: (),
    CreationTaskStatus.FAILED: (CreationTaskStatus.ROLLING_BACK,),
    CreationTaskStatus.CANCELLED: (CreationTaskStatus.ROLLING_BACK,),
}


class CreationTaskState:
    def __init__(self, task_id: str) -> None:
        if not task_id.strip():
            raise ValidationError(
                "Creation task ID is required", source_module=__name__
            )
        self.task_id = task_id
        self.status = CreationTaskStatus.PREVIEW_READY

    def transition(self, status: CreationTaskStatus) -> CreationTaskStatus:
        if status not in ALLOWED_TRANSITIONS[self.status]:
            raise ValidationError(
                f"Invalid creation transition: {self.status.value} -> {status.value}",
                source_module=__name__,
            )
        self.status = status
        return status
