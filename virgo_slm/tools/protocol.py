"""Structured tool-call protocol.

The SLM can request a tool, but this layer never executes one. Virgo's
permission/safety/tool engine remains the sole execution authority.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters_schema: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not self.description.strip():
            raise ValueError("tool description must not be empty")
        if self.parameters_schema.get("type") != "object":
            raise ValueError("tool parameter schema root must be an object")


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any]
    call_id: str

    @classmethod
    def create(cls, name: str, arguments: Mapping[str, Any]) -> "ToolCall":
        return cls(name=name, arguments=dict(arguments), call_id=str(uuid.uuid4()))


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    call_id: str
    success: bool
    output: str
    error: str | None = None


def validate_tool_arguments(
    definition: ToolDefinition,
    arguments: Mapping[str, Any],
) -> tuple[bool, str | None]:
    schema = definition.parameters_schema
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    if not isinstance(arguments, Mapping):
        return False, "arguments must be an object"
    missing = [name for name in required if name not in arguments]
    if missing:
        return False, f"missing required arguments: {', '.join(map(str, missing))}"
    additional = schema.get("additionalProperties", True)
    if additional is False:
        unknown = set(arguments) - set(properties)
        if unknown:
            return False, f"unknown arguments: {', '.join(sorted(map(str, unknown)))}"
    for name, value in arguments.items():
        spec = properties.get(name)
        if not isinstance(spec, Mapping) or "type" not in spec:
            continue
        expected = spec["type"]
        if expected == "string" and not isinstance(value, str):
            return False, f"{name} must be a string"
        if expected == "integer" and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            return False, f"{name} must be an integer"
        if expected == "number" and (
            not isinstance(value, int | float) or isinstance(value, bool)
        ):
            return False, f"{name} must be a number"
        if expected == "boolean" and not isinstance(value, bool):
            return False, f"{name} must be a boolean"
    return True, None


class ToolCallParser:
    """Parse a model response without granting execution authority."""

    PREFIX = "<|tool_call|>"
    SUFFIX = "<|end_tool_call|>"

    def parse(self, text: str) -> tuple[ToolCall, ...]:
        calls: list[ToolCall] = []
        cursor = 0
        while True:
            start = text.find(self.PREFIX, cursor)
            if start < 0:
                break
            end = text.find(self.SUFFIX, start + len(self.PREFIX))
            if end < 0:
                raise ValueError("unterminated tool call block")
            payload_text = text[start + len(self.PREFIX) : end].strip()
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError as error:
                raise ValueError("tool call is not valid JSON") from error
            if not isinstance(payload, dict) or not isinstance(
                payload.get("name"), str
            ):
                raise ValueError("tool call requires a name")
            arguments = payload.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("tool call arguments must be an object")
            call_id = payload.get("call_id")
            calls.append(
                ToolCall.create(payload["name"], arguments)
                if not isinstance(call_id, str) or not call_id
                else ToolCall(
                    name=payload["name"],
                    arguments=dict(arguments),
                    call_id=call_id,
                )
            )
            cursor = end + len(self.SUFFIX)
        return tuple(calls)
