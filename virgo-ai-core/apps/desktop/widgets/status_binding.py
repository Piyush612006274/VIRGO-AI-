"""Explicit application-state binding for the status presentation area."""

from apps.desktop.widgets.status_bar import StatusBarWidget
from virgo.contracts.errors import ValidationError
from virgo.contracts.events import ApplicationStateChangedEvent
from virgo.infrastructure.events import EventDispatcher


class StatusStateBinding:
    """Translate state-change events into status-widget presentation updates."""

    def __init__(
        self,
        dispatcher: EventDispatcher,
        status_widget: StatusBarWidget,
    ) -> None:
        if not isinstance(dispatcher, EventDispatcher):
            raise ValidationError(
                "Status binding requires an EventDispatcher",
                source_module=__name__,
            )
        if not isinstance(status_widget, StatusBarWidget):
            raise ValidationError(
                "Status binding requires a StatusBarWidget",
                source_module=__name__,
            )
        self._dispatcher = dispatcher
        self._status_widget = status_widget
        self._subscribed = dispatcher.subscribe(
            ApplicationStateChangedEvent,
            self._handle_state_changed,
        )

    @property
    def is_subscribed(self) -> bool:
        """Report whether this binding currently owns a subscription."""
        return self._subscribed

    def close(self) -> None:
        """Release the owned event subscription idempotently."""
        if self._subscribed:
            self._dispatcher.unsubscribe(
                ApplicationStateChangedEvent,
                self._handle_state_changed,
            )
            self._subscribed = False

    def _handle_state_changed(self, event: ApplicationStateChangedEvent) -> None:
        self._status_widget.set_status_text(event.current.status_message)
        self._status_widget.set_visual_state(event.current.state.value)
