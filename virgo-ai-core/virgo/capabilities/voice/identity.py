"""Voice identity derived only from voices reported by the active provider."""

from hashlib import sha256

from virgo.contracts.errors import ValidationError
from virgo.contracts.models import (
    CustomVoiceCapability,
    VoiceProfile,
    VoiceProfileSelection,
    VoiceProfileSource,
)
from virgo.contracts.protocols import TTSProviderProtocol


class VoiceIdentityService:
    PROVIDER = "windows_speech"

    def __init__(self, provider: TTSProviderProtocol) -> None:
        self._provider = provider

    def resolve(self, selected_voice: str | None = None) -> VoiceProfileSelection:
        voices = self._provider.list_voices()
        if not voices:
            return VoiceProfileSelection(
                active=None,
                profiles=(),
                custom_voice_capability=CustomVoiceCapability.NOT_CONFIGURED,
                fallback_used=selected_voice is not None,
            )
        active_voice = selected_voice if selected_voice in voices else voices[0]
        fallback_used = selected_voice is not None and selected_voice not in voices
        profiles = tuple(
            VoiceProfile(
                profile_id=_profile_id(voice),
                display_name=voice,
                provider=self.PROVIDER,
                provider_voice_id=voice,
                source=(
                    VoiceProfileSource.DEFAULT_FALLBACK
                    if voice == active_voice and fallback_used
                    else VoiceProfileSource.INSTALLED
                ),
                active=voice == active_voice,
                user_approved=voice == selected_voice,
            )
            for voice in voices
        )
        return VoiceProfileSelection(
            active=next(item for item in profiles if item.active),
            profiles=profiles,
            custom_voice_capability=CustomVoiceCapability.UNSUPPORTED,
            fallback_used=fallback_used,
        )

    def select(self, profile_id: str, *, user_approved: bool) -> VoiceProfile:
        if not user_approved:
            raise ValidationError(
                "Voice profile activation requires explicit user confirmation",
                source_module=__name__,
            )
        selection = self.resolve()
        profile = next(
            (item for item in selection.profiles if item.profile_id == profile_id), None
        )
        if profile is None:
            raise ValidationError(
                "Voice profile is unavailable from the configured provider",
                source_module=__name__,
            )
        return VoiceProfile(
            profile_id=profile.profile_id,
            display_name=profile.display_name,
            provider=profile.provider,
            provider_voice_id=profile.provider_voice_id,
            source=profile.source,
            language=profile.language,
            active=True,
            user_approved=True,
        )


def _profile_id(voice: str) -> str:
    digest = sha256(f"{VoiceIdentityService.PROVIDER}:{voice}".encode()).hexdigest()[
        :16
    ]
    return f"voice-{digest}"
