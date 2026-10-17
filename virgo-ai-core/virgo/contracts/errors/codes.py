"""Stable machine-readable error codes and categories."""

from enum import StrEnum


class ErrorCategory(StrEnum):
    """Provider-neutral failure categories required by the architecture."""

    CONFIGURATION = "configuration"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    AUDIO_DEVICE_FAILURE = "audio_device_failure"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    VALIDATION_FAILURE = "validation_failure"
    TOOL_FAILURE = "tool_failure"
    STORAGE_FAILURE = "storage_failure"
    RUST_CORE_FAILURE = "rust_core_failure"
    SECURITY_VIOLATION = "security_violation"
    UNKNOWN_INTERNAL_FAILURE = "unknown_internal_failure"


class ErrorCode(StrEnum):
    """Stable foundation-level error codes used across module boundaries."""

    CONFIGURATION_ERROR = "configuration_error"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    AUDIO_DEVICE_ERROR = "audio_device_error"
    OPERATION_TIMEOUT = "operation_timeout"
    PERMISSION_DENIED = "permission_denied"
    VALIDATION_ERROR = "validation_error"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    STORAGE_ERROR = "storage_error"
    RUST_CORE_ERROR = "rust_core_error"
    SECURITY_VIOLATION = "security_violation"
    UNKNOWN_INTERNAL_ERROR = "unknown_internal_error"
