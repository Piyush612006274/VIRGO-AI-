"""Public local speech-to-text provider foundation."""

from virgo.contracts.models import (
    STTTask,
    STTTranscriptionRequest,
    STTTranscriptionResult,
)
from virgo.contracts.protocols import STTProviderProtocol
from virgo.providers.stt.faster_whisper_provider import (
    FasterWhisperBackendProtocol,
    FasterWhisperProviderConfiguration,
    FasterWhisperSTTProvider,
)

__all__ = (
    "FasterWhisperBackendProtocol",
    "FasterWhisperProviderConfiguration",
    "FasterWhisperSTTProvider",
    "STTProviderProtocol",
    "STTTask",
    "STTTranscriptionRequest",
    "STTTranscriptionResult",
)
