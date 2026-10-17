"""Immutable speech-to-text request and result contracts."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from virgo.contracts.models.correlation import require_valid_correlation_id

SUPPORTED_STT_SAMPLE_FORMAT = "int16"
STTRequestDictionary = dict[str, str | int | float | None]
STTResultDictionary = dict[str, str | float | None]


class STTTask(StrEnum):
    """Supported non-streaming Whisper tasks."""

    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"


@dataclass(frozen=True, slots=True, kw_only=True)
class STTTranscriptionRequest:
    """One immutable in-memory PCM transcription request."""

    pcm_bytes: bytes
    sample_rate: float
    channels: int
    sample_format: str = SUPPORTED_STT_SAMPLE_FORMAT
    language_hint: str | None = None
    task: STTTask = STTTask.TRANSCRIBE
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pcm_bytes, bytes) or not self.pcm_bytes:
            raise ValueError("pcm_bytes must contain immutable audio bytes")
        if (
            not isinstance(self.sample_rate, int | float)
            or not isfinite(self.sample_rate)
            or self.sample_rate <= 0
        ):
            raise ValueError("sample_rate must be a positive finite number")
        if not isinstance(self.channels, int) or self.channels <= 0:
            raise ValueError("channels must be a positive integer")
        if self.sample_format != SUPPORTED_STT_SAMPLE_FORMAT:
            raise ValueError("sample_format must be int16")
        frame_width = self.channels * 2
        if len(self.pcm_bytes) % frame_width != 0:
            raise ValueError("pcm_bytes must contain complete interleaved frames")
        if self.language_hint is not None and not self.language_hint.strip():
            raise ValueError("language_hint must not be empty when provided")
        if not isinstance(self.task, STTTask):
            raise ValueError("task must be an STTTask")
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    @property
    def frame_count(self) -> int:
        return len(self.pcm_bytes) // (self.channels * 2)

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / float(self.sample_rate)

    def to_dict(self) -> STTRequestDictionary:
        """Serialize metadata only; raw PCM is deliberately excluded."""
        return {
            "sample_rate": float(self.sample_rate),
            "channels": self.channels,
            "sample_format": self.sample_format,
            "frame_count": self.frame_count,
            "duration_seconds": self.duration_seconds,
            "language_hint": self.language_hint,
            "task": self.task.value,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class STTTranscriptionResult:
    """Backend-neutral local transcription result."""

    transcript: str
    detected_language: str | None
    language_confidence: float | None
    duration_seconds: float
    provider_name: str
    model_name: str
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.transcript, str):
            raise ValueError("transcript must be a string")
        for field_name, value in (
            ("provider_name", self.provider_name),
            ("model_name", self.model_name),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.detected_language is not None and not self.detected_language.strip():
            raise ValueError("detected_language must not be empty when provided")
        if self.language_confidence is not None and not (
            0.0 <= self.language_confidence <= 1.0
        ):
            raise ValueError("language_confidence must be between zero and one")
        if not isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise ValueError("duration_seconds must be finite and non-negative")
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    def to_dict(self) -> STTResultDictionary:
        return {
            "transcript": self.transcript,
            "detected_language": self.detected_language,
            "language_confidence": self.language_confidence,
            "duration_seconds": self.duration_seconds,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "correlation_id": self.correlation_id,
        }
