"""Minimal application lifecycle event contracts."""

from dataclasses import dataclass
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationStartedEvent(ApplicationEvent):
    """Report that the application foundation has started."""

    EVENT_NAME: ClassVar[str] = "application_started"


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationStoppingEvent(ApplicationEvent):
    """Report that the application foundation is stopping."""

    EVENT_NAME: ClassVar[str] = "application_stopping"
