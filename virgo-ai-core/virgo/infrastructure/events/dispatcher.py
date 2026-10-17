"""Synchronous instance-owned in-process event dispatcher."""

from collections.abc import Callable
from typing import TypeVar, cast

from virgo.contracts.errors import UnknownInternalError, ValidationError, VirgoError
from virgo.contracts.events import ApplicationEvent

EventT = TypeVar("EventT", bound=ApplicationEvent)
EventHandler = Callable[[EventT], None]
StoredEventHandler = Callable[[ApplicationEvent], None]


class EventDispatcher:
    """Dispatch events synchronously in subscriber registration order."""

    def __init__(self) -> None:
        self._subscribers: dict[type[ApplicationEvent], list[StoredEventHandler]] = {}

    def subscribe(
        self,
        event_type: type[EventT],
        handler: EventHandler[EventT],
    ) -> bool:
        """Register *handler* once for exactly one event class."""
        self._validate_subscription(event_type, handler)
        stored_handler = cast(StoredEventHandler, handler)
        handlers = self._subscribers.setdefault(event_type, [])
        if stored_handler in handlers:
            return False
        handlers.append(stored_handler)
        return True

    def unsubscribe(
        self,
        event_type: type[EventT],
        handler: EventHandler[EventT],
    ) -> bool:
        """Remove a registration safely and report whether it existed."""
        self._validate_subscription(event_type, handler)
        stored_handler = cast(StoredEventHandler, handler)
        handlers = self._subscribers.get(event_type)
        if handlers is None or stored_handler not in handlers:
            return False
        handlers.remove(stored_handler)
        if not handlers:
            del self._subscribers[event_type]
        return True

    def publish(self, event: ApplicationEvent) -> None:
        """Invoke a snapshot of matching subscribers in registration order."""
        if not isinstance(event, ApplicationEvent):
            raise ValidationError(
                "Published value must be an ApplicationEvent",
                source_module=__name__,
            )
        for handler in tuple(self._subscribers.get(type(event), ())):
            try:
                handler(event)
            except VirgoError:
                raise
            except Exception as error:
                raise UnknownInternalError(
                    f"Event handler failed for {event.event_name}",
                    technical_detail=f"{type(error).__name__}: {error}",
                    user_safe_explanation="An internal event handler failed.",
                    source_module=__name__,
                    cause=error,
                ) from error

    def subscriber_count(self, event_type: type[ApplicationEvent]) -> int:
        """Return the current registration count for one event class."""
        if not isinstance(event_type, type) or not issubclass(
            event_type, ApplicationEvent
        ):
            raise ValidationError(
                "Subscriber count requires an ApplicationEvent class",
                source_module=__name__,
            )
        return len(self._subscribers.get(event_type, ()))

    @staticmethod
    def _validate_subscription(
        event_type: object,
        handler: object,
    ) -> None:
        if not isinstance(event_type, type) or not issubclass(
            event_type, ApplicationEvent
        ):
            raise ValidationError(
                "Subscription requires an ApplicationEvent class",
                source_module=__name__,
            )
        if not callable(handler):
            raise ValidationError(
                "Subscription handler must be callable",
                source_module=__name__,
            )
