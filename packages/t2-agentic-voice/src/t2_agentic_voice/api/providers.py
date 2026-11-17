"""The providers a runtime's calls go through (the design's 5.2 and 6.1): the composition root's
part, since only api may build an adapter (harness.toml [layers]).

- `Providers`: speech-to-text, text-to-speech and the chat model, each an adapter object, and
  the spoken-language classifier under `stt.live_language = "classified"` (D-086). A setting
  picks a built-in adapter (`from_settings`: Groq's, D-004; Silero's or ECAPA's classifier,
  `stt.classifier`), and any other is passed in code:
  `Providers.from_settings(settings).replace(stt=...)`; `each` lists the ones given.
- `stt_kinds`: each speech-to-text provider `stt.provider` names (`SttKind`): its builder, its
  key's group and the models it takes, the one place the dev console's choice reads them from
  (api/stt_choices.py).
- `opened`: the runtime's start of them: each one's close pushed on its stack, and the
  classifier loaded, off the event loop, with the agent's codes, when the calls hear each
  turn's language (an agent of one code runs none); under `stt.live_language = "hinted"` on a
  provider that gives no language probability, a warning, once, that the calls run as
  `session` (D-115).

Each call's talker is built by agent/talker.py's `chat_talkers`, on the chat model here.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import get_args

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.provider_keys import TelnyxSttModel
from t2_agentic_voice.core.settings.stt import SttModel
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.language_classifier import LanguageClassifier
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.domain.turn_language import spoken_codes

log = get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class SttKind:
    """One speech-to-text provider `stt.provider` picks: how its adapter is built from the
    settings (`build`), the settings group that holds its key (`key_group`), the models it
    takes (`models`, as the eval's scorecards name them), and the setting that names its model
    when it takes more than one (`model_setting`, a group and a field; None: its one model,
    always used)."""

    build: Callable[[VoiceSettings], SpeechToText]
    key_group: str
    models: tuple[str, ...]
    model_setting: tuple[str, str] | None = None

    def model_of(self, settings: VoiceSettings) -> str:
        """The model `settings` have this provider use."""
        if self.model_setting is None:
            return self.models[0]
        group, field = self.model_setting
        return str(getattr(getattr(settings, group), field))


def stt_kinds() -> dict[str, SttKind]:
    """Every speech-to-text provider a setting picks, by its `stt.provider` name, Groq's first:
    Groq's Whisper, ElevenLabs' Scribe, Speechmatics' ar_en pack, Cohere's Transcribe Arabic
    and Soniox's stt-async-v6, Telnyx's model (HUMAIN's engine by default) and Nabrah's (D-100).
    The one place that names them: the dev console's choice of provider and model is read from it
    too."""
    from t2_agentic_voice.adapters import (
        cohere_stt,
        elevenlabs_stt,
        nabrah_stt,
        soniox_stt,
        speechmatics_stt,
        telnyx_stt,
    )
    from t2_agentic_voice.adapters.groq_stt import GroqSTT

    return {
        "groq": SttKind(
            build=GroqSTT.from_settings,
            key_group="groq",
            models=get_args(SttModel),
            model_setting=("stt", "model"),
        ),
        "elevenlabs": SttKind(
            build=elevenlabs_stt.ElevenLabsSTT.from_settings,
            key_group="elevenlabs",
            models=(elevenlabs_stt.MODEL,),
        ),
        "speechmatics": SttKind(
            build=speechmatics_stt.SpeechmaticsSTT.from_settings,
            key_group="speechmatics",
            models=(f"{speechmatics_stt.LANGUAGE_PACK}-enhanced",),  # its pack, operating point
        ),
        "cohere": SttKind(
            build=cohere_stt.CohereSTT.from_settings, key_group="cohere", models=(cohere_stt.MODEL,)
        ),
        "soniox": SttKind(
            build=soniox_stt.SonioxSTT.from_settings, key_group="soniox", models=(soniox_stt.MODEL,)
        ),
        "telnyx": SttKind(
            build=telnyx_stt.TelnyxSTT.from_settings,
            key_group="telnyx",
            models=get_args(TelnyxSttModel),
            model_setting=("telnyx", "stt_model"),
        ),
        "nabrah": SttKind(
            build=nabrah_stt.NabrahSTT.from_settings, key_group="nabrah", models=(nabrah_stt.MODEL,)
        ),
    }


@dataclass(frozen=True, kw_only=True)
class Providers:
    """The providers a runtime's calls go through (the design's 5.2): speech-to-text,
    text-to-speech and the chat model the talker writes with, each an adapter object (no chat
    model for a runtime whose agent runs the echo), and the spoken-language classifier (none
    unless `stt.live_language` is `classified`; provisional). A setting picks a built-in adapter
    (`from_settings`), and any other is passed in code (the design's 6.1):
    `Providers.from_settings(settings).replace(stt=...)`."""

    stt: SpeechToText
    tts: TextToSpeech
    chat: ChatModel | None = None
    classifier: LanguageClassifier | None = None

    @classmethod
    def from_settings(cls, settings: VoiceSettings) -> Providers:
        """The built-in adapters the settings pick (`stt.provider`: `speech_to_text`;
        `tts.provider` and `llm.provider`: Groq's; `stt.classifier` under `classified`), built
        from the settings with no IO; built in the runtime's lifespan when none are given."""
        from t2_agentic_voice.adapters.ecapa_language import EcapaLanguage
        from t2_agentic_voice.adapters.groq_chat import GroqChat
        from t2_agentic_voice.adapters.groq_tts import GroqTTS
        from t2_agentic_voice.adapters.silero_language import SileroLanguage

        classifier: LanguageClassifier | None = None
        if settings.stt.live_language == "classified":
            kind = EcapaLanguage if settings.stt.classifier == "ecapa" else SileroLanguage
            classifier = kind.from_settings(settings)
        return cls(
            stt=cls.speech_to_text(settings),
            tts=GroqTTS.from_settings(settings),
            chat=GroqChat.from_settings(settings),
            classifier=classifier,
        )

    @staticmethod
    def speech_to_text(settings: VoiceSettings) -> SpeechToText:
        """The speech-to-text adapter `stt.provider` names (`stt_kinds`), built from the
        settings with no IO. A ConfigurationError naming the key's setting when that provider
        has none set; the eval commands build theirs here too."""
        return stt_kinds()[settings.stt.provider].build(settings)

    def each(self) -> tuple[SpeechToText | TextToSpeech | ChatModel | LanguageClassifier, ...]:
        """Every provider given, in order: speech-to-text, text-to-speech, then the chat model
        and the classifier when given; each closes with its `aclose()`."""
        given = (self.stt, self.tts, self.chat, self.classifier)
        return tuple(provider for provider in given if provider is not None)

    def replace(
        self,
        *,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        chat: ChatModel | None = None,
        classifier: LanguageClassifier | None = None,
    ) -> Providers:
        """These providers with each one given in place of its own."""
        return Providers(
            stt=self.stt if stt is None else stt,
            tts=self.tts if tts is None else tts,
            chat=self.chat if chat is None else chat,
            classifier=self.classifier if classifier is None else classifier,
        )


async def opened(
    providers: Providers, agent: VoiceAgent, settings: VoiceSettings, stack: AsyncExitStack
) -> LanguageClassifier | None:
    """Each provider's close pushed on `stack`, then the classifier the calls hear each turn's
    language with, loaded (the module's docstring); None when they hear none."""
    for provider in providers.each():
        stack.push_async_callback(provider.aclose)
    stt = settings.stt
    if stt.live_language == "hinted" and not stt.hints():
        log.warning("hinted_as_session", provider=stt.provider, reason="no_language_probability")
    codes, classifier = spoken_codes(agent), providers.classifier
    if settings.stt.live_language != "classified" or classifier is None or len(codes) < 2:
        return None
    await classifier.load(codes)
    return classifier
