"""Local Windows System.Speech text-to-speech provider."""

from __future__ import annotations

import base64
import binascii
import io
import json
import subprocess
import wave
from pathlib import Path
from time import perf_counter
from typing import Protocol

from virgo.contracts.errors import (
    ModelUnavailableError,
    OperationTimeoutError,
    ProviderUnavailableError,
    ValidationError,
)
from virgo.contracts.models import TTSAudioResult, TTSRequest

DEFAULT_POWERSHELL_PATH = Path(
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)
DEFAULT_SYNTHESIS_TIMEOUT_SECONDS = 60.0
WINDOWS_SPEECH_PROVIDER_NAME = "windows-system-speech"

LIST_VOICES_SCRIPT = """
Add-Type -AssemblyName System.Speech
$synthesizer = [System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $synthesizer.GetInstalledVoices() | ForEach-Object {
        [Console]::Out.WriteLine($_.VoiceInfo.Name)
    }
} finally {
    $synthesizer.Dispose()
}
"""

SYNTHESIZE_SCRIPT = """
Add-Type -AssemblyName System.Speech
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
$synthesizer = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$memory = [System.IO.MemoryStream]::new()
try {
    $synthesizer.SelectVoice([string]$request.voice)
    $synthesizer.Rate = [int]$request.speaking_rate
    $synthesizer.SetOutputToWaveStream($memory)
    $synthesizer.Speak([string]$request.text)
    $synthesizer.SetOutputToNull()
    [Console]::Out.Write([Convert]::ToBase64String($memory.ToArray()))
} finally {
    $memory.Dispose()
    $synthesizer.Dispose()
}
"""


class WindowsSpeechBackendProtocol(Protocol):
    """Injectable boundary around the installed Windows speech runtime."""

    def list_voices(self, timeout_seconds: float) -> tuple[str, ...]: ...

    def synthesize_wav(
        self,
        text: str,
        voice: str,
        speaking_rate: int,
        timeout_seconds: float,
    ) -> bytes: ...


class PowerShellWindowsSpeechBackend:
    """Invoke System.Speech through a hidden, argument-safe local process."""

    def __init__(self, executable: Path = DEFAULT_POWERSHELL_PATH) -> None:
        self._executable = executable

    def list_voices(self, timeout_seconds: float) -> tuple[str, ...]:
        completed = self._run(LIST_VOICES_SCRIPT, None, timeout_seconds)
        return tuple(
            line.strip() for line in completed.stdout.splitlines() if line.strip()
        )

    def synthesize_wav(
        self,
        text: str,
        voice: str,
        speaking_rate: int,
        timeout_seconds: float,
    ) -> bytes:
        payload = json.dumps(
            {"text": text, "voice": voice, "speaking_rate": speaking_rate}
        )
        completed = self._run(SYNTHESIZE_SCRIPT, payload, timeout_seconds)
        return base64.b64decode(completed.stdout.strip(), validate=True)

    def _run(
        self,
        script: str,
        payload: str | None,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(self._executable),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            input=payload,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_seconds,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


class WindowsSpeechTTSProvider:
    """Own one explicitly loaded local Windows speech runtime view."""

    def __init__(
        self,
        backend: WindowsSpeechBackendProtocol | None = None,
        *,
        timeout_seconds: float = DEFAULT_SYNTHESIS_TIMEOUT_SECONDS,
    ) -> None:
        if (
            not isinstance(timeout_seconds, int | float)
            or not 0 < timeout_seconds <= 300
        ):
            raise ValidationError(
                "timeout_seconds must be between zero and 300",
                source_module=__name__,
            )
        self._backend = backend or PowerShellWindowsSpeechBackend()
        self._timeout_seconds = float(timeout_seconds)
        self._voices: tuple[str, ...] = ()

    @property
    def is_ready(self) -> bool:
        return bool(self._voices)

    def load(self) -> None:
        if self.is_ready:
            return
        try:
            voices = self._backend.list_voices(self._timeout_seconds)
        except subprocess.TimeoutExpired as error:
            raise self._timeout_error(
                "Windows speech loading timed out", error
            ) from error
        except Exception as error:
            raise ProviderUnavailableError(
                "Windows speech runtime could not be loaded",
                technical_detail=f"{type(error).__name__}: {error}",
                source_module=__name__,
                cause=error,
            ) from error
        if not voices:
            raise ModelUnavailableError(
                "No installed Windows speech voices are available",
                source_module=__name__,
            )
        self._voices = voices

    def list_voices(self) -> tuple[str, ...]:
        if not self.is_ready:
            raise ModelUnavailableError(
                "Windows speech runtime is not loaded",
                source_module=__name__,
            )
        return self._voices

    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        if not isinstance(request, TTSRequest):
            raise ValidationError(
                "Synthesis requires a TTSRequest",
                source_module=__name__,
            )
        if not self.is_ready:
            raise ModelUnavailableError(
                "Windows speech runtime is not loaded",
                source_module=__name__,
            )
        if request.voice not in self._voices:
            raise ModelUnavailableError(
                "Selected Windows speech voice is not installed",
                technical_detail=f"Unavailable voice: {request.voice}",
                source_module=__name__,
            )
        started_at = perf_counter()
        try:
            wav_bytes = self._backend.synthesize_wav(
                request.text,
                request.voice,
                request.speaking_rate,
                self._timeout_seconds,
            )
            pcm_bytes, sample_rate, channels, frame_count = _parse_pcm_wave(wav_bytes)
            return TTSAudioResult(
                pcm_bytes=pcm_bytes,
                sample_rate=sample_rate,
                channels=channels,
                sample_format="int16",
                frame_count=frame_count,
                provider_name=WINDOWS_SPEECH_PROVIDER_NAME,
                voice=request.voice,
                synthesis_duration_seconds=perf_counter() - started_at,
                correlation_id=request.correlation_id,
            )
        except subprocess.TimeoutExpired as error:
            raise self._timeout_error(
                "Windows speech synthesis timed out", error
            ) from error
        except (ModelUnavailableError, OperationTimeoutError):
            raise
        except Exception as error:
            raise ProviderUnavailableError(
                "Windows speech synthesis failed",
                technical_detail=f"{type(error).__name__}: {error}",
                source_module=__name__,
                cause=error,
            ) from error

    def close(self) -> None:
        self._voices = ()

    @staticmethod
    def _timeout_error(
        message: str,
        error: BaseException,
    ) -> OperationTimeoutError:
        return OperationTimeoutError(
            message,
            technical_detail=f"{type(error).__name__}: {error}",
            source_module=__name__,
            cause=error,
        )


def _parse_pcm_wave(wav_bytes: bytes) -> tuple[bytes, int, int, int]:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wave_file:
            if wave_file.getcomptype() != "NONE" or wave_file.getsampwidth() != 2:
                raise ValueError("speech output must be uncompressed int16 PCM")
            channels = wave_file.getnchannels()
            sample_rate = wave_file.getframerate()
            frame_count = wave_file.getnframes()
            pcm_bytes = wave_file.readframes(frame_count)
    except (EOFError, wave.Error, binascii.Error) as error:
        raise ValueError("speech output is not a valid PCM WAVE stream") from error
    if channels not in (1, 2) or sample_rate <= 0 or frame_count <= 0:
        raise ValueError("speech output contains invalid audio metadata")
    return pcm_bytes, sample_rate, channels, frame_count
