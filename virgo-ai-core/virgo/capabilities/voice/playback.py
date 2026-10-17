"""Explicit synchronous playback of bounded synthesized PCM audio."""

from __future__ import annotations

from importlib import import_module
from typing import Protocol, cast

from virgo.capabilities.voice.discovery import AudioDeviceDiscoveryService
from virgo.contracts.errors import AudioDeviceError, ValidationError
from virgo.contracts.models import AudioDeviceInfo, TTSAudioResult

PLAYBACK_CHUNK_FRAMES = 2_048
SAMPLE_WIDTH_BYTES = 2


class PlaybackStreamProtocol(Protocol):
    def start(self) -> object: ...

    def write(self, data: bytes) -> object: ...

    def stop(self) -> object: ...

    def abort(self) -> object: ...

    def close(self) -> object: ...


class PlaybackBackendProtocol(Protocol):
    def open_output_stream(
        self,
        *,
        device_id: int,
        sample_rate: int,
        channels: int,
        sample_format: str,
    ) -> PlaybackStreamProtocol: ...


class _SoundDeviceModuleProtocol(Protocol):
    def RawOutputStream(self, **kwargs: object) -> PlaybackStreamProtocol: ...


class SoundDevicePlaybackBackend:
    """Lazy sounddevice adapter that opens raw output streams only."""

    def open_output_stream(
        self,
        *,
        device_id: int,
        sample_rate: int,
        channels: int,
        sample_format: str,
    ) -> PlaybackStreamProtocol:
        sounddevice = cast(
            _SoundDeviceModuleProtocol,
            import_module("sounddevice"),
        )
        return sounddevice.RawOutputStream(
            device=device_id,
            samplerate=sample_rate,
            channels=channels,
            dtype=sample_format,
        )


class AudioPlaybackService:
    """Own one explicitly opened output stream during synchronous playback."""

    def __init__(
        self,
        discovery: AudioDeviceDiscoveryService | None = None,
        backend: PlaybackBackendProtocol | None = None,
    ) -> None:
        self._discovery = discovery or AudioDeviceDiscoveryService()
        self._backend = backend or SoundDevicePlaybackBackend()
        self._stream: PlaybackStreamProtocol | None = None
        self._is_playing = False

    @property
    def is_playing(self) -> bool:
        return self._is_playing

    def play(self, audio: TTSAudioResult, *, device_id: int | None = None) -> None:
        if not isinstance(audio, TTSAudioResult):
            raise ValidationError(
                "Playback requires a TTSAudioResult",
                source_module=__name__,
            )
        if self._stream is not None:
            raise AudioDeviceError(
                "Playback is already active",
                source_module=__name__,
            )
        device = self._select_device(device_id)
        if device.output_channels < audio.channels:
            raise AudioDeviceError(
                "Output device does not support the synthesized channel count",
                source_module=__name__,
            )
        try:
            stream = self._backend.open_output_stream(
                device_id=device.device_id,
                sample_rate=audio.sample_rate,
                channels=audio.channels,
                sample_format=audio.sample_format,
            )
            self._stream = stream
            stream.start()
            self._is_playing = True
            chunk_size = PLAYBACK_CHUNK_FRAMES * audio.channels * SAMPLE_WIDTH_BYTES
            for offset in range(0, len(audio.pcm_bytes), chunk_size):
                if self._stream is not stream:
                    break
                stream.write(audio.pcm_bytes[offset : offset + chunk_size])
            if self._stream is stream:
                stream.stop()
        except Exception as error:
            raise AudioDeviceError(
                "Synthesized speech playback failed",
                technical_detail=f"{type(error).__name__}: {error}",
                user_safe_explanation="The selected speaker could not play speech.",
                source_module=__name__,
                cause=error,
            ) from error
        finally:
            if self._stream is not None:
                self._release_stream()

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.abort()
        except Exception as error:
            raise AudioDeviceError(
                "Speech playback could not be stopped",
                technical_detail=f"{type(error).__name__}: {error}",
                source_module=__name__,
                cause=error,
            ) from error
        finally:
            self._release_stream()

    def close(self) -> None:
        self.stop()

    def _select_device(self, device_id: int | None) -> AudioDeviceInfo:
        inventory = self._discovery.discover()
        if device_id is None:
            if inventory.default_output is None:
                raise AudioDeviceError(
                    "No default output device is available",
                    source_module=__name__,
                )
            return inventory.default_output
        if not isinstance(device_id, int) or device_id < 0:
            raise ValidationError(
                "device_id must be a non-negative integer",
                source_module=__name__,
            )
        selected = next(
            (
                device
                for device in inventory.output_devices
                if device.device_id == device_id
            ),
            None,
        )
        if selected is None:
            raise AudioDeviceError(
                "Selected output device is unavailable",
                source_module=__name__,
            )
        return selected

    def _release_stream(self) -> None:
        stream = self._stream
        self._stream = None
        self._is_playing = False
        if stream is not None:
            try:
                stream.close()
            except Exception as error:
                raise AudioDeviceError(
                    "Speech playback stream could not be closed",
                    technical_detail=f"{type(error).__name__}: {error}",
                    source_module=__name__,
                    cause=error,
                ) from error
