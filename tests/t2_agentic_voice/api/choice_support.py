"""What the call choices' tests share (api/call_options.py, choice_menu.py, choice_calls.py,
choices_route.py): an app's offers, made-up keys (inline, and Telnyx's in a file under the
test's folder), settings with `server.call_choices` on, and builders of fake adapters that keep
what each was built with, so no test reaches a provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from t2_agentic_voice.api.call_options import CallOptions, ModelOffer, SttOffer, VoiceOffer
from t2_agentic_voice.api.choice_calls import ChoiceBuilders
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.groq import GroqSettings
from t2_agentic_voice.core.settings.provider_keys import (
    ElevenLabsSettings,
    OpenAISettings,
    TelnyxSettings,
)
from t2_agentic_voice.core.settings.server import ServerSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.core.settings.tts_voices import LanguageTag, TtsVoice, default_voices
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatRequest

from tests.t2_agentic_voice.api.runtime_support import dev_settings
from tests.t2_agentic_voice.fakes import FAKE_FLOW, FakeSpeechToText, FakeTextToSpeech

GROQ_KEY = "gsk_made-up-groq-key-0123456789abcdef"
ELEVEN_KEY = "sk_made-up-elevenlabs-key-0123456789abcdef"
OPENAI_KEY = "sk-made-up-openai-key-0123456789abcdef"
TELNYX_KEY = "KEYmade-up-telnyx-key-0123456789abcdef"
KEY_FILE = "telnyx-made-up.key"
BAYAN: dict[LanguageTag, TtsVoice] = {
    "ar-SA": TtsVoice(model="Telnyx.Bayan", voice="Jasem"),
    "ar": TtsVoice(model="Telnyx.Bayan", voice="Jasem"),
    "en": TtsVoice(model="Telnyx.Bayan", voice="Michael"),
}
OPTIONS = CallOptions(
    stt=(
        SttOffer(id="whisper", provider="groq", model="whisper-large-v3"),
        SttOffer(id="scribe", provider="elevenlabs", model="scribe_v3"),
    ),
    models=(
        ModelOffer(id="gpt-oss-120b", model="openai/gpt-oss-120b", reasoning_effort="medium"),
        ModelOffer(id="gpt-5.5", model="gpt-5.5", reasoning_effort="none"),
    ),
    voices=(
        VoiceOffer(id="orpheus", provider="groq", languages=default_voices("groq")),
        VoiceOffer(id="eleven", provider="elevenlabs", languages=default_voices("elevenlabs")),
        VoiceOffer(id="bayan", provider="telnyx", languages=BAYAN),
    ),
)
# The voices' IDs, which no answer or log line shows.
VOICE_IDS = ("abdullah", "troy", "nhJWWCFdNdusuVUT3x19", "Jasem", "Michael")


def choice_settings(
    tmp_path: Path, *, on: bool = True, keys: bool = True, **groups: Any
) -> VoiceSettings:
    """Settings with the call choices `on`, on Groq's Whisper and Orpheus and gpt-oss-120b
    unless a test names its own; with `keys`, ElevenLabs' and OpenAI's keys inline and
    Telnyx's in a file under `tmp_path`."""
    groups.setdefault("stt", SttSettings(provider="groq"))
    groups.setdefault("tts", TtsSettings(provider="groq"))
    groups.setdefault("groq", GroqSettings(api_key=SecretStr(GROQ_KEY)))
    if keys:
        key_file = tmp_path / KEY_FILE
        tmp_path.mkdir(parents=True, exist_ok=True)
        key_file.write_text(TELNYX_KEY, encoding="utf-8")
        groups.setdefault("elevenlabs", ElevenLabsSettings(api_key=SecretStr(ELEVEN_KEY)))
        groups.setdefault("openai", OpenAISettings(api_key=SecretStr(OPENAI_KEY)))
        groups.setdefault("telnyx", TelnyxSettings(api_key_file=key_file))
    groups.setdefault("server", ServerSettings(call_choices=on))
    return dev_settings(tmp_path, **groups)


class FakeChat:
    """A chat model that is never asked (the tests build calls, not turns); `closed` says
    whether it was closed."""

    data_flow = FAKE_FLOW

    def __init__(self, name: str = "fake-chat") -> None:
        self.name, self.closed = name, False

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        raise AssertionError("no request is sent in these tests")

    async def aclose(self) -> None:
        self.closed = True


class Built:
    """Fake builders of a choice's adapters, each kept with the settings it was built from."""

    def __init__(self) -> None:
        self.stts: list[tuple[VoiceSettings, FakeSpeechToText]] = []
        self.ttss: list[tuple[VoiceSettings, FakeTextToSpeech]] = []
        self.chats: list[tuple[VoiceSettings, FakeChat]] = []
        self.tts_failure: Exception | None = None

    def builders(self) -> ChoiceBuilders:
        return ChoiceBuilders(stt=self._stt, tts=self._tts, chat=self._chat)

    def _stt(self, settings: VoiceSettings) -> FakeSpeechToText:
        stt = FakeSpeechToText()
        self.stts.append((settings, stt))
        return stt

    def _tts(self, settings: VoiceSettings) -> FakeTextToSpeech:
        if self.tts_failure is not None:
            raise self.tts_failure
        tts = FakeTextToSpeech()
        self.ttss.append((settings, tts))
        return tts

    def _chat(self, settings: VoiceSettings) -> FakeChat:
        chat = FakeChat(f"chat-{settings.llm.provider}")
        self.chats.append((settings, chat))
        return chat
