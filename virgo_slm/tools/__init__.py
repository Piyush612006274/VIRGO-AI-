"""Structured tool-request protocol for Virgo SLM outputs."""

from virgo_slm.tools.protocol import (
    ToolCall,
    ToolCallParser,
    ToolDefinition,
    ToolExecutionResult,
    validate_tool_arguments,
)

__all__ = (
    "ToolCall",
    "ToolCallParser",
    "ToolDefinition",
    "ToolExecutionResult",
    "validate_tool_arguments",
)
