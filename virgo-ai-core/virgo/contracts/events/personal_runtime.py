"""Metadata-only personal task lifecycle events."""

from dataclasses import dataclass
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskStartedEvent(ApplicationEvent):
    EVENT_NAME: ClassVar[str] = "personal_task_started"


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskPlanCreatedEvent(ApplicationEvent):
    EVENT_NAME: ClassVar[str] = "personal_task_plan_created"


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskCancelledEvent(ApplicationEvent):
    EVENT_NAME: ClassVar[str] = "personal_task_cancelled"


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskCompletedEvent(ApplicationEvent):
    EVENT_NAME: ClassVar[str] = "personal_task_completed"


@dataclass(frozen=True, slots=True, kw_only=True)
class PersonalTaskFailedEvent(ApplicationEvent):
    EVENT_NAME: ClassVar[str] = "personal_task_failed"
