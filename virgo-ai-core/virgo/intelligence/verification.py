"""Deterministic verifier kept separate from execution evidence production."""

from collections.abc import Callable
from threading import Event

from virgo.contracts.models.capability_execution import CapabilityExecutionStatus
from virgo.contracts.models.verification import (
    VerificationRequest,
    VerificationResult,
    VerificationStatus,
)


class ResponseVerifier:
    """Verify one scoped claim using an independently invoked postcondition read-back."""

    def verify(
        self,
        request: VerificationRequest,
        execution_status: CapabilityExecutionStatus,
        *,
        read_back: Callable[[], str] | None = None,
        cancellation: Event | None = None,
    ) -> VerificationResult:
        references = request.execution_evidence.audit_references
        if cancellation is not None and cancellation.is_set():
            return self._result(request, VerificationStatus.CANCELLED, references)
        if execution_status is not CapabilityExecutionStatus.COMPLETED:
            return self._result(
                request,
                VerificationStatus.FAILED,
                references,
                limitations=("execution did not complete successfully",),
            )
        if request.expected_postcondition is None or read_back is None:
            return self._result(
                request,
                VerificationStatus.NOT_VERIFIABLE,
                references,
                limitations=("no independent postcondition read-back is available",),
            )
        try:
            observed = read_back()
        except (OSError, RuntimeError, ValueError) as error:
            return self._result(
                request,
                VerificationStatus.UNVERIFIED,
                references,
                limitations=(
                    f"postcondition read-back failed: {type(error).__name__}",
                ),
            )
        all_references = (*references, f"postcondition:{request.verification_id}")
        if observed == request.expected_postcondition:
            return self._result(
                request,
                VerificationStatus.VERIFIED,
                all_references,
                verified=(request.claim,),
            )
        if not observed.strip():
            return self._result(
                request,
                VerificationStatus.UNVERIFIED,
                all_references,
                unverified=(request.claim,),
                limitations=("postcondition was not observed",),
            )
        if request.expected_postcondition.startswith(observed):
            return self._result(
                request,
                VerificationStatus.PARTIALLY_VERIFIED,
                all_references,
                unverified=(request.claim,),
                limitations=("postcondition matched only part of the observed state",),
            )
        return self._result(
            request,
            VerificationStatus.CONFLICTING,
            all_references,
            unverified=(request.claim,),
            conflicts=("observed postcondition differs from expected postcondition",),
        )

    @staticmethod
    def _result(
        request: VerificationRequest,
        status: VerificationStatus,
        references: tuple[str, ...],
        *,
        verified: tuple[str, ...] = (),
        unverified: tuple[str, ...] = (),
        conflicts: tuple[str, ...] = (),
        limitations: tuple[str, ...] = (),
    ) -> VerificationResult:
        return VerificationResult(
            verification_id=request.verification_id,
            task_id=request.task_id,
            status=status,
            verified_claims=verified,
            unverified_claims=unverified,
            conflicts=conflicts,
            evidence_references=references,
            limitations=limitations,
        )
