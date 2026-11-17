"""When a turn's one request moves the call to the agent's other language, under
`stt.live_language = "hinted"` (D-115; the owner's request of 2026-11-17: "utilize Elevenlabs
scribe v3 language probability to switch the language seamlessly during a call instead of
sending two requests"). Pure: no IO, no clock.

Each request names the call's current language as a hint and the agent's other languages beside
it (Scribe v3's `secondary_language_codes`, which the provider's documentation says "may be
present in the audio"; voice/stt_requests.py), so one answer gives the words and the language
heard with its probability. `hinted_switch` moves the call when all three hold:

1. the answer's language maps exactly to one of the agent's codes (domain/words.py's
   `heard_code`) and is not the one the request named (`hinted_move`);
2. the turn is a question or request, not a short reply, as D-103's rule reads it for
   `detected` (domain/language_switch.py's `short_reply`): at least two words, not only the
   short replies of either language in either script;
3. the answer's probability is at least the rule's `min_probability`
   (`stt.switch_min_probability`); an answer with none never moves the call.

`hinted_move` is the rule without its third condition, which a measurement reads at every
threshold (run H's Scribe arms).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.language_switch import short_reply
from t2_agentic_voice.domain.words import heard_code


@dataclass(frozen=True, kw_only=True)
class HintRule:
    """When a turn's one request moves a call whose agent speaks `codes`, two or more: an
    answer in another of them heard with a probability of at least `min_probability`."""

    min_probability: float
    codes: tuple[LanguageCode, ...]

    def __post_init__(self) -> None:
        if not 0 < self.min_probability <= 1:
            raise ValueError("min_probability is a probability above 0, at most 1")
        if len(set(self.codes)) < 2:
            raise ValueError("a call moves only between two of the agent's languages or more")

    def others(self, named: str | None) -> tuple[LanguageCode, ...]:
        """The agent's codes but the one `named` maps to (all of them for none): the languages
        a request naming `named` gives beside it."""
        code = heard_code(named)
        return tuple(dict.fromkeys(each for each in self.codes if each != code))


def hinted_move(
    named: str | None, heard: str | None, *, codes: Sequence[LanguageCode], text: str
) -> LanguageCode | None:
    """The code a turn whose request named `named` and heard `text` in `heard` (the answer's
    language, a code or a provider's name of it) moves the call to on its language and words
    alone, conditions 1 and 2 of the module's docstring; None when it does not."""
    code = heard_code(heard)
    if code is None or code not in codes or code == heard_code(named):
        return None
    return None if short_reply(text) else code


def hinted_switch(
    named: str | None,
    heard: str | None,
    probability: float | None,
    *,
    text: str,
    rule: HintRule,
) -> LanguageCode | None:
    """The code the call moves to when its request named `named` and its answer heard `text` in
    `heard` with `probability` (None: the provider gave none); None when nothing moves (the
    module's docstring, all three conditions)."""
    code = hinted_move(named, heard, codes=rule.codes, text=text)
    if code is None or probability is None or probability < rule.min_probability:
        return None
    return code
