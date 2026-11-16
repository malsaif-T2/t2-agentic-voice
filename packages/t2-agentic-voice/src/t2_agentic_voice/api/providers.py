"""The providers a runtime's calls go through (the design's 5.2 and 6.1): the composition root's
part, since only api may build an adapter (harness.toml [layers]).

- `Providers`: speech-to-text, text-to-speech and the chat model, each an adapter object, and
  the spoken-language classifier under `stt.live_language = "classified"` (D-086). A setting
  picks a built-in adapter (`from_settings`: Groq's, D-004; Silero's or ECAPA's classifier,
  `stt.classifier`), and any other is passed in code:
  `Providers.from_settings(settings).replace(stt=...)`; `each` lists the ones given.
- `opened`: the runtime's start of them: each one's close pushed on its stack, and the
  classifier loaded, off the event loop, with the agent's codes, when the calls hear each
  turn's language (an agent of one code runs none).

Each call's talker is built by agent/talker.py's `chat_talkers`, on the chat model here.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.language_classifier import LanguageClassifier
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.domain.turn_language import spoken_codes


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
        """The speech-to-text adapter `stt.provider` names, built from the settings with no IO:
        Groq's Whisper, ElevenLabs' Scribe or Speechmatics' ar_en pack (D-100). A
        ConfigurationError naming the key's setting when that provider has none set; the eval
        commands build theirs here too."""
        from t2_agentic_voice.adapters.elevenlabs_stt import ElevenLabsSTT
        from t2_agentic_voice.adapters.groq_stt import GroqSTT
        from t2_agentic_voice.adapters.speechmatics_stt import SpeechmaticsSTT

        built: dict[str, Callable[[VoiceSettings], SpeechToText]] = {
            "groq": GroqSTT.from_settings,
            "elevenlabs": ElevenLabsSTT.from_settings,
            "speechmatics": SpeechmaticsSTT.from_settings,
        }
        return built[settings.stt.provider](settings)

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
    codes, classifier = spoken_codes(agent), providers.classifier
    if settings.stt.live_language != "classified" or classifier is None or len(codes) < 2:
        return None
    await classifier.load(codes)
    return classifier
