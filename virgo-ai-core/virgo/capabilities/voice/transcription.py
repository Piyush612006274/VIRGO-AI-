"""Bounded synchronous bridge from captured audio chunks to local STT."""

from virgo.contracts.errors import ValidationError
from virgo.contracts.models import (
    AudioChunk,
    STTTask,
    STTTranscriptionRequest,
    STTTranscriptionResult,
)
from virgo.contracts.protocols import STTProviderProtocol

DEFAULT_MAXIMUM_AUDIO_BYTES = 16 * 1_024 * 1_024
SUPPORTED_TRANSCRIPTION_CHANNELS = (1, 2)


class MicrophoneSTTIntegrationService:
    """Accumulate one bounded ordered PCM request and transcribe on flush."""

    def __init__(
        self,
        provider: STTProviderProtocol,
        *,
        maximum_audio_bytes: int = DEFAULT_MAXIMUM_AUDIO_BYTES,
    ) -> None:
        if not isinstance(maximum_audio_bytes, int) or maximum_audio_bytes <= 0:
            raise ValidationError(
                "maximum_audio_bytes must be a positive integer",
                source_module=__name__,
            )
        self._provider = provider
        self._maximum_audio_bytes = maximum_audio_bytes
        self._chunks: list[AudioChunk] = []
        self._buffered_bytes = 0

    @property
    def buffered_chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def buffered_byte_count(self) -> int:
        return self._buffered_bytes

    def add_chunk(self, chunk: AudioChunk) -> None:
        """Validate and append one contiguous captured chunk."""
        if not isinstance(chunk, AudioChunk):
            raise self._validation_error("Expected an AudioChunk")
        if chunk.sample_format != "int16":
            raise self._validation_error("Only int16 PCM chunks are supported")
        if chunk.channels not in SUPPORTED_TRANSCRIPTION_CHANNELS:
            raise self._validation_error("Only mono or stereo chunks are supported")
        if self._chunks:
            previous = self._chunks[-1]
            if chunk.sequence != previous.sequence + 1:
                raise self._validation_error("Audio chunk sequence is not contiguous")
            if chunk.sample_rate != previous.sample_rate:
                raise self._validation_error("Audio chunk sample rates do not match")
            if chunk.channels != previous.channels:
                raise self._validation_error("Audio chunk channel counts do not match")
            if chunk.sample_format != previous.sample_format:
                raise self._validation_error("Audio chunk formats do not match")
        if self._buffered_bytes + chunk.byte_count > self._maximum_audio_bytes:
            raise self._validation_error("Transcription audio buffer is full")
        self._chunks.append(chunk)
        self._buffered_bytes += chunk.byte_count

    def flush(
        self,
        *,
        language_hint: str | None = None,
        task: STTTask = STTTask.TRANSCRIBE,
        correlation_id: str | None = None,
    ) -> STTTranscriptionResult:
        """Create one request, call the existing provider once, and reset."""
        if not self._chunks:
            raise self._validation_error("No audio chunks are buffered")
        first = self._chunks[0]
        try:
            request = STTTranscriptionRequest(
                pcm_bytes=b"".join(chunk.pcm_bytes for chunk in self._chunks),
                sample_rate=first.sample_rate,
                channels=first.channels,
                sample_format=first.sample_format,
                language_hint=language_hint,
                task=task,
                correlation_id=correlation_id,
            )
            return self._provider.transcribe(request)
        except ValueError as error:
            raise ValidationError(
                "Buffered audio could not form a transcription request",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error
        finally:
            self.reset()

    def reset(self) -> None:
        """Discard the current in-memory request explicitly."""
        self._chunks.clear()
        self._buffered_bytes = 0

    @staticmethod
    def _validation_error(message: str) -> ValidationError:
        return ValidationError(message, source_module=__name__)
