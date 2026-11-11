"""The agent's voices, as the runtime's start opens them (api/runtime.py; the design's 10.4): the
phrase cache, which has the agent's fixed phrases at hand under `storage.var_dir/<agent
name>/phrases`, declared on the providers' text-to-speech; and, with `tts.cache_clauses` on and
an agent whose calls run the talker (`session.mode_for`, as api/providers.py reads it), the clause
cache over that text-to-speech under `<agent name>/clauses`, opened, its own close pushed on the
runtime's stack. Otherwise the calls get the providers' text-to-speech itself. An echo agent's
calls never have a clause cache: the echo says the caller's words back, and the cache keeps only
what the agent produced (plan 007). The cache never closes the text-to-speech it wraps: the
runtime closes the providers' own, once.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.voice.session.io import PhraseAudio


@dataclass(frozen=True, kw_only=True)
class Voices:
    """What the calls speak with: the phrase audio, the text-to-speech (the clause cache, or the
    providers' own), and the requests the phrase cache sent at the start."""

    phrases: PhraseAudio
    tts: TextToSpeech
    phrase_requests: int


async def open_voices(
    agent: VoiceAgent, settings: VoiceSettings, tts: TextToSpeech, *, stack: AsyncExitStack
) -> Voices:
    """The phrase cache declared on `tts`, then the clause cache over it when the settings and
    the agent call for one (the module's docstring), its close pushed on `stack`."""
    from t2_agentic_voice.adapters.phrase_cache import PhraseCache  # at first use: a test swaps it

    folder = settings.storage.var_dir / agent.name
    phrases = PhraseCache.from_settings(settings, tts, folder=folder / "phrases")
    requests = await phrases.declare(agent)
    spoken = tts
    mode = None
    if settings.tts.cache_clauses:
        mode = settings.session.mode_for(instructed=agent.instructed, prefix=settings.prefix)
    if mode == "talker":
        from t2_agentic_voice.adapters.clause_cache import ClauseCache

        cache = ClauseCache.from_settings(settings, tts, folder=folder / "clauses")
        await cache.open()
        stack.push_async_callback(cache.aclose)
        spoken = cache
    return Voices(phrases=phrases, tts=spoken, phrase_requests=requests)
