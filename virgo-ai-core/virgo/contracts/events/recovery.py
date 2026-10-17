"""Minimal immutable recovery lifecycle events."""

from dataclasses import dataclass
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent, EventDictionary
from virgo.contracts.models import ErrorInfo


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoveryStartedEvent(ApplicationEvent):
    operation_name: str
    EVENT_NAME: ClassVar[str] = "recovery_started"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        _require_operation_name(self.operation_name)

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["operation_name"] = self.operation_name
        return serialized


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoveryAttemptEvent(ApplicationEvent):
    operation_name: str
    attempt: int
    EVENT_NAME: ClassVar[str] = "recovery_attempt"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        _require_operation_name(self.operation_name)
        _require_attempt(self.attempt)

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized.update(operation_name=self.operation_name, attempt=self.attempt)
        return serialized


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoverySucceededEvent(ApplicationEvent):
    operation_name: str
    attempts: int
    EVENT_NAME: ClassVar[str] = "recovery_succeeded"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        _require_operation_name(self.operation_name)
        _require_attempt(self.attempts)

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized.update(operation_name=self.operation_name, attempts=self.attempts)
        return serialized


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoveryFailedEvent(ApplicationEvent):
    operation_name: str
    attempts: int
    error: ErrorInfo
    EVENT_NAME: ClassVar[str] = "recovery_failed"

    def __post_init__(self) -> None:
        ApplicationEvent.__post_init__(self)
        _require_operation_name(self.operation_name)
        _require_attempt(self.attempts)
        if not isinstance(self.error, ErrorInfo):
            raise ValueError("error must be an ErrorInfo")

    def to_dict(self) -> EventDictionary:
        serialized = ApplicationEvent.to_dict(self)
        serialized["operation_name"] = self.operation_name
        serialized["attempts"] = self.attempts
        serialized["error_code"] = self.error.code.value
        return serialized


def _require_operation_name(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("operation_name must not be empty")


def _require_attempt(value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("attempt count must be a positive integer")
