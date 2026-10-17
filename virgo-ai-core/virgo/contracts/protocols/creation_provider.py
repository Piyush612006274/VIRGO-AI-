"""Provider-neutral boundary for untrusted creation proposals."""

from typing import Protocol

from virgo.contracts.models import LLMRequest, LLMResponse


class CreationLLMProviderProtocol(Protocol):
    def generate(self, request: LLMRequest) -> LLMResponse: ...
