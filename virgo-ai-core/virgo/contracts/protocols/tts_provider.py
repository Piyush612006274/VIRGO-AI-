"""Synchronous local text-to-speech provider boundary."""

from typing import Protocol

from virgo.contracts.models import TTSAudioResult, TTSRequest


class TTSProviderProtocol(Protocol):
    """Minimal explicit lifecycle for one local TTS provider."""

    @property
    def is_ready(self) -> bool: ...

    def load(self) -> None: ...

    def list_voices(self) -> tuple[str, ...]: ...

    def synthesize(self, request: TTSRequest) -> TTSAudioResult: ...

    def close(self) -> None: ...
