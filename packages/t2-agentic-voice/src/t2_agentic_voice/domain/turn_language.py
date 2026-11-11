"""The language each turn is sent to speech-to-text in, under `stt.live_language = "classified"`
(plan 007's Block H; Q17 and Q18), as a pure rule. Pure: no IO, no clock.

Whisper writes a turn in the language it is told, so an English question in an Arabic call,
told Arabic, comes back as Arabic sounds. A spoken-language classifier hears the turn's first
`from_s` seconds and gives each of the agent's languages a share
(domain/ports/language_classifier.py). When a turn's request goes, `choose_language` decides,
in this order:

1. **short**: the turn's speech had not reached `from_s` seconds when its request went, so
   nothing was asked;
2. **late**: the classifier was asked and has not answered (the request never waits, Q18);
3. **busy**: the classifier was classifying another turn;
4. **failed**: it raised, or its answer did not parse;
5. **unsure**: its best share is under `min_share`;
6. else **classified**: the language of the best share.

Every case but the last keeps the current language. Only `classified` moves it (`current_after`),
so after an English question the "yes" to its English read-back, too short to classify, goes as
English (Q17). The speech is counted in bytes of the audio held from where the speech detector
heard it begin, never on the clock, and may hold pauses. With no rule (`session`, or an agent of
one language) the current language stands, `session`, whatever any verdict says.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from t2_agentic_voice.core.events import LanguageBy
from t2_agentic_voice.domain.declaration import VoiceAgent
from t2_agentic_voice.domain.ports.language_classifier import LanguageScores

# What a turn's classification gave when its request went: the scores, or none in hand yet
# (`pending`), the classifier busy, or it failed.
type Verdict = LanguageScores | Literal["pending", "busy", "failed"]


@dataclass(frozen=True, kw_only=True)
class LanguageRule:
    """The rule's two numbers (Q20): the seconds of a turn's speech the classifier hears,
    `from_s`, and the best share that moves the language, `min_share`."""

    from_s: float
    min_share: float

    def __post_init__(self) -> None:
        if not self.from_s > 0:
            raise ValueError("from_s is a length of speech above 0 seconds")
        if not 0 < self.min_share <= 1:
            raise ValueError("min_share is a share above 0 and at most 1")


@dataclass(frozen=True, kw_only=True)
class LanguageChoice:
    """The language a turn's request names (None: none, for Whisper to detect) and how it was
    chosen (`by`)."""

    language: str | None
    by: LanguageBy


def choose_language(
    current: str | None, verdict: Verdict, *, speech_s: float, rule: LanguageRule | None
) -> LanguageChoice:
    """The language of a turn whose speech held `speech_s` seconds when its request went, with
    `verdict` in hand, the call's language being `current` (the module's docstring)."""
    if rule is None:
        return LanguageChoice(language=current, by="session")
    if speech_s < rule.from_s:
        return LanguageChoice(language=current, by="short")
    if verdict == "pending":
        return LanguageChoice(language=current, by="late")
    if verdict == "busy" or verdict == "failed":
        return LanguageChoice(language=current, by=verdict)
    code, share = verdict.best
    if share < rule.min_share:
        return LanguageChoice(language=current, by="unsure")
    return LanguageChoice(language=code, by="classified")


def current_after(current: str | None, choice: LanguageChoice) -> str | None:
    """The call's current language once `choice` was made: moved only by `classified`."""
    return choice.language if choice.by == "classified" else current


def spoken_codes(agent: VoiceAgent) -> tuple[str, ...]:
    """The primary codes of the languages `agent` speaks, each once, in its order: what a
    classifier chooses among. An agent of one code runs no classifier."""
    return tuple(dict.fromkeys(language.primary for language in agent.languages))
