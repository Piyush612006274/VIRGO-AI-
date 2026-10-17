"""Foundation-level Virgo exception hierarchy."""

from typing import ClassVar

from virgo.contracts.errors.base import VirgoError
from virgo.contracts.errors.codes import ErrorCategory, ErrorCode


class ConfigurationError(VirgoError):
    error_code = ErrorCode.CONFIGURATION_ERROR
    error_category = ErrorCategory.CONFIGURATION
    default_user_explanation = "The application configuration is invalid."


class ProviderUnavailableError(VirgoError):
    error_code = ErrorCode.PROVIDER_UNAVAILABLE
    error_category = ErrorCategory.PROVIDER_UNAVAILABLE
    default_user_explanation = "The requested service is currently unavailable."
    recoverable = True
    retry_advice: ClassVar[str | None] = "Try again later."


class ModelUnavailableError(VirgoError):
    error_code = ErrorCode.MODEL_UNAVAILABLE
    error_category = ErrorCategory.MODEL_UNAVAILABLE
    default_user_explanation = "The requested model is currently unavailable."
    recoverable = True
    retry_advice: ClassVar[str | None] = "Try again later."


class AudioDeviceError(VirgoError):
    error_code = ErrorCode.AUDIO_DEVICE_ERROR
    error_category = ErrorCategory.AUDIO_DEVICE_FAILURE
    default_user_explanation = "The audio device could not be used."
    recoverable = True
    retry_advice: ClassVar[str | None] = "Check the device and try again."


class OperationTimeoutError(VirgoError):
    error_code = ErrorCode.OPERATION_TIMEOUT
    error_category = ErrorCategory.TIMEOUT
    default_user_explanation = "The operation took too long to complete."
    recoverable = True
    retry_advice: ClassVar[str | None] = "Try the operation again."


class PermissionDeniedError(VirgoError):
    error_code = ErrorCode.PERMISSION_DENIED
    error_category = ErrorCategory.PERMISSION_DENIED
    default_user_explanation = "Permission was not granted for this operation."


class ValidationError(VirgoError):
    error_code = ErrorCode.VALIDATION_ERROR
    error_category = ErrorCategory.VALIDATION_FAILURE
    default_user_explanation = "The supplied information is invalid."


class ToolExecutionError(VirgoError):
    error_code = ErrorCode.TOOL_EXECUTION_ERROR
    error_category = ErrorCategory.TOOL_FAILURE
    default_user_explanation = "The requested tool could not complete its work."


class StorageError(VirgoError):
    error_code = ErrorCode.STORAGE_ERROR
    error_category = ErrorCategory.STORAGE_FAILURE
    default_user_explanation = "Stored information could not be accessed safely."
    recoverable = True
    retry_advice: ClassVar[str | None] = "Try again later."


class RustCoreError(VirgoError):
    error_code = ErrorCode.RUST_CORE_ERROR
    error_category = ErrorCategory.RUST_CORE_FAILURE
    default_user_explanation = "A core operation could not be completed."


class SecurityViolationError(VirgoError):
    error_code = ErrorCode.SECURITY_VIOLATION
    error_category = ErrorCategory.SECURITY_VIOLATION
    default_user_explanation = "The operation was blocked for safety."


class UnknownInternalError(VirgoError):
    error_code = ErrorCode.UNKNOWN_INTERNAL_ERROR
    error_category = ErrorCategory.UNKNOWN_INTERNAL_FAILURE
    default_user_explanation = "An internal error occurred."
