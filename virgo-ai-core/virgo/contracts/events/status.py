"""Minimal status and structured-error event contracts."""

from dataclasses import dataclass
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent, EventDictionary
from virgo.contracts.models import ErrorInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class StatusMessageEvent(ApplicationEvent):
    """Carry one presentation-neutral status message."""

    message: str

    EVENT_NAME: ClassVar[str] = "status_message"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if not self.message.strip():
            raise ValueError("message must not be empty")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["message"] = self.message
        return serialized


@dataclass(frozen=True, slots=True, kw_only=True)
class ErrorOccurredEvent(ApplicationEvent):
    """Carry canonical structured error information without exception internals."""

    error: ErrorInfo

    EVENT_NAME: ClassVar[str] = "error_occurred"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if not isinstance(self.error, ErrorInfo):
            raise ValueError("error must be an ErrorInfo instance")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["error"] = self.error.to_dict()
        return serialized
