"""Explicit CPU-local faster-whisper transcription provider."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

import numpy as np
import numpy.typing as npt

from virgo.contracts.errors import (
    ModelUnavailableError,
    ProviderUnavailableError,
    ValidationError,
)
from virgo.contracts.models import (
    STTTranscriptionRequest,
    STTTranscriptionResult,
)

PROVIDER_NAME = "faster-whisper"
PROVIDER_SAMPLE_RATE = 16_000


@dataclass(frozen=True, slots=True, kw_only=True)
class FasterWhisperProviderConfiguration:
    """Minimal explicit CPU-local model configuration."""

    model_name: str = "tiny"
    cache_directory: Path | None = None
    cpu_threads: int = 0
    beam_size: int = 5
    temperature: float = 0.0
    condition_on_previous_text: bool = False

    def __post_init__(self) -> None:
        if not self.model_name.strip():
            raise ValueError("model_name must not be empty")
        if not isinstance(self.cpu_threads, int) or self.cpu_threads < 0:
            raise ValueError("cpu_threads must be non-negative")
        if not isinstance(self.beam_size, int) or not 1 <= self.beam_size <= 10:
            raise ValueError("beam_size must be between one and ten")
        if (
            not isinstance(self.temperature, int | float)
            or isinstance(self.temperature, bool)
            or not 0.0 <= self.temperature <= 1.0
        ):
            raise ValueError("temperature must be between zero and one")
        if not isinstance(self.condition_on_previous_text, bool):
            raise ValueError("condition_on_previous_text must be a bool")


class _SegmentProtocol(Protocol):
    text: str


class _TranscriptionInfoProtocol(Protocol):
    language: str
    language_probability: float


class _WhisperModelProtocol(Protocol):
    def transcribe(
        self,
        audio: npt.NDArray[np.float32],
        *,
        language: str | None,
        task: str,
        vad_filter: bool,
        beam_size: int,
        temperature: float,
        condition_on_previous_text: bool,
    ) -> tuple[Iterable[_SegmentProtocol], _TranscriptionInfoProtocol]: ...


class FasterWhisperBackendProtocol(Protocol):
    """Narrow injectable model-construction boundary."""

    def load_model(
        self,
        configuration: FasterWhisperProviderConfiguration,
    ) -> _WhisperModelProtocol: ...


class _FasterWhisperModuleProtocol(Protocol):
    def WhisperModel(self, model_size_or_path: str, **kwargs: object) -> object: ...


class FasterWhisperBackend:
    """Lazy backend adapter; import and model resolution occur only on load."""

    def load_model(
        self,
        configuration: FasterWhisperProviderConfiguration,
    ) -> _WhisperModelProtocol:
        module = cast(
            _FasterWhisperModuleProtocol,
            import_module("faster_whisper"),
        )
        return cast(
            _WhisperModelProtocol,
            module.WhisperModel(
                configuration.model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=configuration.cpu_threads,
                download_root=(
                    str(configuration.cache_directory)
                    if configuration.cache_directory is not None
                    else None
                ),
            ),
        )


class FasterWhisperSTTProvider:
    """Own one explicitly loaded local faster-whisper model."""

    def __init__(
        self,
        configuration: FasterWhisperProviderConfiguration | None = None,
        backend: FasterWhisperBackendProtocol | None = None,
    ) -> None:
        self._configuration = configuration or FasterWhisperProviderConfiguration()
        self._backend = backend or FasterWhisperBackend()
        self._model: _WhisperModelProtocol | None = None

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    @property
    def model_name(self) -> str:
        return self._configuration.model_name

    def load(self) -> None:
        """Explicitly resolve and load the configured local model once."""
        if self._model is not None:
            return
        try:
            self._model = self._backend.load_model(self._configuration)
        except Exception as error:
            raise ModelUnavailableError(
                "Local STT model could not be loaded",
                technical_detail=f"{type(error).__name__}: {error}",
                user_safe_explanation="The local speech model is unavailable.",
                source_module=__name__,
                cause=error,
            ) from error

    def transcribe(
        self,
        request: STTTranscriptionRequest,
    ) -> STTTranscriptionResult:
        """Synchronously transcribe supplied in-memory PCM audio."""
        if not isinstance(request, STTTranscriptionRequest):
            raise ValidationError(
                "Transcription requires an STTTranscriptionRequest",
                source_module=__name__,
            )
        if self._model is None:
            raise ModelUnavailableError(
                "Local STT model is not loaded",
                user_safe_explanation="The local speech model is not ready.",
                source_module=__name__,
            )
        audio = _convert_pcm_to_provider_audio(request)
        try:
            segments, information = self._model.transcribe(
                audio,
                language=request.language_hint,
                task=request.task.value,
                vad_filter=False,
                beam_size=self._configuration.beam_size,
                temperature=float(self._configuration.temperature),
                condition_on_previous_text=(
                    self._configuration.condition_on_previous_text
                ),
            )
            transcript = "".join(segment.text for segment in segments).strip()
            return STTTranscriptionResult(
                transcript=transcript,
                detected_language=(information.language or None),
                language_confidence=information.language_probability,
                duration_seconds=request.duration_seconds,
                provider_name=PROVIDER_NAME,
                model_name=self.model_name,
                correlation_id=request.correlation_id,
            )
        except Exception as error:
            raise ProviderUnavailableError(
                "Local STT transcription failed",
                technical_detail=f"{type(error).__name__}: {error}",
                user_safe_explanation="Speech could not be transcribed locally.",
                source_module=__name__,
                cause=error,
            ) from error

    def close(self) -> None:
        """Release the provider-owned model reference idempotently."""
        self._model = None


def _convert_pcm_to_provider_audio(
    request: STTTranscriptionRequest,
) -> npt.NDArray[np.float32]:
    samples = np.frombuffer(request.pcm_bytes, dtype="<i2").astype(np.float32)
    samples /= 32_768.0
    if request.channels > 1:
        samples = samples.reshape(-1, request.channels).mean(axis=1, dtype=np.float32)
    if request.sample_rate == PROVIDER_SAMPLE_RATE:
        return np.ascontiguousarray(samples, dtype=np.float32)

    source_positions = np.arange(samples.size, dtype=np.float64)
    output_size = max(
        1,
        round(samples.size * PROVIDER_SAMPLE_RATE / request.sample_rate),
    )
    target_positions = np.linspace(
        0,
        max(0, samples.size - 1),
        output_size,
        dtype=np.float64,
    )
    resampled = np.interp(target_positions, source_positions, samples)
    return np.ascontiguousarray(resampled, dtype=np.float32)
