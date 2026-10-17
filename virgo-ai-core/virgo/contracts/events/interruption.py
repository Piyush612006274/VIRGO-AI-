"""Minimal typed events for coordinated interruption."""

from dataclasses import dataclass
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent, EventDictionary
from virgo.contracts.events.state import ApplicationState
from virgo.contracts.models.interruption import InterruptionRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class InterruptionRequestedEvent(ApplicationEvent):
    request: InterruptionRequest

    EVENT_NAME: ClassVar[str] = "interruption_requested"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if not isinstance(self.request, InterruptionRequest):
            raise ValueError("request must be an InterruptionRequest")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["request"] = self.request.to_dict()
        return serialized


@dataclass(frozen=True, slots=True, kw_only=True)
class InterruptionCompletedEvent(ApplicationEvent):
    request: InterruptionRequest
    active_state: ApplicationState
    handled: bool

    EVENT_NAME: ClassVar[str] = "interruption_completed"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        if not isinstance(self.request, InterruptionRequest):
            raise ValueError("request must be an InterruptionRequest")
        if not isinstance(self.active_state, ApplicationState):
            raise ValueError("active_state must be an ApplicationState")
        if not isinstance(self.handled, bool):
            raise ValueError("handled must be a bool")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["request"] = self.request.to_dict()
        serialized["active_state"] = self.active_state.value
        serialized["handled"] = self.handled
        return serialized
