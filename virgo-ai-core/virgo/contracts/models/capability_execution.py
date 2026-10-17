"""Typed bounded capability resolution and execution evidence."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.personal_runtime import ActionRisk, RuntimeProviderStatus


class CapabilityType(StrEnum):
    TOOL = "tool"
    AGENT = "agent"


class RollbackState(StrEnum):
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    NOT_REQUIRED = "not_required"
    AVAILABLE = "available"
    ATTEMPTED = "attempted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CapabilityExecutionStatus(StrEnum):
    COMPLETED = "completed"
    PERMISSION_REQUIRED = "permission_required"
    NOT_AVAILABLE = "not_available"
    INCOMPATIBLE = "incompatible"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class CapabilityResolutionStatus(StrEnum):
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    INCOMPATIBLE = "incompatible"
    PERMISSION_REQUIRED = "permission_required"


@dataclass(frozen=True, slots=True, kw_only=True)
class EnvironmentFacts:
    platform: str
    working_directory: str
    filesystem_scope: str
    network_available: bool
    configured_runtimes: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityDescriptor:
    capability_id: str
    name: str
    description: str
    capability_type: CapabilityType
    input_contract: str
    output_contract: str
    permission_required: bool
    risk: ActionRisk
    timeout_seconds: float
    cancellation_supported: bool
    audit_logged: bool
    rollback: RollbackState
    environment_requirements: tuple[str, ...]
    availability: RuntimeProviderStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityExecutionRequest:
    task_id: str
    capability: CapabilityDescriptor
    objective: str
    validated_input: tuple[tuple[str, str], ...]
    environment: EnvironmentFacts
    working_scope: str
    expected_output: str
    permission_id: str | None = None
    timeout_seconds: float = 30.0
    execution_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if (
            not self.task_id.strip()
            or not self.objective.strip()
            or not self.working_scope.strip()
        ):
            raise ValueError("capability execution request identity is invalid")
        if not 0 < self.timeout_seconds <= self.capability.timeout_seconds:
            raise ValueError("capability execution timeout exceeds registration")
        if self.capability.permission_required != (self.permission_id is not None):
            raise ValueError("capability permission preflight is inconsistent")
        if any(
            not key.strip() or not value.strip() for key, value in self.validated_input
        ):
            raise ValueError("capability input must be non-empty text")


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityExecutionEvidence:
    execution_id: str
    task_id: str
    capability_id: str
    started_at: datetime
    finished_at: datetime
    validated_input_summary: tuple[str, ...]
    environment_summary: str
    permission_reference: str | None
    operations_performed: tuple[str, ...]
    structured_output: str | None
    errors: tuple[str, ...]
    cancelled: bool
    timed_out: bool
    rollback: RollbackState
    audit_references: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityExecutionResult:
    status: CapabilityExecutionStatus
    evidence: CapabilityExecutionEvidence
    verified: bool = False

    def __post_init__(self) -> None:
        if self.verified:
            raise ValueError("executor output cannot self-certify verification")


@dataclass(frozen=True, slots=True, kw_only=True)
class CapabilityResolution:
    status: CapabilityResolutionStatus
    descriptor: CapabilityDescriptor | None
    request: CapabilityExecutionRequest | None
    reason: str
