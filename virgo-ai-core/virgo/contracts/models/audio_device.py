"""Immutable audio-device discovery contracts."""

from dataclasses import dataclass
from math import isfinite

AudioDeviceDictionary = dict[str, str | int | float | bool | None]
AudioInventoryDictionary = dict[
    str,
    list[AudioDeviceDictionary] | AudioDeviceDictionary | None,
]


@dataclass(frozen=True, slots=True)
class AudioDeviceInfo:
    """Backend-neutral information about one audio device."""

    device_id: int
    name: str
    input_channels: int
    output_channels: int
    default_sample_rate: float
    host_api_name: str
    is_input_capable: bool
    is_output_capable: bool
    is_default_input: bool = False
    is_default_output: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.device_id, int) or self.device_id < 0:
            raise ValueError("device_id must be a non-negative integer")
        for field_name, string_value in (
            ("name", self.name),
            ("host_api_name", self.host_api_name),
        ):
            if not isinstance(string_value, str) or not string_value.strip():
                raise ValueError(f"{field_name} must not be empty")
        for field_name, channel_count in (
            ("input_channels", self.input_channels),
            ("output_channels", self.output_channels),
        ):
            if not isinstance(channel_count, int) or channel_count < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if (
            not isinstance(self.default_sample_rate, int | float)
            or not isfinite(self.default_sample_rate)
            or self.default_sample_rate <= 0
        ):
            raise ValueError("default_sample_rate must be a positive finite number")
        if self.is_input_capable != (self.input_channels > 0):
            raise ValueError("is_input_capable must match input_channels")
        if self.is_output_capable != (self.output_channels > 0):
            raise ValueError("is_output_capable must match output_channels")
        if self.is_default_input and not self.is_input_capable:
            raise ValueError("default input device must be input capable")
        if self.is_default_output and not self.is_output_capable:
            raise ValueError("default output device must be output capable")

    def to_dict(self) -> AudioDeviceDictionary:
        """Serialize only declared backend-neutral values."""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "input_channels": self.input_channels,
            "output_channels": self.output_channels,
            "default_sample_rate": float(self.default_sample_rate),
            "host_api_name": self.host_api_name,
            "is_input_capable": self.is_input_capable,
            "is_output_capable": self.is_output_capable,
            "is_default_input": self.is_default_input,
            "is_default_output": self.is_default_output,
        }


@dataclass(frozen=True, slots=True)
class AudioDeviceInventory:
    """One immutable snapshot of available input and output devices."""

    input_devices: tuple[AudioDeviceInfo, ...] = ()
    output_devices: tuple[AudioDeviceInfo, ...] = ()
    default_input: AudioDeviceInfo | None = None
    default_output: AudioDeviceInfo | None = None

    def __post_init__(self) -> None:
        if (
            self.default_input is not None
            and self.default_input not in self.input_devices
        ):
            raise ValueError("default_input must exist in input_devices")
        if (
            self.default_output is not None
            and self.default_output not in self.output_devices
        ):
            raise ValueError("default_output must exist in output_devices")

    def to_dict(self) -> AudioInventoryDictionary:
        """Serialize the inventory without backend objects or live handles."""
        return {
            "input_devices": [device.to_dict() for device in self.input_devices],
            "output_devices": [device.to_dict() for device in self.output_devices],
            "default_input": (
                self.default_input.to_dict() if self.default_input is not None else None
            ),
            "default_output": (
                self.default_output.to_dict()
                if self.default_output is not None
                else None
            ),
        }
