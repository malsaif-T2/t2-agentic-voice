"""The providers a runtime's calls go through (the design's 5.2 and 6.1), and how each call of an
agent that runs the talker gets its talker (plan 006): the composition root's part, since only
api may build an adapter and hand voice what the tools' layer makes (harness.toml [layers]).

- `Providers`: speech-to-text, text-to-speech and the chat model, each an adapter object. A
  setting picks a built-in adapter (`from_settings`: Groq's, D-004), and any other is passed in
  code: `Providers.from_settings(settings).replace(stt=...)`.
- `talkers`: the factory voice's entry point builds each call's talker with (voice/talkers.py):
  the library's `ChatTalker` for the agent, on the chat model, with one tool runner of the
  agent's tools for every call (it holds no call's state), the agent's one action runner when
  it declares actions (api/actions.py opens it; each call's talker reads its own call's record
  from it, which that call's jobs add to), and the call's clock; None for an agent whose calls
  run the echo.
"""

from __future__ import annotations

from dataclasses import dataclass

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.actions.action_runner import ActionRunner
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.actions.tools import Tool
from t2_agentic_voice.agent.talker import ChatTalker, Talker, TalkerCall
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.chat_model import ChatModel
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.talkers import TalkerFactory


@dataclass(frozen=True, kw_only=True)
class Providers:
    """The providers a runtime's calls go through (the design's 5.2): speech-to-text,
    text-to-speech and the chat model the talker writes with, each an adapter object (no chat
    model for a runtime whose agent runs the echo). A setting picks a built-in adapter
    (`from_settings`), and any other is passed in code (the design's 6.1):
    `Providers.from_settings(settings).replace(stt=...)`."""

    stt: SpeechToText
    tts: TextToSpeech
    chat: ChatModel | None = None

    @classmethod
    def from_settings(cls, settings: VoiceSettings) -> Providers:
        """The built-in adapters the settings pick (`stt.provider`, `tts.provider`,
        `llm.provider`: Groq's), built from the settings; built in the runtime's lifespan when
        none are given."""
        from t2_agentic_voice.adapters.groq_chat import GroqChat
        from t2_agentic_voice.adapters.groq_stt import GroqSTT
        from t2_agentic_voice.adapters.groq_tts import GroqTTS

        return cls(
            stt=GroqSTT.from_settings(settings),
            tts=GroqTTS.from_settings(settings),
            chat=GroqChat.from_settings(settings),
        )

    def replace(
        self,
        *,
        stt: SpeechToText | None = None,
        tts: TextToSpeech | None = None,
        chat: ChatModel | None = None,
    ) -> Providers:
        """These providers with each one given in place of its own."""
        return Providers(
            stt=self.stt if stt is None else stt,
            tts=self.tts if tts is None else tts,
            chat=self.chat if chat is None else chat,
        )


def tools_of(agent: VoiceAgent) -> tuple[Tool, ...]:
    """The agent's tools, each the library's `Tool` the runner runs, its actions left to their
    own runner; ConfigurationError for any other."""
    tools = tuple(tool for tool in agent.tools if isinstance(tool, Tool))
    if len(tools) + sum(isinstance(tool, Action) for tool in agent.tools) != len(agent.tools):
        raise ConfigurationError(
            "A tool the agent declares is not one the library runs. FIX: build each with @tool, "
            "Tool.from_function, knowledge_tool or @action."
        )
    return tools


def actions_of(agent: VoiceAgent) -> tuple[Action, ...]:
    """The agent's actions, in order, each carried out by its action runner, never by the tool
    runner."""
    return tuple(tool for tool in agent.tools if isinstance(tool, Action))


def talkers(
    agent: VoiceAgent,
    settings: VoiceSettings,
    chat: ChatModel | None,
    actions: ActionRunner | None = None,
) -> TalkerFactory | None:
    """The factory of each call's talker (the module's docstring), each given `actions`, the
    agent's action runner; None for an agent whose calls run the echo, or when no chat model
    was given (voice's entry point then refuses an agent that runs the talker, saying so)."""
    mode = settings.session.mode_for(instructed=agent.instructed, prefix=settings.prefix)
    if mode != "talker" or chat is None:
        return None
    runner = ToolRunner(tools_of(agent))
    model: ChatModel = chat

    def build(call: TalkerCall, clock: Clock) -> Talker:
        return ChatTalker(
            agent,
            model=model,
            runner=runner,
            settings=settings,
            call=call,
            clock=clock,
            actions=actions,
        )

    return build
