"""Typed immutable application-state event contracts."""

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent, EventDictionary
from virgo.contracts.models import ErrorInfo, is_valid_correlation_id


class ApplicationState(StrEnum):
    """Stage 1 application state vocabulary without workflow behavior."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING_SPEECH = "processing_speech"
    THINKING = "thinking"
    RESPONDING = "responding"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    RECOVERING = "recovering"
    ERROR = "error"
    OFFLINE = "offline"


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationStateSnapshot:
    """Minimal safe application-state value object."""

    state: ApplicationState
    status_message: str
    error: ErrorInfo | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, ApplicationState):
            raise ValueError("state must be an ApplicationState")
        if not isinstance(self.status_message, str) or not self.status_message.strip():
            raise ValueError("status_message must not be empty")
        if self.error is not None and not isinstance(self.error, ErrorInfo):
            raise ValueError("error must be an ErrorInfo instance")
        if self.correlation_id is not None and not is_valid_correlation_id(
            self.correlation_id
        ):
            raise ValueError("correlation_id must be a canonical UUID string")

    def to_dict(self) -> EventDictionary:
        """Serialize only safe declared state fields."""
        return {
            "state": self.state.value,
            "status_message": self.status_message,
            "error": self.error.to_dict() if self.error is not None else None,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationStateChangedEvent(ApplicationEvent):
    """Report one real transition between immutable state snapshots."""

    previous: ApplicationStateSnapshot
    current: ApplicationStateSnapshot

    EVENT_NAME: ClassVar[str] = "application_state_changed"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if not isinstance(self.previous, ApplicationStateSnapshot):
            raise ValueError("previous must be an ApplicationStateSnapshot")
        if not isinstance(self.current, ApplicationStateSnapshot):
            raise ValueError("current must be an ApplicationStateSnapshot")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["previous"] = self.previous.to_dict()
        serialized["current"] = self.current.to_dict()
        return serialized
