"""Public structured error contracts and exception types."""

from virgo.contracts.errors.base import VirgoError
from virgo.contracts.errors.codes import ErrorCategory, ErrorCode
from virgo.contracts.errors.exceptions import (
    AudioDeviceError,
    ConfigurationError,
    ModelUnavailableError,
    OperationTimeoutError,
    PermissionDeniedError,
    ProviderUnavailableError,
    RustCoreError,
    SecurityViolationError,
    StorageError,
    ToolExecutionError,
    UnknownInternalError,
    ValidationError,
)

__all__ = (
    "AudioDeviceError",
    "ConfigurationError",
    "ErrorCategory",
    "ErrorCode",
    "ModelUnavailableError",
    "OperationTimeoutError",
    "PermissionDeniedError",
    "ProviderUnavailableError",
    "RustCoreError",
    "SecurityViolationError",
    "StorageError",
    "ToolExecutionError",
    "UnknownInternalError",
    "ValidationError",
    "VirgoError",
)
