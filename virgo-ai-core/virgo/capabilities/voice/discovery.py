"""Explicit side-effect-free audio-device discovery service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib import import_module
from typing import Protocol, cast

from virgo.contracts.errors import AudioDeviceError
from virgo.contracts.models import AudioDeviceInfo, AudioDeviceInventory

BackendRecord = Mapping[str, object]
WINDOWS_WASAPI_HOST_API = "Windows WASAPI"


class AudioDeviceBackendProtocol(Protocol):
    """Narrow backend boundary used only for device metadata discovery."""

    def query_devices(self) -> Sequence[BackendRecord]: ...

    def query_host_apis(self) -> Sequence[BackendRecord]: ...

    def query_default_devices(self) -> tuple[int | None, int | None]: ...


class _SoundDeviceDefaultsProtocol(Protocol):
    @property
    def device(self) -> Sequence[object]: ...


class _SoundDeviceModuleProtocol(Protocol):
    default: _SoundDeviceDefaultsProtocol

    def query_devices(self) -> Sequence[BackendRecord]: ...

    def query_hostapis(self) -> Sequence[BackendRecord]: ...


class SoundDeviceBackend:
    """Lazy adapter around sounddevice metadata APIs; never opens a stream."""

    def query_devices(self) -> Sequence[BackendRecord]:
        sounddevice = _load_sounddevice()
        return tuple(dict(device) for device in sounddevice.query_devices())

    def query_host_apis(self) -> Sequence[BackendRecord]:
        sounddevice = _load_sounddevice()
        return tuple(dict(host_api) for host_api in sounddevice.query_hostapis())

    def query_default_devices(self) -> tuple[int | None, int | None]:
        sounddevice = _load_sounddevice()
        defaults = sounddevice.default.device
        default_input = _normalize_default(defaults[0])
        host_apis = sounddevice.query_hostapis()
        return (
            _preferred_input_default(host_apis, default_input),
            _normalize_default(defaults[1]),
        )


class AudioDeviceDiscoveryService:
    """Discover audio-device metadata only when explicitly requested."""

    def __init__(self, backend: AudioDeviceBackendProtocol | None = None) -> None:
        self._backend = backend or SoundDeviceBackend()

    def discover(self) -> AudioDeviceInventory:
        """Return a typed inventory or raise a structured audio error."""
        try:
            devices = self._backend.query_devices()
            host_apis = self._backend.query_host_apis()
            default_input_id, default_output_id = self._backend.query_default_devices()
            parsed_devices = tuple(
                _parse_device(
                    device_id,
                    record,
                    host_apis,
                    default_input_id,
                    default_output_id,
                )
                for device_id, record in enumerate(devices)
            )
        except AudioDeviceError:
            raise
        except Exception as error:
            raise AudioDeviceError(
                "Audio-device discovery failed",
                technical_detail=f"{type(error).__name__}: {error}",
                user_safe_explanation="Audio devices could not be checked safely.",
                source_module=__name__,
                cause=error,
            ) from error

        input_devices = tuple(
            device for device in parsed_devices if device.is_input_capable
        )
        output_devices = tuple(
            device for device in parsed_devices if device.is_output_capable
        )
        return AudioDeviceInventory(
            input_devices=input_devices,
            output_devices=output_devices,
            default_input=next(
                (device for device in input_devices if device.is_default_input),
                None,
            ),
            default_output=next(
                (device for device in output_devices if device.is_default_output),
                None,
            ),
        )


def _parse_device(
    device_id: int,
    record: BackendRecord,
    host_apis: Sequence[BackendRecord],
    default_input_id: int | None,
    default_output_id: int | None,
) -> AudioDeviceInfo:
    name = _required_str(record, "name")
    input_channels = _required_int(record, "max_input_channels")
    output_channels = _required_int(record, "max_output_channels")
    sample_rate = _required_float(record, "default_samplerate")
    host_api_id = _required_int(record, "hostapi")
    if host_api_id >= len(host_apis):
        raise ValueError("hostapi index is outside the backend inventory")
    host_api_name = _required_str(host_apis[host_api_id], "name")
    return AudioDeviceInfo(
        device_id=device_id,
        name=name,
        input_channels=input_channels,
        output_channels=output_channels,
        default_sample_rate=sample_rate,
        host_api_name=host_api_name,
        is_input_capable=input_channels > 0,
        is_output_capable=output_channels > 0,
        is_default_input=device_id == default_input_id,
        is_default_output=device_id == default_output_id,
    )


def _required_str(record: BackendRecord, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_int(record: BackendRecord, key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _required_float(record: BackendRecord, key: str) -> float:
    value = record.get(key)
    if not isinstance(value, int | float):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _normalize_default(value: object) -> int | None:
    if value in (None, -1):
        return None
    if not isinstance(value, int) or value < 0:
        raise ValueError("default device identifier must be a non-negative integer")
    return value


def _preferred_input_default(
    host_apis: Sequence[BackendRecord], fallback: int | None
) -> int | None:
    """Prefer the Windows-native default capture endpoint when available."""
    for host_api in host_apis:
        if host_api.get("name") == WINDOWS_WASAPI_HOST_API:
            preferred = _normalize_default(host_api.get("default_input_device"))
            if preferred is not None:
                return preferred
    return fallback


def _load_sounddevice() -> _SoundDeviceModuleProtocol:
    return cast(_SoundDeviceModuleProtocol, import_module("sounddevice"))
