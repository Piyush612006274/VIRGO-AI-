"""Explicit provider registry and local model router."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from threading import Event, RLock

from virgo.contracts.errors import (
    ModelUnavailableError,
    ProviderUnavailableError,
    ValidationError,
)
from virgo.contracts.models import LLMRequest, LLMResponse, LLMStreamChunk
from virgo.contracts.protocols import LLMProviderProtocol


class ModelRouter:
    """Resolve an explicit model name to a registered local provider."""

    def __init__(self, providers: Sequence[LLMProviderProtocol]) -> None:
        if not providers:
            raise ValidationError(
                "ModelRouter requires at least one provider", source_module=__name__
            )
        self._providers = tuple(providers)
        self._lock = RLock()
        self._model_map: dict[str, LLMProviderProtocol] = {}
        self.refresh()

    @property
    def providers(self) -> tuple[LLMProviderProtocol, ...]:
        return self._providers

    def refresh(self) -> tuple[str, ...]:
        """Refresh advertised models from all registered providers."""
        mapping: dict[str, LLMProviderProtocol] = {}
        for provider in self._providers:
            try:
                for model in provider.list_models():
                    if isinstance(model, str) and model.strip():
                        mapping.setdefault(model.strip(), provider)
            except Exception:
                continue
        with self._lock:
            self._model_map = mapping
        return tuple(mapping)

    def list_models(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._model_map)

    def resolve(self, model: str) -> LLMProviderProtocol:
        normalized = model.strip() if isinstance(model, str) else ""
        if not normalized:
            raise ValidationError(
                "Model name must not be empty", source_module=__name__
            )
        with self._lock:
            provider = self._model_map.get(normalized)
        if provider is not None:
            return provider
        self.refresh()
        with self._lock:
            provider = self._model_map.get(normalized)
        if provider is not None:
            return provider
        raise ModelUnavailableError(
            "No configured local provider advertises the selected model",
            technical_detail=f"Requested model: {normalized}",
            source_module=__name__,
        )

    def health(self) -> dict[str, bool]:
        status: dict[str, bool] = {}
        for index, provider in enumerate(self._providers):
            key = getattr(provider, "provider_name", f"provider-{index}")
            try:
                status[str(key)] = bool(provider.health_check())
            except Exception:
                status[str(key)] = False
        return status


class RoutedLLMProvider(LLMProviderProtocol):
    """Provider-protocol facade used by the conversation orchestrator."""

    DEFAULT_PROVIDER_NAME = "model-router"

    def __init__(self, router: ModelRouter) -> None:
        self._router = router
        self._lock = RLock()
        self._last_provider_name: str | None = None

    @property
    def provider_name(self) -> str:
        """Return the provider used by the most recent routed request."""
        with self._lock:
            return self._last_provider_name or self.DEFAULT_PROVIDER_NAME

    @property
    def router(self) -> ModelRouter:
        return self._router

    def health_check(self) -> bool:
        statuses = self._router.health()
        if any(statuses.values()):
            return True
        raise ProviderUnavailableError(
            "No local LLM provider is healthy", source_module=__name__
        )

    def list_models(self) -> tuple[str, ...]:
        return self._router.refresh()

    def generate(self, request: LLMRequest) -> LLMResponse:
        provider = self._router.resolve(request.model)
        self._record_provider(provider)
        return provider.generate(request)

    def stream(
        self,
        request: LLMRequest,
        cancellation: Event | None = None,
    ) -> Iterator[LLMStreamChunk]:
        provider = self._router.resolve(request.model)
        self._record_provider(provider)
        yield from provider.stream(request, cancellation)

    def close(self) -> None:
        for provider in self._router.providers:
            provider.close()

    def _record_provider(self, provider: LLMProviderProtocol) -> None:
        with self._lock:
            self._last_provider_name = str(
                getattr(provider, "provider_name", self.DEFAULT_PROVIDER_NAME)
            )
