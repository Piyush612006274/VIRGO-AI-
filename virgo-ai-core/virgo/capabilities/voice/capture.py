"""Explicit bounded microphone-capture lifecycle."""

from __future__ import annotations

from collections.abc import Buffer, Callable
from enum import StrEnum
from importlib import import_module
from queue import Empty, Full, Queue
from threading import Event
from time import monotonic_ns
from typing import Protocol, cast

from virgo.contracts.errors import AudioDeviceError
from virgo.contracts.models import AudioChunk, MicrophoneCaptureConfiguration

RawCaptureCallback = Callable[[Buffer, int, object, object], None]


class CaptureLifecycle(StrEnum):
    """Internal lifecycle for one capture service instance."""

    CLOSED = "closed"
    OPEN = "open"
    CAPTURING = "capturing"
    STOPPED = "stopped"
    FAILED = "failed"


class CaptureStreamProtocol(Protocol):
    """Narrow lifecycle surface required from an input stream."""

    def start(self) -> object: ...

    def stop(self) -> object: ...

    def close(self) -> object: ...


class MicrophoneBackendProtocol(Protocol):
    """Backend seam for opening one raw input stream."""

    def open_input_stream(
        self,
        configuration: MicrophoneCaptureConfiguration,
        callback: RawCaptureCallback,
    ) -> CaptureStreamProtocol: ...


class _SoundDeviceModuleProtocol(Protocol):
    def RawInputStream(self, **kwargs: object) -> CaptureStreamProtocol: ...


class SoundDeviceMicrophoneBackend:
    """Lazy sounddevice adapter that opens raw input streams only."""

    def open_input_stream(
        self,
        configuration: MicrophoneCaptureConfiguration,
        callback: RawCaptureCallback,
    ) -> CaptureStreamProtocol:
        sounddevice = cast(
            _SoundDeviceModuleProtocol,
            import_module("sounddevice"),
        )
        return sounddevice.RawInputStream(
            device=configuration.device_id,
            samplerate=configuration.sample_rate,
            channels=configuration.channels,
            blocksize=configuration.block_size,
            dtype=configuration.sample_format,
            callback=callback,
        )


class MicrophoneCaptureService:
    """Own one explicitly controlled microphone stream and bounded chunk queue."""

    def __init__(
        self,
        configuration: MicrophoneCaptureConfiguration,
        backend: MicrophoneBackendProtocol | None = None,
    ) -> None:
        if not isinstance(configuration, MicrophoneCaptureConfiguration):
            raise AudioDeviceError(
                "Microphone capture requires valid configuration",
                source_module=__name__,
            )
        self._configuration = configuration
        self._backend = backend or SoundDeviceMicrophoneBackend()
        self._chunks: Queue[AudioChunk] = Queue(
            maxsize=configuration.maximum_buffered_chunks
        )
        self._stream: CaptureStreamProtocol | None = None
        self._lifecycle = CaptureLifecycle.CLOSED
        self._cancelled = Event()
        self._next_sequence = 0
        self._dropped_chunks = 0
        self._callback_failure: str | None = None

    @property
    def lifecycle(self) -> CaptureLifecycle:
        return self._lifecycle

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def buffered_chunk_count(self) -> int:
        return self._chunks.qsize()

    @property
    def dropped_chunk_count(self) -> int:
        return self._dropped_chunks

    def open(self) -> None:
        """Open but do not start the configured input stream."""
        if self._lifecycle is not CaptureLifecycle.CLOSED:
            raise self._lifecycle_error("Capture stream is already open")
        self._cancelled.clear()
        self._callback_failure = None
        try:
            self._stream = self._backend.open_input_stream(
                self._configuration,
                self._capture_callback,
            )
            self._lifecycle = CaptureLifecycle.OPEN
        except Exception as error:
            self._stream = None
            self._lifecycle = CaptureLifecycle.FAILED
            raise self._backend_error(
                "Microphone stream could not be opened", error
            ) from error

    def start(self) -> None:
        """Start an opened or stopped input stream explicitly."""
        if self._lifecycle not in (CaptureLifecycle.OPEN, CaptureLifecycle.STOPPED):
            raise self._lifecycle_error("Microphone stream must be open before start")
        if self._stream is None:
            raise self._lifecycle_error("Microphone stream is unavailable")
        self._cancelled.clear()
        try:
            self._stream.start()
            self._lifecycle = CaptureLifecycle.CAPTURING
        except Exception as error:
            self._lifecycle = CaptureLifecycle.FAILED
            raise self._backend_error(
                "Microphone stream could not be started", error
            ) from error

    def stop(self) -> None:
        """Stop active capture; repeated calls are harmless."""
        if self._lifecycle in (CaptureLifecycle.CLOSED, CaptureLifecycle.STOPPED):
            return
        if self._lifecycle is CaptureLifecycle.OPEN:
            self._lifecycle = CaptureLifecycle.STOPPED
            return
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._lifecycle = CaptureLifecycle.STOPPED
        except Exception as error:
            self._lifecycle = CaptureLifecycle.FAILED
            raise self._backend_error(
                "Microphone stream could not be stopped", error
            ) from error

    def cancel(self) -> None:
        """Signal cancellation and stop capture without discarding buffered chunks."""
        self._cancelled.set()
        self.stop()

    def close(self) -> None:
        """Reliably release the stream; repeated calls are harmless."""
        if self._lifecycle is CaptureLifecycle.CLOSED and self._stream is None:
            return
        pending_error: AudioDeviceError | None = None
        try:
            if self._lifecycle is CaptureLifecycle.CAPTURING:
                try:
                    self.stop()
                except AudioDeviceError as error:
                    pending_error = error
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception as error:
                    if pending_error is None:
                        pending_error = self._backend_error(
                            "Microphone stream could not be closed",
                            error,
                        )
        finally:
            self._stream = None
            self._lifecycle = CaptureLifecycle.CLOSED
        if pending_error is not None:
            raise pending_error

    def get_chunk(self, timeout: float = 0.0) -> AudioChunk | None:
        """Retrieve one ordered chunk without indefinite blocking."""
        if not isinstance(timeout, int | float) or timeout < 0:
            raise self._lifecycle_error("Chunk timeout must be non-negative")
        self._raise_callback_failure()
        try:
            if timeout == 0:
                return self._chunks.get_nowait()
            return self._chunks.get(timeout=float(timeout))
        except Empty:
            self._raise_callback_failure()
            return None

    def _capture_callback(
        self,
        input_data: Buffer,
        frame_count: int,
        time_info: object,
        status: object,
    ) -> None:
        del time_info
        if self._cancelled.is_set():
            return
        if status:
            self._callback_failure = str(status)
            return
        try:
            chunk = AudioChunk(
                pcm_bytes=bytes(input_data),
                sample_rate=self._configuration.sample_rate,
                channels=self._configuration.channels,
                sample_format=self._configuration.sample_format,
                frame_count=frame_count,
                sequence=self._next_sequence,
                captured_at_ns=monotonic_ns(),
            )
            self._next_sequence += 1
            try:
                self._chunks.put_nowait(chunk)
            except Full:
                try:
                    self._chunks.get_nowait()
                    self._dropped_chunks += 1
                except Empty:
                    pass
                try:
                    self._chunks.put_nowait(chunk)
                except Full:
                    self._dropped_chunks += 1
        except Exception as error:
            self._callback_failure = f"{type(error).__name__}: {error}"

    def _raise_callback_failure(self) -> None:
        if self._callback_failure is not None:
            detail = self._callback_failure
            self._callback_failure = None
            self._lifecycle = CaptureLifecycle.FAILED
            raise AudioDeviceError(
                "Microphone callback failed",
                technical_detail=detail,
                user_safe_explanation="Microphone capture encountered an error.",
                source_module=__name__,
            )

    @staticmethod
    def _backend_error(message: str, error: BaseException) -> AudioDeviceError:
        return AudioDeviceError(
            message,
            technical_detail=f"{type(error).__name__}: {error}",
            user_safe_explanation="The microphone could not be used safely.",
            source_module=__name__,
            cause=error,
        )

    @staticmethod
    def _lifecycle_error(message: str) -> AudioDeviceError:
        return AudioDeviceError(
            message,
            user_safe_explanation="The microphone is not ready for that action.",
            source_module=__name__,
        )
