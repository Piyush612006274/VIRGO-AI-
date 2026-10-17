"""Coordinate explicit interruption of active conversation or speech."""

from __future__ import annotations

from threading import RLock
from typing import Protocol

from virgo.application.state_store import ApplicationStateStore
from virgo.contracts.errors import UnknownInternalError, ValidationError, VirgoError
from virgo.contracts.events import (
    ApplicationState,
    InterruptionCompletedEvent,
    InterruptionRequestedEvent,
)
from virgo.contracts.models import InterruptionRequest
from virgo.infrastructure.events import EventDispatcher

INTERRUPTIBLE_CONVERSATION_STATES = frozenset(
    (ApplicationState.THINKING, ApplicationState.RESPONDING)
)


class ConversationCancellationProtocol(Protocol):
    def cancel_active(self, correlation_id: str) -> bool: ...


class PlaybackCancellationProtocol(Protocol):
    @property
    def is_playing(self) -> bool: ...

    def stop(self) -> None: ...


class BargeInCoordinator:
    """Route one explicit interruption to the currently active capability."""

    def __init__(
        self,
        conversation: ConversationCancellationProtocol,
        playback: PlaybackCancellationProtocol,
        state_store: ApplicationStateStore,
        dispatcher: EventDispatcher,
    ) -> None:
        self._conversation = conversation
        self._playback = playback
        self._state_store = state_store
        self._dispatcher = dispatcher
        self._lock = RLock()
        self._last_request_id: str | None = None

    def interrupt(self, request: InterruptionRequest) -> bool:
        """Stop active work once and report whether cancellation was applied."""
        if not isinstance(request, InterruptionRequest):
            raise ValidationError(
                "Interruption requires an InterruptionRequest",
                source_module=__name__,
            )
        with self._lock:
            if request.correlation_id == self._last_request_id:
                return False
            self._last_request_id = request.correlation_id
            active_state = self._state_store.snapshot.state
            self._dispatcher.publish(
                InterruptionRequestedEvent(
                    request=request,
                    correlation_id=request.correlation_id,
                    source_module=__name__,
                )
            )
            try:
                handled = self._interrupt_active(request, active_state)
            except VirgoError:
                self._state_store.transition(
                    ApplicationState.ERROR,
                    correlation_id=request.correlation_id,
                )
                raise
            except Exception as error:
                failure = UnknownInternalError(
                    "Interruption failed unexpectedly",
                    technical_detail=f"{type(error).__name__}: {error}",
                    source_module=__name__,
                    correlation_id=request.correlation_id,
                    cause=error,
                )
                self._state_store.transition(
                    ApplicationState.ERROR,
                    error=failure.error_info,
                    correlation_id=request.correlation_id,
                )
                raise failure from error
            self._dispatcher.publish(
                InterruptionCompletedEvent(
                    request=request,
                    active_state=active_state,
                    handled=handled,
                    correlation_id=request.correlation_id,
                    source_module=__name__,
                )
            )
            return handled

    def _interrupt_active(
        self,
        request: InterruptionRequest,
        active_state: ApplicationState,
    ) -> bool:
        if active_state in INTERRUPTIBLE_CONVERSATION_STATES:
            return self._conversation.cancel_active(request.correlation_id)
        if active_state is not ApplicationState.SPEAKING:
            return False
        if not self._playback.is_playing:
            return False
        self._playback.stop()
        self._state_store.transition(
            ApplicationState.INTERRUPTED,
            correlation_id=request.correlation_id,
        )
        self._state_store.transition(
            ApplicationState.IDLE,
            correlation_id=request.correlation_id,
        )
        return True
