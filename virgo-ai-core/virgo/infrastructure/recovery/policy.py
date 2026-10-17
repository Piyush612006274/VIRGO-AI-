"""Bounded synchronous retry and application-state recovery coordination."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from time import sleep
from typing import TypeVar

from virgo.application.state_store import ApplicationStateStore
from virgo.contracts.errors import UnknownInternalError, ValidationError, VirgoError
from virgo.contracts.events import (
    ApplicationState,
    RecoveryAttemptEvent,
    RecoveryFailedEvent,
    RecoveryStartedEvent,
    RecoverySucceededEvent,
)
from virgo.infrastructure.events import EventDispatcher

ResultT = TypeVar("ResultT")
AttemptHandler = Callable[[int], None]


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoveryPolicy:
    max_attempts: int = 3
    retry_delay_seconds: float = 0.1
    maximum_delay_seconds: float = 1.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or not 1 <= self.max_attempts <= 5
        ):
            raise ValueError("max_attempts must be between one and five")
        if (
            not isinstance(self.retry_delay_seconds, int | float)
            or isinstance(self.retry_delay_seconds, bool)
            or not 0 <= self.retry_delay_seconds <= 5
        ):
            raise ValueError("retry_delay_seconds must be between zero and five")
        if (
            not isinstance(self.maximum_delay_seconds, int | float)
            or isinstance(self.maximum_delay_seconds, bool)
            or not 0 <= self.maximum_delay_seconds <= 10
        ):
            raise ValueError("maximum_delay_seconds must be between zero and ten")

    def execute(
        self,
        operation: Callable[[], ResultT],
        *,
        cancellation: Event | None = None,
        on_attempt: AttemptHandler | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> ResultT:
        for attempt in range(1, self.max_attempts + 1):
            self._require_not_cancelled(cancellation)
            if on_attempt is not None:
                on_attempt(attempt)
            try:
                return operation()
            except VirgoError as error:
                if not error.error_info.recoverable or attempt == self.max_attempts:
                    raise
                delay = min(
                    self.retry_delay_seconds * attempt,
                    self.maximum_delay_seconds,
                )
                self._require_not_cancelled(cancellation)
                if delay:
                    sleeper(delay)
            except Exception as error:
                raise UnknownInternalError(
                    "Recovery operation failed unexpectedly",
                    technical_detail=f"{type(error).__name__}: {error}",
                    source_module=__name__,
                    cause=error,
                ) from error
        raise AssertionError("bounded retry loop exhausted unexpectedly")

    @staticmethod
    def _require_not_cancelled(cancellation: Event | None) -> None:
        if cancellation is not None and cancellation.is_set():
            raise ValidationError(
                "Recovery was cancelled",
                source_module=__name__,
            )


class RecoveryCoordinator:
    """Apply one policy while publishing lifecycle and state changes."""

    def __init__(
        self,
        policy: RecoveryPolicy,
        dispatcher: EventDispatcher,
        state_store: ApplicationStateStore,
    ) -> None:
        self._policy = policy
        self._dispatcher = dispatcher
        self._state_store = state_store

    def execute(
        self,
        operation_name: str,
        operation: Callable[[], ResultT],
        *,
        correlation_id: str,
        cancellation: Event | None = None,
    ) -> ResultT:
        if not operation_name.strip():
            raise ValidationError(
                "operation_name must not be empty", source_module=__name__
            )
        self._dispatcher.publish(
            RecoveryStartedEvent(
                operation_name=operation_name,
                correlation_id=correlation_id,
                source_module=__name__,
            )
        )
        self._state_store.transition(
            ApplicationState.RECOVERING,
            correlation_id=correlation_id,
        )
        attempts = 0

        def report_attempt(attempt: int) -> None:
            nonlocal attempts
            attempts = attempt
            self._dispatcher.publish(
                RecoveryAttemptEvent(
                    operation_name=operation_name,
                    attempt=attempt,
                    correlation_id=correlation_id,
                    source_module=__name__,
                )
            )

        try:
            result = self._policy.execute(
                operation,
                cancellation=cancellation,
                on_attempt=report_attempt,
            )
        except VirgoError as error:
            self._state_store.transition(
                ApplicationState.ERROR,
                error=error.error_info,
                correlation_id=correlation_id,
            )
            self._dispatcher.publish(
                RecoveryFailedEvent(
                    operation_name=operation_name,
                    attempts=attempts,
                    error=error.error_info,
                    correlation_id=correlation_id,
                    source_module=__name__,
                )
            )
            raise
        self._state_store.transition(
            ApplicationState.IDLE,
            correlation_id=correlation_id,
        )
        self._dispatcher.publish(
            RecoverySucceededEvent(
                operation_name=operation_name,
                attempts=attempts,
                correlation_id=correlation_id,
                source_module=__name__,
            )
        )
        return result
