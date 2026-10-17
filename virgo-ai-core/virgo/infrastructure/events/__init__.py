"""Public synchronous in-process event infrastructure."""

from virgo.infrastructure.events.dispatcher import EventDispatcher, EventHandler

__all__ = ("EventDispatcher", "EventHandler")
