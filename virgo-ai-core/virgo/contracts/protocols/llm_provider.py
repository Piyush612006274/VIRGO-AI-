"""Synchronous local language-model provider boundary."""

from collections.abc import Iterator
from threading import Event
from typing import Protocol

from virgo.contracts.models import LLMRequest, LLMResponse, LLMStreamChunk


class LLMProviderProtocol(Protocol):
    """Minimal explicit lifecycle for one local LLM provider."""

    def health_check(self) -> bool: ...

    def list_models(self) -> tuple[str, ...]: ...

    def generate(self, request: LLMRequest) -> LLMResponse: ...

    def stream(
        self,
        request: LLMRequest,
        cancellation: Event | None = None,
    ) -> Iterator[LLMStreamChunk]: ...

    def close(self) -> None: ...
