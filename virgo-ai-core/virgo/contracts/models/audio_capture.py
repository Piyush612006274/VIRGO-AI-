"""Immutable microphone-capture contracts."""

from dataclasses import dataclass

SUPPORTED_CAPTURE_FORMATS: dict[str, int] = {
    "int16": 2,
    "int24": 3,
    "int32": 4,
    "float32": 4,
}

AudioChunkDictionary = dict[str, str | int | float]
CaptureConfigurationDictionary = dict[str, str | int | float]


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """One immutable ordered block of raw interleaved PCM audio."""

    pcm_bytes: bytes
    sample_rate: float
    channels: int
    sample_format: str
    frame_count: int
    sequence: int
    captured_at_ns: int

    def __post_init__(self) -> None:
        if not isinstance(self.pcm_bytes, bytes):
            raise ValueError("pcm_bytes must be immutable bytes")
        if not isinstance(self.sample_rate, int | float) or self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if not isinstance(self.channels, int) or self.channels <= 0:
            raise ValueError("channels must be positive")
        if self.sample_format not in SUPPORTED_CAPTURE_FORMATS:
            raise ValueError("sample_format is unsupported")
        if not isinstance(self.frame_count, int) or self.frame_count <= 0:
            raise ValueError("frame_count must be positive")
        if not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if not isinstance(self.captured_at_ns, int) or self.captured_at_ns <= 0:
            raise ValueError("captured_at_ns must be positive")
        expected_bytes = (
            self.frame_count
            * self.channels
            * SUPPORTED_CAPTURE_FORMATS[self.sample_format]
        )
        if len(self.pcm_bytes) != expected_bytes:
            raise ValueError("pcm_bytes length does not match frame metadata")

    @property
    def byte_count(self) -> int:
        """Return the immutable payload size without exposing it in serialization."""
        return len(self.pcm_bytes)

    def to_dict(self) -> AudioChunkDictionary:
        """Serialize metadata only; raw PCM content is deliberately excluded."""
        return {
            "sample_rate": float(self.sample_rate),
            "channels": self.channels,
            "sample_format": self.sample_format,
            "frame_count": self.frame_count,
            "sequence": self.sequence,
            "captured_at_ns": self.captured_at_ns,
            "byte_count": self.byte_count,
        }


@dataclass(frozen=True, slots=True)
class MicrophoneCaptureConfiguration:
    """Minimal explicit configuration for one microphone stream."""

    device_id: int
    sample_rate: float
    channels: int = 1
    block_size: int = 1_024
    sample_format: str = "int16"
    maximum_buffered_chunks: int = 32

    def __post_init__(self) -> None:
        if not isinstance(self.device_id, int) or self.device_id < 0:
            raise ValueError("device_id must be a non-negative integer")
        if not isinstance(self.sample_rate, int | float) or self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        for field_name, value in (
            ("channels", self.channels),
            ("block_size", self.block_size),
            ("maximum_buffered_chunks", self.maximum_buffered_chunks),
        ):
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.sample_format not in SUPPORTED_CAPTURE_FORMATS:
            raise ValueError("sample_format is unsupported")

    @property
    def sample_width(self) -> int:
        """Return bytes per sample for the configured raw PCM format."""
        return SUPPORTED_CAPTURE_FORMATS[self.sample_format]

    def to_dict(self) -> CaptureConfigurationDictionary:
        """Serialize declared configuration without backend state."""
        return {
            "device_id": self.device_id,
            "sample_rate": float(self.sample_rate),
            "channels": self.channels,
            "block_size": self.block_size,
            "sample_format": self.sample_format,
            "maximum_buffered_chunks": self.maximum_buffered_chunks,
        }
