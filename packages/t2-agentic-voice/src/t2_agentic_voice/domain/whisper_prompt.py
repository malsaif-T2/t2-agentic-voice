"""The Whisper prompt of a call (the design's 4.3; plan 006's run W, Q17): the words a
speech-to-text request carries so that Whisper writes the agent's product terms, and the caller's
command words, as they should be written. A pure function (`whisper_prompt`), so the live call
sends the same prompt the measurement measured: run W kept its arm W1 (Q23), so every request of
a call carries it (voice/stt_bridge.py's `call_prompts`) unless `stt.send_prompt` is off (GP-18).

**What it holds**, each once, joined with a comma, in this order: the declaration's vocabulary
terms (`VoiceAgent.vocabulary`), then each command word of the call's language as it should be
written (`COMMAND_SPELLINGS`); trimmed in that order to `PROMPT_BYTES` of UTF-8, so the first word
that does not fit and every one after it are left out. Whisper's longest prompt is 224 tokens
(Groq's transcription API); with no tokenizer installed, a prompt is held to as many bytes, since
a token of a byte-level tokenizer is a byte at least.

**The command words** are proper spellings chosen here, never the presets' lists whole
(domain/words.py, domain/interruption_words.py): those also hold what Whisper writes for a command
word over the agent's voice, such as reet for 'eed, wakaif or wughf for wagif, or "stopp", so the
rule catches them; a prompt holding one could make Whisper write it (the owner's Q17). Each
spelling here, in the rule's form (`rule_form`), is one of the presets' stop, wait or repeat words,
written as a transcript should write it: with its hamza and its teh marbuta (oqif, lahza), where
the presets' lists hold the rule's form, a bare alef and a heh. The Arabic is written with `\\u`
escapes, as the library's tables are, each comment giving the word's sound and meaning.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.settings.words import LanguageCode

PROMPT_BYTES: Final = 224

# The command words a prompt adds for a call's language, by its primary code, most needed
# first: the stop words, the wait words, then the repeat words.
COMMAND_SPELLINGS: Final[Mapping[LanguageCode, tuple[str, ...]]] = {
    "ar": (
        "وقف",  # wagif, stop (Saudi)
        "توقف",  # tawaqqaf, stop (MSA)
        "أوقف",  # oqif, stop, with its hamza
        "قف",  # qif, stop (MSA)
        "خلاص",  # khalas, enough
        "لحظة",  # lahza, a moment, with its teh marbuta
        "انتظر",  # intazir, wait (MSA)
        "عيد",  # 'eed, repeat (Saudi)
        "أعد",  # a'id, repeat (MSA), with its hamza
        "كرر",  # karrir, say again
        "ممكن تعيد",  # mumkin t'eed, can you repeat
    ),
    "en": (
        "stop",
        "wait",
        "one moment",
        "hold on",
        "repeat",
        "repeat that",
        "can you repeat that",
        "come again",
    ),
}


class WhisperPrompt(BaseModel):
    """A call's Whisper prompt (the module's docstring): its text, how many words it holds, and
    of how many it could have held (the terms and the command words, each once)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    kept: int = Field(ge=0)
    of: int = Field(ge=0)


def whisper_prompt(terms: Iterable[str], language: LanguageCode) -> WhisperPrompt:
    """The prompt of a call in `language` (its primary code, `ar` or `en`) for an agent whose
    vocabulary holds `terms` (the module's docstring)."""
    candidates = list(dict.fromkeys([*terms, *COMMAND_SPELLINGS[language]]))
    kept: list[str] = []
    for word in candidates:
        if len(", ".join([*kept, word]).encode("utf-8")) > PROMPT_BYTES:
            break
        kept.append(word)
    return WhisperPrompt(text=", ".join(kept), kept=len(kept), of=len(candidates))
