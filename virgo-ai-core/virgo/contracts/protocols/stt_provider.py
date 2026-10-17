"""Synchronous speech-to-text provider boundary."""

from typing import Protocol

from virgo.contracts.models import STTTranscriptionRequest, STTTranscriptionResult


class STTProviderProtocol(Protocol):
    """Minimal explicit lifecycle for a local transcription provider."""

    @property
    def is_ready(self) -> bool: ...

    def load(self) -> None: ...

    def transcribe(
        self,
        request: STTTranscriptionRequest,
    ) -> STTTranscriptionResult: ...

    def close(self) -> None: ...
