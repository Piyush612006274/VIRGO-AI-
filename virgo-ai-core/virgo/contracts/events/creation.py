"""Events emitted by the preview-first Creation Core."""

from dataclasses import dataclass
from typing import ClassVar

from virgo.contracts.events.base import ApplicationEvent
from virgo.contracts.models.creation import CreationPlan, PermissionRequest


@dataclass(frozen=True, slots=True, kw_only=True)
class CreationPlanPreparedEvent(ApplicationEvent):
    plan: CreationPlan

    EVENT_NAME: ClassVar[str] = "creation_plan_prepared"


@dataclass(frozen=True, slots=True, kw_only=True)
class CreationPermissionRequestedEvent(ApplicationEvent):
    request: PermissionRequest

    EVENT_NAME: ClassVar[str] = "creation_permission_requested"
