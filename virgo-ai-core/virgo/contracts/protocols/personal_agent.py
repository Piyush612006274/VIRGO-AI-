"""Protocol for runtime-owned bounded agents."""

from threading import Event
from typing import Protocol

from virgo.contracts.models.personal_runtime import (
    PersonalTaskPlan,
    PersonalTaskRequest,
    PersonalTaskResult,
    PersonalTaskVerification,
)


class PersonalAgentProtocol(Protocol):
    agent_id: str

    def plan(self, request: PersonalTaskRequest) -> PersonalTaskPlan: ...

    def execute(
        self, request: PersonalTaskRequest, plan: PersonalTaskPlan, cancellation: Event
    ) -> PersonalTaskResult: ...

    def verify(self, result: PersonalTaskResult) -> PersonalTaskVerification: ...

    def cancel(self) -> None: ...
