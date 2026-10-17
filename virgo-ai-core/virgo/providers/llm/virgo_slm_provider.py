"""Virgo SLM provider implementing the shared local LLM protocol."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from threading import Event, RLock
from time import perf_counter
from typing import TYPE_CHECKING, Any

from virgo.contracts.errors import (
    ModelUnavailableError,
    ProviderUnavailableError,
    ValidationError,
)
from virgo.contracts.models import LLMRequest, LLMResponse, LLMStreamChunk
from virgo.contracts.protocols import LLMProviderProtocol

if TYPE_CHECKING:
    from virgo_slm.inference.runtime import GenerationConfig, SLMRuntime

VIRGO_SLM_PROVIDER_NAME = "virgo-slm"
DEFAULT_VIRGO_SLM_MODEL = "virgo-slm-103m"
DEFAULT_VIRGO_SLM_ARTIFACT = Path("data/models/virgo-slm")


class VirgoSLMProvider(LLMProviderProtocol):
    """Lazy local provider backed by an operator-supplied SLM artifact.

    The training package is optional at desktop startup. The provider remains
    importable without PyTorch/tokenizers and advertises the model only when a
    valid artifact and its runtime dependencies are present.
    """

    def __init__(
        self,
        artifact_dir: str | Path = DEFAULT_VIRGO_SLM_ARTIFACT,
        *,
        model_name: str = DEFAULT_VIRGO_SLM_MODEL,
        device: str = "auto",
        runtime: SLMRuntime | Any | None = None,
        generation: GenerationConfig | Any | None = None,
    ) -> None:
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValidationError(
                "Virgo SLM model name must not be empty", source_module=__name__
            )
        self._artifact_dir = Path(artifact_dir)
        self._model_name = model_name.strip()
        self._device = device
        self._runtime = runtime
        self._generation = generation
        self._lock = RLock()
        self._closed = False
        self._artifact_checked = runtime is not None

    @property
    def provider_name(self) -> str:
        return VIRGO_SLM_PROVIDER_NAME

    @property
    def artifact_dir(self) -> Path:
        return self._artifact_dir

    @property
    def model_name(self) -> str:
        return self._model_name

    def health_check(self) -> bool:
        """Validate readiness without loading model weights."""
        self._ensure_open()
        with self._lock:
            runtime = self._runtime
        if runtime is not None:
            return bool(runtime.health_check())
        self._validate_runtime_dependencies()
        try:
            self._load_and_validate_artifact()
        except Exception as error:
            raise ProviderUnavailableError(
                "Virgo SLM artifact is not ready",
                technical_detail=str(error),
                source_module=__name__,
            ) from error
        return True

    def list_models(self) -> tuple[str, ...]:
        """Advertise the SLM only when its artifact and runtime are usable."""
        self._ensure_open()
        with self._lock:
            if self._runtime is not None:
                return (self._model_name,)
            if self._artifact_checked:
                return (self._model_name,)

        try:
            self._validate_runtime_dependencies()
            self._load_and_validate_artifact()
        except (
            RuntimeError,
            ImportError,
            ModuleNotFoundError,
            ProviderUnavailableError,
        ):
            return ()

        with self._lock:
            self._artifact_checked = True
        return (self._model_name,)

    def refresh(self) -> None:
        """Invalidate cached readiness so a newly exported artifact is discovered."""
        with self._lock:
            self._artifact_checked = self._runtime is not None

    def generate(self, request: LLMRequest) -> LLMResponse:
        self._validate_request(request)
        self._require_model(request.model)
        started = perf_counter()
        try:
            text = self._get_runtime().generate(
                _prompt(request),
                generation=self._generation_for_request(request),
            )
        except Exception as error:
            raise ProviderUnavailableError(
                "Virgo SLM generation runtime is unavailable",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error
        return LLMResponse(
            text=text or "Virgo SLM returned no text.",
            model=self._model_name,
            provider=VIRGO_SLM_PROVIDER_NAME,
            completed=True,
            generation_duration_seconds=perf_counter() - started,
            correlation_id=request.correlation_id,
        )

    def stream(
        self,
        request: LLMRequest,
        cancellation: Event | None = None,
    ) -> Iterator[LLMStreamChunk]:
        self._validate_request(request)
        self._require_model(request.model)
        try:
            for delta in self._get_runtime().stream(
                _prompt(request),
                generation=self._generation_for_request(request),
                cancellation=cancellation,
            ):
                if cancellation is not None and cancellation.is_set():
                    return
                yield LLMStreamChunk(
                    text_delta=delta,
                    done=False,
                    model=self._model_name,
                    correlation_id=request.correlation_id,
                )
            if cancellation is not None and cancellation.is_set():
                return
            yield LLMStreamChunk(
                text_delta="",
                done=True,
                model=self._model_name,
                correlation_id=request.correlation_id,
            )
        except Exception as error:
            raise ProviderUnavailableError(
                "Virgo SLM streaming runtime is unavailable",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._runtime = None

    def _get_runtime(self) -> SLMRuntime | Any:
        with self._lock:
            if self._runtime is not None:
                return self._runtime
        self._validate_runtime_dependencies()
        try:
            artifact = self._load_and_validate_artifact()
            runtime_type = _get_slm_runtime_type()
            runtime = runtime_type(artifact, device=self._device)
        except RuntimeError:
            raise
        except Exception as error:
            raise RuntimeError(str(error)) from error
        with self._lock:
            if self._runtime is None:
                self._runtime = runtime
            return self._runtime

    def _load_and_validate_artifact(self) -> Any:
        artifact = _load_artifact(self._artifact_dir)
        if artifact.metadata.model_name != self._model_name:
            raise RuntimeError(
                "SLM artifact model name does not match configured provider model: "
                f"{artifact.metadata.model_name!r} != {self._model_name!r}"
            )
        return artifact

    def _generation_for_request(self, request: LLMRequest) -> GenerationConfig | Any:
        runtime_module = _get_runtime_module()
        generation_type = runtime_module.GenerationConfig
        base = self._generation or generation_type()
        max_new = (
            request.max_tokens
            if request.max_tokens is not None
            else base.max_new_tokens
        )
        return generation_type(
            temperature=request.temperature,
            top_k=base.top_k,
            top_p=base.top_p,
            repetition_penalty=base.repetition_penalty,
            max_new_tokens=max_new,
            min_new_tokens=min(base.min_new_tokens, max_new),
        )

    def _validate_request(self, request: LLMRequest) -> None:
        self._ensure_open()
        if not isinstance(request, LLMRequest):
            raise ValidationError(
                "Generation requires an LLMRequest", source_module=__name__
            )

    def _require_model(self, model: str) -> None:
        if model != self._model_name or not self.list_models():
            raise ModelUnavailableError(
                "Selected Virgo SLM model is unavailable",
                technical_detail=(
                    f"Expected {self._model_name!r} at {self._artifact_dir}"
                ),
                source_module=__name__,
            )

    def _validate_runtime_dependencies(self) -> None:
        with self._lock:
            injected_runtime = self._runtime is not None
        if injected_runtime:
            return
        try:
            import torch  # noqa: F401
            import tokenizers  # noqa: F401
            _get_runtime_module()
        except (ImportError, ModuleNotFoundError) as error:
            raise ProviderUnavailableError(
                "Virgo SLM runtime dependencies are not installed",
                technical_detail="Install the virgo_slm runtime extra.",
                source_module=__name__,
                cause=error,
            ) from error

    def _ensure_open(self) -> None:
        if self._closed:
            raise ProviderUnavailableError(
                "Virgo SLM provider is closed", source_module=__name__
            )


def _get_runtime_module() -> Any:
    from virgo_slm import inference as runtime_module

    return runtime_module


def _get_slm_runtime_type() -> type[Any]:
    return _get_runtime_module().SLMRuntime


def _load_artifact(path: Path) -> Any:
    return _get_runtime_module().load_artifact(path)


def _prompt(request: LLMRequest) -> str:
    if request.system_instruction is None:
        return request.prompt
    return (
        f"System:\n{request.system_instruction}\n\n"
        f"User:\n{request.prompt}\n\nAssistant:\n"
    )
