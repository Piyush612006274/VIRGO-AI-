"""Public explicit audio-device discovery foundation."""

from virgo.capabilities.voice.capture import (
    CaptureLifecycle,
    CaptureStreamProtocol,
    MicrophoneBackendProtocol,
    MicrophoneCaptureService,
)
from virgo.capabilities.voice.discovery import (
    AudioDeviceBackendProtocol,
    AudioDeviceDiscoveryService,
)
from virgo.capabilities.voice.identity import VoiceIdentityService
from virgo.capabilities.voice.playback import (
    AudioPlaybackService,
    PlaybackBackendProtocol,
    PlaybackStreamProtocol,
)
from virgo.capabilities.voice.transcription import MicrophoneSTTIntegrationService
from virgo.contracts.models import (
    AudioChunk,
    AudioDeviceInfo,
    AudioDeviceInventory,
    MicrophoneCaptureConfiguration,
)

__all__ = (
    "AudioChunk",
    "AudioPlaybackService",
    "AudioDeviceBackendProtocol",
    "AudioDeviceDiscoveryService",
    "AudioDeviceInfo",
    "AudioDeviceInventory",
    "CaptureLifecycle",
    "CaptureStreamProtocol",
    "MicrophoneBackendProtocol",
    "MicrophoneCaptureConfiguration",
    "MicrophoneCaptureService",
    "MicrophoneSTTIntegrationService",
    "VoiceIdentityService",
    "PlaybackBackendProtocol",
    "PlaybackStreamProtocol",
)
