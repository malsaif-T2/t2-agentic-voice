"""How voice's entry point gives each call its talker (voice/calls.py; plan 006): the agent's mode
(`session.mode`, `SessionSettings.mode_for`) says whether its calls run the talker, and a call
that does gets one built for it, by the factory the composition root gives (api/providers.py's
`talkers`: the library's `ChatTalker` on the runtime's chat model and the agent's tools, which
voice may not build itself, since it may not import the tools' layer: harness.toml [layers]), on
the call's clock, the one its session runs on. A call of the echo gets none.
"""

from __future__ import annotations

from collections.abc import Callable

from t2_agentic_voice.agent.talker import Talker, TalkerCall
from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.events import CallId
from t2_agentic_voice.core.identity import Caller
from t2_agentic_voice.domain.declaration import Language, VoiceAgent

# What builds one call's talker: given the call (its id, verified caller and language) and the
# clock it runs on.
TalkerFactory = Callable[[TalkerCall, Clock], Talker]


def talks(agent: VoiceAgent, settings: VoiceSettings, factory: TalkerFactory | None) -> bool:
    """Whether `agent`'s calls run the talker; ConfigurationError, naming the setting, when they
    do but no factory builds one (no chat model was given), or when `session.mode` is talker for
    an agent with no instructions."""
    mode = settings.session.mode_for(instructed=agent.instructed, prefix=settings.prefix)
    if mode == "talker" and factory is None:
        raise ConfigurationError(
            f"The agent {agent.name} runs the talker, but no chat model was given. FIX: give the "
            "runtime one (Providers.from_settings(settings), or Providers(..., chat=...)), or set "
            f"{settings.env_name('session', 'mode')}=echo for an audio check."
        )
    return mode == "talker"


def talker_for(
    factory: TalkerFactory | None,
    *,
    call_id: CallId,
    caller: Caller,
    language: Language,
    clock: Clock,
) -> Talker | None:
    """The call's talker, built by `factory` for it; None for a call of the echo (no factory)."""
    if factory is None:
        return None
    return factory(TalkerCall(call_id=call_id, caller=caller, language=language.tag), clock)
