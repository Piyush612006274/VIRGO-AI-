"""Base exception carrying canonical structured error information."""

from typing import ClassVar

from virgo.contracts.errors.codes import ErrorCategory, ErrorCode
from virgo.contracts.models.correlation import new_correlation_id
from virgo.contracts.models.error_info import ErrorDictionary, ErrorInfo


class VirgoError(Exception):
    """Common base for deterministic application exceptions."""

    error_code: ClassVar[ErrorCode] = ErrorCode.UNKNOWN_INTERNAL_ERROR
    error_category: ClassVar[ErrorCategory] = ErrorCategory.UNKNOWN_INTERNAL_FAILURE
    default_user_explanation: ClassVar[str] = "An internal error occurred."
    recoverable: ClassVar[bool] = False
    retry_advice: ClassVar[str | None] = None

    def __init__(
        self,
        message: str,
        *,
        technical_detail: str | None = None,
        user_safe_explanation: str | None = None,
        source_module: str,
        correlation_id: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        """Build the exception without logging, recovery, or external I/O."""
        self.error_info = ErrorInfo(
            code=self.error_code,
            category=self.error_category,
            message=message,
            technical_detail=technical_detail,
            user_safe_explanation=(
                user_safe_explanation or self.default_user_explanation
            ),
            recoverable=self.recoverable,
            retry_advice=self.retry_advice,
            source_module=source_module,
            correlation_id=correlation_id or new_correlation_id(),
        )
        self.original_cause = cause
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause

    @property
    def user_safe_explanation(self) -> str:
        """Return the explanation intended for display to a user."""
        return self.error_info.user_safe_explanation

    def to_dict(self) -> ErrorDictionary:
        """Return safe declared fields without cause or traceback internals."""
        return self.error_info.to_dict()
