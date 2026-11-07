"""Run W's arms (plan 006's registration, W) as `poe eval`'s options (`run.py`).

- **W1**, `--prompt-agent MODULE:NAME`: each request carries the Whisper prompt of the language it
  is sent in, the one the agent would ship (Q17): the library's `whisper_prompt` (the `languages`
  facade) of the agent's declared vocabulary, its terms then the language's command words as they
  should be written, never a mishearing the presets keep. The agent is built as runs K, S and T
  build theirs (factories.py), its factory given no knowledge base, since only its declaration is
  read: Ole5's is `ole5_voice.agent:talker_agent`, its vocabulary `agent.VOCABULARY`. The log says
  how many words each language's prompt kept. `evals/terms.toml` stays the list term recall is
  scored on, never the prompt's source. **W0**, without it: no prompt.
- **X**, `--language-hint ar`: every variant is sent as Arabic, an English item's too, as an
  Arabic call sends it.

Each is recorded, as `run.prompt` (the factory, the agent's name and version, the digest of the
prompts sent and each one's counts) and `run.language_hint`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

from t2_agentic_voice import VoiceAgent, get_logger
from t2_agentic_voice.languages import WhisperPrompt, whisper_prompt

from ole5_voice.evals.factories import Loader, agent_of, load_factory

PROMPT_LANGUAGES: Final[tuple[Literal["ar", "en"], ...]] = ("ar", "en")  # the codes sent
log = get_logger(__name__)


def prompts_of(agent: VoiceAgent) -> dict[str, WhisperPrompt]:
    """The Whisper prompt of each language a request is sent in, for `agent`'s vocabulary."""
    return {code: whisper_prompt(agent.vocabulary.terms, code) for code in PROMPT_LANGUAGES}


@dataclass(frozen=True)
class AnswerOptions:
    """Run W's arms as the `groq` answerer takes them: the language every request goes in
    (None: the item's), each language's prompt, and how the run records them (`run.prompt`)."""

    language: str | None = None
    prompts: Mapping[str, str] = field(default_factory=dict)
    shown: str = "none"


def answer_options(args: argparse.Namespace, load: Loader = load_factory) -> AnswerOptions:
    """The arms `--language-hint ar` and `--prompt-agent` choose; the run's refusal, before
    anything is sent, for an agent factory that is not there or gives no agent."""
    language = "ar" if args.language_hint == "ar" else None
    spec: str | None = args.prompt_agent
    if spec is None:
        return AnswerOptions(language=language)
    agent = agent_of(load, spec, None)
    prompts = prompts_of(agent)
    for code, prompt in prompts.items():
        log.info("whisper_prompt", language=code, words_kept=prompt.kept, of=prompt.of)
    texts = {code: prompt.text for code, prompt in prompts.items() if prompt.text}
    digest = hashlib.sha256(json.dumps(texts, sort_keys=True).encode("utf-8")).hexdigest()
    counts = ", ".join(f"{code} {p.kept} of {p.of} words" for code, p in prompts.items())
    named = f"{spec} ({agent.name} {agent.version or 'unversioned'})"
    return AnswerOptions(language, texts, f"{named}, sha256 {digest[:16]}, {counts}")
