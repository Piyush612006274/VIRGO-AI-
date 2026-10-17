"""Immutable local text-to-speech contracts."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from virgo.contracts.models.correlation import require_valid_correlation_id

MAXIMUM_TTS_TEXT_LENGTH = 500
SUPPORTED_TTS_SAMPLE_FORMAT = "int16"
TTSRequestDictionary = dict[str, str | int | None]
TTSAudioDictionary = dict[str, str | int | float | None]


class VoiceProfileSource(StrEnum):
    INSTALLED = "installed"
    DEFAULT_FALLBACK = "default_fallback"


class CustomVoiceCapability(StrEnum):
    UNSUPPORTED = "unsupported"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True, slots=True, kw_only=True)
class VoiceProfile:
    profile_id: str
    display_name: str
    provider: str
    provider_voice_id: str
    source: VoiceProfileSource
    language: str | None = None
    active: bool = False
    user_approved: bool = False

    def __post_init__(self) -> None:
        for value, name in (
            (self.profile_id, "profile_id"),
            (self.display_name, "display_name"),
            (self.provider, "provider"),
            (self.provider_voice_id, "provider_voice_id"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if self.language is not None and not self.language.strip():
            raise ValueError("language must be non-empty when supplied")


@dataclass(frozen=True, slots=True, kw_only=True)
class VoiceProfileSelection:
    active: VoiceProfile | None
    profiles: tuple[VoiceProfile, ...]
    custom_voice_capability: CustomVoiceCapability
    fallback_used: bool = False

    def __post_init__(self) -> None:
        if self.active is not None and self.active not in self.profiles:
            raise ValueError("active voice profile must be listed")


@dataclass(frozen=True, slots=True, kw_only=True)
class TTSRequest:
    """One bounded local speech-synthesis request."""

    text: str
    voice: str
    speaking_rate: int = 0
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must not be empty")
        normalized_text = " ".join(self.text.split())
        if len(normalized_text) > MAXIMUM_TTS_TEXT_LENGTH:
            raise ValueError("text exceeds the bounded synthesis limit")
        object.__setattr__(self, "text", normalized_text)
        if not isinstance(self.voice, str) or not self.voice.strip():
            raise ValueError("voice must not be empty")
        object.__setattr__(self, "voice", self.voice.strip())
        if (
            not isinstance(self.speaking_rate, int)
            or not -10 <= self.speaking_rate <= 10
        ):
            raise ValueError("speaking_rate must be between -10 and 10")
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    def to_dict(self) -> TTSRequestDictionary:
        return {
            "text": self.text,
            "voice": self.voice,
            "speaking_rate": self.speaking_rate,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class TTSAudioResult:
    """Validated in-memory PCM synthesized speech."""

    pcm_bytes: bytes
    sample_rate: int
    channels: int
    sample_format: str
    frame_count: int
    provider_name: str
    voice: str
    synthesis_duration_seconds: float | None = None
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.pcm_bytes, bytes) or not self.pcm_bytes:
            raise ValueError("pcm_bytes must contain immutable audio bytes")
        if not isinstance(self.sample_rate, int) or self.sample_rate <= 0:
            raise ValueError("sample_rate must be a positive integer")
        if not isinstance(self.channels, int) or self.channels not in (1, 2):
            raise ValueError("channels must be one or two")
        if self.sample_format != SUPPORTED_TTS_SAMPLE_FORMAT:
            raise ValueError("sample_format must be int16")
        if not isinstance(self.frame_count, int) or self.frame_count <= 0:
            raise ValueError("frame_count must be a positive integer")
        if len(self.pcm_bytes) != self.frame_count * self.channels * 2:
            raise ValueError("pcm_bytes length does not match frame metadata")
        for field_name, value in (
            ("provider_name", self.provider_name),
            ("voice", self.voice),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
        if self.synthesis_duration_seconds is not None and (
            not isfinite(self.synthesis_duration_seconds)
            or self.synthesis_duration_seconds < 0
        ):
            raise ValueError("synthesis_duration_seconds must be non-negative")
        if self.correlation_id is not None:
            require_valid_correlation_id(self.correlation_id)

    @property
    def audio_duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate

    @property
    def byte_count(self) -> int:
        return len(self.pcm_bytes)

    def to_dict(self) -> TTSAudioDictionary:
        """Serialize metadata only; raw PCM is deliberately excluded."""
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_format": self.sample_format,
            "frame_count": self.frame_count,
            "audio_duration_seconds": self.audio_duration_seconds,
            "byte_count": self.byte_count,
            "provider_name": self.provider_name,
            "voice": self.voice,
            "synthesis_duration_seconds": self.synthesis_duration_seconds,
            "correlation_id": self.correlation_id,
        }
