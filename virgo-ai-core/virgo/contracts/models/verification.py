"""Independent, claim-scoped verification contracts."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from virgo.contracts.models.capability_execution import CapabilityExecutionEvidence
from virgo.contracts.models.correlation import new_correlation_id


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    UNVERIFIED = "unverified"
    CONFLICTING = "conflicting"
    FAILED = "failed"
    NOT_VERIFIABLE = "not_verifiable"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True, kw_only=True)
class VerificationRequest:
    task_id: str
    claim: str
    expected_postcondition: str | None
    execution_evidence: CapabilityExecutionEvidence
    verification_id: str = field(default_factory=new_correlation_id)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.task_id != self.execution_evidence.task_id or not self.claim.strip():
            raise ValueError("verification request identity is invalid")
        if (
            self.expected_postcondition is not None
            and not self.expected_postcondition.strip()
        ):
            raise ValueError("expected postcondition must be non-empty text")


@dataclass(frozen=True, slots=True, kw_only=True)
class VerificationResult:
    verification_id: str
    task_id: str
    status: VerificationStatus
    verified_claims: tuple[str, ...] = ()
    unverified_claims: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    method: str = "independent_postcondition_read_back"
    limitations: tuple[str, ...] = ()
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def passed(self) -> bool:
        """Compatibility view; only fully verified results pass."""
        return self.status is VerificationStatus.VERIFIED
