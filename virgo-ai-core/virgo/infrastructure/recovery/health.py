"""Side-effect-minimal health adapters for existing Stage 1 components."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol

from virgo.capabilities.voice.discovery import AudioDeviceDiscoveryService
from virgo.contracts.errors import VirgoError
from virgo.contracts.models import (
    ProviderComponentType,
    ProviderHealthResult,
    ProviderHealthStatus,
)


class STTHealthProviderProtocol(Protocol):
    @property
    def is_ready(self) -> bool: ...

    @property
    def model_name(self) -> str: ...


class LLMHealthProviderProtocol(Protocol):
    def health_check(self) -> bool: ...

    def list_models(self) -> tuple[str, ...]: ...


class TTSHealthProviderProtocol(Protocol):
    @property
    def is_ready(self) -> bool: ...

    def list_voices(self) -> tuple[str, ...]: ...


class HealthCheckProtocol(Protocol):
    provider_name: str
    component_type: ProviderComponentType

    def check(self) -> ProviderHealthResult: ...


class STTHealthCheck:
    provider_name = "faster-whisper"
    component_type = ProviderComponentType.STT

    def __init__(self, provider: STTHealthProviderProtocol) -> None:
        self._provider = provider

    def check(self) -> ProviderHealthResult:
        started = perf_counter()
        if self._provider.is_ready:
            return _result(
                self.provider_name,
                self.component_type,
                ProviderHealthStatus.HEALTHY,
                "STT model is loaded and ready",
                started,
                selected_resource=self._provider.model_name,
            )
        return _result(
            self.provider_name,
            self.component_type,
            ProviderHealthStatus.DEGRADED,
            "STT runtime is configured but its model is not loaded",
            started,
            selected_resource=self._provider.model_name,
        )


class OllamaHealthCheck:
    provider_name = "ollama"
    component_type = ProviderComponentType.LLM

    def __init__(
        self,
        provider: LLMHealthProviderProtocol,
        *,
        selected_model: str | None = None,
    ) -> None:
        self._provider = provider
        self._selected_model = selected_model

    def check(self) -> ProviderHealthResult:
        started = perf_counter()
        try:
            self._provider.health_check()
            models = self._provider.list_models()
        except VirgoError as error:
            return _error_result(
                self.provider_name,
                self.component_type,
                started,
                error,
            )
        selected_available = (
            self._selected_model is None or self._selected_model in models
        )
        return _result(
            self.provider_name,
            self.component_type,
            (
                ProviderHealthStatus.HEALTHY
                if selected_available and models
                else ProviderHealthStatus.DEGRADED
            ),
            (
                "Local Ollama endpoint and selected model are ready"
                if selected_available and models
                else "Ollama is reachable but the selected model is unavailable"
            ),
            started,
            selected_resource=self._selected_model,
            available_count=len(models),
        )


class ModelRouterHealthCheck:
    """Health adapter for the composite local model router."""

    provider_name = "local-model-router"
    component_type = ProviderComponentType.LLM

    def __init__(self, provider: LLMHealthProviderProtocol, *, selected_model: str | None = None) -> None:
        self._provider = provider
        self._selected_model = selected_model

    def check(self) -> ProviderHealthResult:
        started = perf_counter()
        try:
            self._provider.health_check()
            models = self._provider.list_models()
        except VirgoError as error:
            return _error_result(self.provider_name, self.component_type, started, error)
        selected_available = self._selected_model is None or self._selected_model in models
        status = ProviderHealthStatus.HEALTHY if selected_available and models else ProviderHealthStatus.DEGRADED
        message = (
            "At least one local LLM provider and the selected model are ready"
            if status is ProviderHealthStatus.HEALTHY
            else "No ready local provider advertises the selected model"
        )
        return _result(
            self.provider_name,
            self.component_type,
            status,
            message,
            started,
            selected_resource=self._selected_model,
            available_count=len(models),
        )


class TTSHealthCheck:
    provider_name = "windows-system-speech"
    component_type = ProviderComponentType.TTS

    def __init__(
        self,
        provider: TTSHealthProviderProtocol,
        *,
        selected_voice: str | None = None,
    ) -> None:
        self._provider = provider
        self._selected_voice = selected_voice

    def check(self) -> ProviderHealthResult:
        started = perf_counter()
        if not self._provider.is_ready:
            return _result(
                self.provider_name,
                self.component_type,
                ProviderHealthStatus.DEGRADED,
                "TTS runtime is configured but voices are not loaded",
                started,
                selected_resource=self._selected_voice,
            )
        try:
            voices = self._provider.list_voices()
        except VirgoError as error:
            return _error_result(
                self.provider_name,
                self.component_type,
                started,
                error,
            )
        selected_available = (
            self._selected_voice is None or self._selected_voice in voices
        )
        return _result(
            self.provider_name,
            self.component_type,
            (
                ProviderHealthStatus.HEALTHY
                if selected_available and voices
                else ProviderHealthStatus.DEGRADED
            ),
            (
                "Windows speech runtime and selected voice are ready"
                if selected_available and voices
                else "Windows speech is ready but the selected voice is unavailable"
            ),
            started,
            selected_resource=self._selected_voice,
            available_count=len(voices),
        )


class AudioDeviceHealthCheck:
    provider_name = "sounddevice"

    def __init__(
        self,
        discovery: AudioDeviceDiscoveryService,
        component_type: ProviderComponentType,
    ) -> None:
        if component_type not in (
            ProviderComponentType.AUDIO_INPUT,
            ProviderComponentType.AUDIO_OUTPUT,
        ):
            raise ValueError("audio health requires an input or output component")
        self.component_type = component_type
        self._discovery = discovery

    def check(self) -> ProviderHealthResult:
        started = perf_counter()
        try:
            inventory = self._discovery.discover()
        except VirgoError as error:
            return _error_result(
                self.provider_name,
                self.component_type,
                started,
                error,
            )
        is_input = self.component_type is ProviderComponentType.AUDIO_INPUT
        devices = inventory.input_devices if is_input else inventory.output_devices
        default = inventory.default_input if is_input else inventory.default_output
        return _result(
            self.provider_name,
            self.component_type,
            (
                ProviderHealthStatus.HEALTHY
                if default is not None
                else ProviderHealthStatus.DEGRADED
            ),
            (
                "Default audio device is available"
                if default is not None
                else "No default audio device is available"
            ),
            started,
            selected_resource=None if default is None else default.name,
            available_count=len(devices),
        )


class CallableHealthCheck:
    """Adapt one explicit bounded readiness callable without owning its resource."""

    def __init__(
        self,
        provider_name: str,
        component_type: ProviderComponentType,
        operation: Callable[[], object],
        *,
        expected_result: object = True,
    ) -> None:
        self.provider_name = provider_name
        self.component_type = component_type
        self._operation = operation
        self._expected_result = expected_result

    def check(self) -> ProviderHealthResult:
        started = perf_counter()
        try:
            outcome = self._operation()
        except VirgoError as error:
            return _error_result(
                self.provider_name,
                self.component_type,
                started,
                error,
            )
        ready = outcome == self._expected_result
        return _result(
            self.provider_name,
            self.component_type,
            ProviderHealthStatus.HEALTHY if ready else ProviderHealthStatus.DEGRADED,
            (
                "Component is ready"
                if ready
                else "Component returned an unexpected readiness status"
            ),
            started,
        )


def _result(
    provider_name: str,
    component_type: ProviderComponentType,
    status: ProviderHealthStatus,
    message: str,
    started: float,
    *,
    selected_resource: str | None = None,
    available_count: int | None = None,
) -> ProviderHealthResult:
    return ProviderHealthResult(
        provider_name=provider_name,
        component_type=component_type,
        status=status,
        message=message,
        checked_at=datetime.now(UTC),
        latency_seconds=perf_counter() - started,
        selected_resource=selected_resource,
        available_count=available_count,
    )


def _error_result(
    provider_name: str,
    component_type: ProviderComponentType,
    started: float,
    error: VirgoError,
) -> ProviderHealthResult:
    return ProviderHealthResult(
        provider_name=provider_name,
        component_type=component_type,
        status=ProviderHealthStatus.UNAVAILABLE,
        message=error.user_safe_explanation,
        checked_at=datetime.now(UTC),
        latency_seconds=perf_counter() - started,
        recoverable=error.error_info.recoverable,
        error=error.error_info,
        correlation_id=error.error_info.correlation_id,
    )
