"""Public local language-model providers."""

from virgo.contracts.models import LLMRequest, LLMResponse, LLMStreamChunk
from virgo.contracts.protocols import LLMProviderProtocol
from virgo.providers.llm.ollama_provider import (
    DEFAULT_OLLAMA_ENDPOINT,
    OllamaLLMProvider,
    OllamaTransportProtocol,
)
from virgo.providers.llm.virgo_slm_provider import (
    DEFAULT_VIRGO_SLM_ARTIFACT,
    DEFAULT_VIRGO_SLM_MODEL,
    VIRGO_SLM_PROVIDER_NAME,
    VirgoSLMProvider,
)

__all__ = (
    "DEFAULT_OLLAMA_ENDPOINT",
    "DEFAULT_VIRGO_SLM_ARTIFACT",
    "DEFAULT_VIRGO_SLM_MODEL",
    "LLMProviderProtocol",
    "LLMRequest",
    "LLMResponse",
    "LLMStreamChunk",
    "OllamaLLMProvider",
    "OllamaTransportProtocol",
    "VIRGO_SLM_PROVIDER_NAME",
    "VirgoSLMProvider",
)
