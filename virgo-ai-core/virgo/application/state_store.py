"""Instance-owned application state store."""

from virgo.contracts.errors import ValidationError
from virgo.contracts.events import (
    ApplicationState,
    ApplicationStateChangedEvent,
    ApplicationStateSnapshot,
)
from virgo.contracts.models import ErrorInfo
from virgo.infrastructure.events import EventDispatcher

STATE_STATUS_MESSAGES: dict[ApplicationState, str] = {
    ApplicationState.IDLE: "Ready",
    ApplicationState.LISTENING: "Listening",
    ApplicationState.PROCESSING_SPEECH: "Processing speech",
    ApplicationState.THINKING: "Thinking",
    ApplicationState.RESPONDING: "Responding",
    ApplicationState.SPEAKING: "Speaking",
    ApplicationState.INTERRUPTED: "Interrupted",
    ApplicationState.RECOVERING: "Recovering",
    ApplicationState.ERROR: "Error",
    ApplicationState.OFFLINE: "Offline",
}


class ApplicationStateStore:
    """Hold one immutable snapshot and publish actual changes synchronously."""

    def __init__(self, dispatcher: EventDispatcher) -> None:
        if not isinstance(dispatcher, EventDispatcher):
            raise ValidationError(
                "State store requires an EventDispatcher",
                source_module=__name__,
            )
        self._dispatcher = dispatcher
        self._snapshot = ApplicationStateSnapshot(
            state=ApplicationState.IDLE,
            status_message=STATE_STATUS_MESSAGES[ApplicationState.IDLE],
        )

    @property
    def snapshot(self) -> ApplicationStateSnapshot:
        """Return the current immutable snapshot."""
        return self._snapshot

    def transition(
        self,
        state: ApplicationState,
        *,
        status_message: str | None = None,
        error: ErrorInfo | None = None,
        correlation_id: str | None = None,
    ) -> ApplicationStateSnapshot:
        """Replace the snapshot and publish exactly one event when it changes."""
        if not isinstance(state, ApplicationState):
            raise ValidationError(
                "State transition requires an ApplicationState",
                source_module=__name__,
            )
        try:
            current = ApplicationStateSnapshot(
                state=state,
                status_message=(
                    STATE_STATUS_MESSAGES[state]
                    if status_message is None
                    else status_message
                ),
                error=error,
                correlation_id=correlation_id,
            )
        except (TypeError, ValueError) as invalid_snapshot:
            raise ValidationError(
                "State transition contains invalid snapshot data",
                technical_detail=str(invalid_snapshot),
                source_module=__name__,
                cause=invalid_snapshot,
            ) from invalid_snapshot

        previous = self._snapshot
        if current == previous:
            return previous
        self._snapshot = current
        self._dispatcher.publish(
            ApplicationStateChangedEvent(
                previous=previous,
                current=current,
                correlation_id=current.correlation_id,
                source_module=__name__,
            )
        )
        return current
