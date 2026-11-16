"""The keys of the providers measured beside Groq (D-100): one group per account, `elevenlabs`,
`speechmatics`, `cohere`, `soniox`, `openai`, `inworld`, `telnyx`, `humain` and `nabrah`, each
a key inline or in its file, as the `groq` group's (core/settings/groq.py). Every key is
optional: with none, its provider is unavailable, and an adapter asked for it raises a
ConfigurationError naming the setting to set. Groq stays the default and the fallback until a
bake-off and the owner's ruling (D-100). The providers that hear a turn over a WebSocket
(`telnyx`'s HUMAIN engine, `nabrah`) also bound the turn's time and the quiet that ends it."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator

from t2_agentic_voice.core.settings.base import (
    PREFIX,
    Group,
    key,
    read_secret_file,
    setting_name,
    url,
)

# Speechmatics' regions for its batch and streaming endpoints: the EU (eu1) or the US (us1).
SpeechmaticsRegion = Literal["eu", "us"]
# The Telnyx speech-to-text models its adapter takes: HUMAIN's engine on the streaming WebSocket,
# then the two Arabic-capable models of its batch endpoint (its docs, read 2026-11-16).
TelnyxSttModel = Literal["humain/realtime", "deepgram/nova-3", "openai/whisper-large-v3-turbo"]


class ProviderKey(Group):
    """A provider's API key: `api_key`, or `api_key_file` naming a file that holds only the key.
    `GROUP` is the group's name in the settings, which every error names under the prefix."""

    GROUP: ClassVar[str] = ""

    api_key: SecretStr | None = Field(
        default=None,
        description=(
            "The provider's API key; unset, its adapters are unavailable and say so when chosen. "
            "Or give api_key_file instead."
        ),
    )
    api_key_file: Path | None = Field(
        default=None,
        description=(
            "Or the full path of a file outside the repository that holds only the key, so the "
            "key can live outside .env."
        ),
    )

    def resolved_api_key(self, prefix: str = PREFIX) -> SecretStr | None:
        """The key: `api_key` when set, otherwise the contents of `api_key_file` (a byte-order
        mark dropped), with the space around them removed; None when neither holds one (a blank
        value counts as unset). A key file that cannot be read, or a key holding a character no
        key holds, raises ConfigurationError naming the setting it came from under `prefix`,
        never its value or the file's path (as `GroqSettings.resolved_api_key`)."""
        if self.api_key is not None and self.api_key.get_secret_value().strip():
            value = self.api_key.get_secret_value().strip()
            return key(value, setting_name(self.GROUP, "api_key", prefix=prefix))
        if self.api_key_file is None:
            return None
        setting = setting_name(self.GROUP, "api_key_file", prefix=prefix)
        text = read_secret_file(self.api_key_file, setting)
        return None if text is None else key(text, setting)


class ElevenLabsSettings(ProviderKey):
    """ElevenLabs: speech-to-text (Scribe) now, voices later; measured beside Groq (D-100)."""

    GROUP: ClassVar[str] = "elevenlabs"


class SpeechmaticsSettings(ProviderKey):
    """Speechmatics: speech-to-text, its Arabic-English pack; measured beside Groq (D-100)."""

    GROUP: ClassVar[str] = "speechmatics"

    region: SpeechmaticsRegion = Field(
        default="eu",
        description=(
            "Where Speechmatics processes the audio: eu (its eu1 endpoints) or us (us1). eu by "
            "default, the region its data terms were read for (D-100)."
        ),
    )
    job_timeout_s: float = Field(
        default=60.0,
        gt=0,
        le=600,
        allow_inf_nan=False,
        description=(
            "The longest one batch transcription may take, from the job's upload to its "
            "transcript: a batch job queues and polls, so it takes longer than stt.timeout_s "
            "allows one request, and its time is measured, never assumed."
        ),
    )


class CohereSettings(ProviderKey):
    """Cohere: speech-to-text (Transcribe Arabic); measured beside Groq (D-100)."""

    GROUP: ClassVar[str] = "cohere"


class SonioxSettings(ProviderKey):
    """Soniox: speech-to-text, batch and streaming; measured beside Groq (D-100)."""

    GROUP: ClassVar[str] = "soniox"

    job_timeout_s: float = Field(
        default=60.0,
        gt=0,
        le=600,
        allow_inf_nan=False,
        description=(
            "The longest one async transcription may take, from the file's upload to its "
            "transcript: the job queues and polls, so its time is measured, never assumed."
        ),
    )


class OpenAISettings(ProviderKey):
    """OpenAI: a talker and speech-to-text to measure beside Groq (D-100)."""

    GROUP: ClassVar[str] = "openai"

    base_url: str = Field(
        default="https://api.openai.com/v1",
        description=(
            "OpenAI's API address; another only for a regional route OpenAI gives the account. "
            "HTTPS only, since the key travels with every request."
        ),
    )

    @field_validator("base_url")
    @classmethod
    def _https(cls, value: str) -> str:
        parts = urlsplit(url(value, frozenset({"https"})))
        if parts.query or parts.fragment:
            raise ValueError("must hold no query or fragment: the adapter adds its own path")
        return value


class InworldSettings(ProviderKey):
    """Inworld: voices to measure beside Groq's (D-100); the key in the Base64 form the portal
    copies."""

    GROUP: ClassVar[str] = "inworld"


class StreamedTurn(ProviderKey):
    """A provider that hears a turn over its streaming WebSocket: how long one turn may take,
    and the quiet after its last message that ends it when the provider does not close."""

    turn_timeout_s: float = Field(
        default=20.0,
        gt=0,
        le=120,
        allow_inf_nan=False,
        description=(
            "The longest one turn may take over the provider's WebSocket, from the connection "
            "to its last transcript; its time is measured, never assumed."
        ),
    )
    quiet_s: float = Field(
        default=1.5,
        gt=0,
        le=10,
        allow_inf_nan=False,
        description=(
            "Once the turn's audio is sent, how long a quiet socket (no message) means the "
            "provider has said all it heard, when it does not close the socket itself; this "
            "wait is part of the turn's measured time."
        ),
    )


class TelnyxSettings(StreamedTurn):
    """Telnyx: speech-to-text through its engines, HUMAIN's Arabic engine among them; measured
    beside Groq (D-100)."""

    GROUP: ClassVar[str] = "telnyx"

    stt_model: TelnyxSttModel = Field(
        default="humain/realtime",
        description=(
            "The Telnyx speech-to-text model: humain/realtime (HUMAIN's Arabic engine with "
            "Arabic-English code-switching, on Telnyx's streaming WebSocket, the default), or "
            "deepgram/nova-3 or openai/whisper-large-v3-turbo (its batch endpoint)."
        ),
    )


class HumainSettings(ProviderKey):
    """HUMAIN: its own key, kept for its speech, voice and chat APIs once their reference is
    given; no adapter reads it yet (D-100)."""

    GROUP: ClassVar[str] = "humain"


class NabrahSettings(StreamedTurn):
    """Nabrah: Saudi Arabic speech-to-text on its streaming WebSocket; measured beside Groq
    (D-100)."""

    GROUP: ClassVar[str] = "nabrah"
