"""What a `poe first-audio` run (`first_audio.py`; plan 006's registration, T) is built from and
on: its parts, each replaceable by a test's fake; its settings, `poe eval`'s with the arm's on
top; the agent its factory gives; the recorded requests it replays; and the settings it
records.
"""

from __future__ import annotations

import argparse
import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from t2_agentic_voice import VoiceAgent, VoiceSettings
from t2_agentic_voice.groq import GroqChat, GroqSTT, GroqTTS
from t2_agentic_voice.ports import ChatModel, SpeechToText, TextToSpeech
from t2_agentic_voice.stores import PhraseCache

from ole5_voice.evals import history, run_settings
from ole5_voice.evals.audio import read_wav
from ole5_voice.evals.first_audio_run import (
    LEAD_S,
    TAIL_S,
    Phrases,
    Prices,
    ReplayFactory,
    not_wired,
)
from ole5_voice.evals.knowledge_set import RECORDED
from ole5_voice.evals.models import Split
from ole5_voice.evals.overlap_card import AppendLine
from ole5_voice.evals.overlap_plan import with_set
from ole5_voice.evals.run_parts import Choice, Parts, Todo, audio_roots, load_plan
from ole5_voice.evals.timing_run import TAGS
from ole5_voice.evals.worktree import refused

# The flags a run needs: its split, agent and arm, every model's settings, its prices and cap.
NEEDED: Final = (
    "split",
    "agent",
    "trim_silence",
    "model",
    "timeout_s",
    "llm_model",
    "llm_reasoning_effort",
    "llm_max_output_tokens",
    "llm_timeout_s",
    "llm_input_tokens",
    "price_per_hour",
    "llm_price_input",
    "llm_price_output",
    "cap_usd",
    "out",
    "note",
)


def phrase_cache(settings: VoiceSettings, tts: TextToSpeech, agent: VoiceAgent) -> Phrases:
    """The phrase cache the runtime would build, kept in the agent's own folder."""
    folder = settings.storage.var_dir / agent.name / "phrases"
    return PhraseCache.from_settings(settings, tts, folder=folder)


@dataclass(frozen=True)
class FirstAudioParts:
    """What a run is built from, each replaceable by a test's fake: the run's `Parts`, the
    speech, voice and chat adapters, the phrase cache, the replay and the history."""

    plan: Parts = field(default_factory=Parts)
    speech_to_text: Callable[[VoiceSettings], SpeechToText] = GroqSTT.from_settings
    text_to_speech: Callable[[VoiceSettings], TextToSpeech] = GroqTTS.from_settings
    chat_model: Callable[[VoiceSettings], ChatModel] = GroqChat.from_settings
    phrases: Callable[[VoiceSettings, TextToSpeech, VoiceAgent], Phrases] = phrase_cache
    replay: ReplayFactory = not_wired
    append_line: AppendLine = history.append_line


def price(text: str) -> tuple[str, float]:
    """An argparse type: `--tts-price MODEL=USD`, per million characters."""
    model, equals, amount = text.partition("=")
    try:
        value = float(amount)
    except ValueError:
        value = -1.0
    if not equals or not model or not value >= 0 or value == float("inf"):
        raise argparse.ArgumentTypeError("give a price as MODEL=USD, per million characters")
    return model, value


def settings_of(args: argparse.Namespace) -> VoiceSettings:
    """The settings `poe eval` loads, untraced, with the arm's from the flags and each `--set`
    on top."""
    namespace = argparse.Namespace(**vars(args), tracing_endpoint=None)
    pinned = [
        ("tts.trim_silence", args.trim_silence == "on"),
        ("llm.model", args.llm_model),
        ("llm.reasoning_effort", args.llm_reasoning_effort),
        ("llm.max_output_tokens", args.llm_max_output_tokens),
        ("llm.timeout_s", args.llm_timeout_s),
    ]
    return with_set(run_settings.load_settings(namespace), [*pinned, *args.set])


def agent_of(text: str, *, tools: bool) -> VoiceAgent:
    """The agent `--agent MODULE:NAME` names, its tools left out unless `tools`; the run's
    refusal for a factory that is not there or gives no talker's agent."""
    module, colon, name = text.partition(":")
    try:
        factory = getattr(importlib.import_module(module), name, None) if colon else None
    except (ImportError, ValueError):  # no such module, or an empty name
        factory = None
    if not callable(factory):
        raise refused("--agent names no factory", "give it as MODULE:NAME, an importable callable")
    agent = factory()
    if not isinstance(agent, VoiceAgent) or not agent.instructed:
        raise refused(
            "--agent's factory gives no agent with instructions, whose calls run the talker",
            "name the app's factory of its talker's agent",
        )
    return agent if tools else agent.model_copy(update={"tools": ()})


def shown(settings: VoiceSettings, args: argparse.Namespace) -> dict[str, str]:
    """Every setting, as `poe eval` records them, with the run's own."""
    namespace = argparse.Namespace(
        language_hint="label",
        max_rpm=args.stt_rpm,
        max_attempts=1,
        variant_timeout_s=0,
        cap_usd=args.cap_usd,
        windows_ms=[],
        smoke_only=args.smoke_only,
    )
    library = run_settings.shown(settings, namespace)
    run = {
        "run.agent": args.agent,
        "run.tools": "none" if args.no_tools else "declared",
        "run.lead_s": str(LEAD_S),
        "run.tail_s": str(TAIL_S),
        "run.stt_rpm": str(args.stt_rpm),
        "run.tts_rpm": str(args.tts_rpm),
        "run.llm_rpm": str(args.llm_rpm),
        "run.llm_input_tokens": str(args.llm_input_tokens),
        "run.cap_usd": str(args.cap_usd),
        "run.smoke_only": str(args.smoke_only).lower(),
    }
    return {k: v for k, v in library.items() if not k.startswith("run.")} | run


def recorded(
    data: Path, split: Split, args: argparse.Namespace, plan: Parts
) -> tuple[str, list[Todo]]:
    """The digest of `split`'s checked variants (`run_parts.load_plan`'s), and those of its
    recorded requests, each with its audio checked."""
    choice = Choice(split=split, roots=audio_roots(args.audio), needs_audio=True)
    loaded = load_plan(data, choice, plan)
    found = [t for t in loaded.todo if RECORDED.match(t.item.id) and t.item.language in TAGS]
    return loaded.digest, found


def prices_of(args: argparse.Namespace, settings: VoiceSettings, voices: Sequence[str]) -> Prices:
    """The run's prices, a voice's from `--tts-price`; refused for a voice with none."""
    given = dict(args.tts_price)
    if unpriced := [model for model in voices if model not in given]:
        raise refused(
            f"--tts-price names no price for {', '.join(unpriced)}",
            "give --tts-price MODEL=USD for each voice the agent speaks in",
        )
    cached = args.llm_price_input if args.llm_price_cached is None else args.llm_price_cached
    return Prices(
        stt_model=settings.stt.model,
        per_hour_usd=args.price_per_hour,
        per_million_chars_usd={model: given[model] for model in voices},
        chat_input_usd=args.llm_price_input,
        chat_cached_usd=cached,
        chat_output_usd=args.llm_price_output,
        chat_input_tokens=args.llm_input_tokens,
        chat_output_tokens=settings.llm.max_output_tokens,
        cap_usd=args.cap_usd,
    )


def seconds_of(todo: Todo) -> float:
    """How long a recording lasts, its segments together."""
    return sum(read_wav(path).seconds for path in todo.request.segments)


def voice_of(settings: VoiceSettings, todo: Todo) -> str:
    """The voice a recording's call is answered in."""
    return settings.tts.languages[TAGS[todo.item.language]].model
