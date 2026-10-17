"""Public local Windows text-to-speech provider."""

from virgo.contracts.models import TTSAudioResult, TTSRequest
from virgo.contracts.protocols import TTSProviderProtocol
from virgo.providers.tts.windows_speech_provider import (
    PowerShellWindowsSpeechBackend,
    WindowsSpeechBackendProtocol,
    WindowsSpeechTTSProvider,
)

__all__ = (
    "PowerShellWindowsSpeechBackend",
    "TTSAudioResult",
    "TTSProviderProtocol",
    "TTSRequest",
    "WindowsSpeechBackendProtocol",
    "WindowsSpeechTTSProvider",
)
