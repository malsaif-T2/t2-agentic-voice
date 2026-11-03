"""The words the interruption rule reads (the design's 3.1 and 4.3; plan 005), for each language
by its primary code (`ar` for both Arabic presets, `en`): the caller's stop words, which stop the
agent at once; the words that ask it to pause, which stop it as a stop word does; its repeat
words, which stop it and have it say its last reply again; its listening sounds (`backchannel`),
after which it goes on; and its no words, which a short output never holds
(domain/interruptions.py).

Each language preset reaches its lists (`Language.words`, from `PRESET_WORDS`); an agent's are
its `phrases` (`VoiceAgent(phrases=...)`), the presets' by default (`Phrases.defaults()`), which
a team extends in its declaration (`Phrases.defaults().extend(stop={"ar": [...]})`) or through
the `words` settings group. A word is matched as whole words of a transcript, both in the
canonical normalized form (the rule's own, domain/interruptions.py).

The presets' lists are empty until plan 005's Track A writes them, under the owner's ruling on
the words the golden set's items also hold (plan 005, Q1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.words import LanguageCode, WordLists

# What a team's additions to one kind of list are: words for each language, by its code.
Additions = Mapping[LanguageCode, Sequence[str]] | None
_FIX = (
    "FIX: give each kind's additions as words for each language by its code, `ar` or `en`, "
    'each on one line, as extend(stop={"en": ["..."]}).'
)


class Words(BaseModel):
    """One language's lists, each a tuple of words or phrases as written."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    stop: tuple[str, ...] = ()
    wait: tuple[str, ...] = ()
    repeat: tuple[str, ...] = ()
    backchannel: tuple[str, ...] = ()
    no: tuple[str, ...] = ()


# The kinds of list, in the order `Words` holds them.
WORD_KINDS: tuple[str, ...] = tuple(Words.model_fields)
# Each language preset's lists, by its primary code (`Language.words`).
PRESET_WORDS: Mapping[LanguageCode, Words] = {"ar": Words(), "en": Words()}


class Phrases(BaseModel):
    """The words an agent's interruption rule reads, for every language: each kind's lists by
    language code, read-only (`VoiceAgent.phrases`). `defaults` gives the presets' lists, and
    `extend` adds a team's; `words` gives one language's. Built on its own with values it cannot
    take, it raises pydantic's ValidationError, as a settings group does; `extend` raises a
    ConfigurationError naming the kind."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    stop: WordLists = Field(default_factory=dict, validate_default=True)
    wait: WordLists = Field(default_factory=dict, validate_default=True)
    repeat: WordLists = Field(default_factory=dict, validate_default=True)
    backchannel: WordLists = Field(default_factory=dict, validate_default=True)
    no: WordLists = Field(default_factory=dict, validate_default=True)

    @classmethod
    def defaults(cls) -> Phrases:
        """The language presets' lists (`PRESET_WORDS`), each kind by language code."""
        lists = {
            kind: {code: getattr(words, kind) for code, words in PRESET_WORDS.items()}
            for kind in WORD_KINDS
        }
        return cls.model_validate(lists)

    def extend(
        self,
        *,
        stop: Additions = None,
        wait: Additions = None,
        repeat: Additions = None,
        backchannel: Additions = None,
        no: Additions = None,
    ) -> Phrases:
        """These lists with the words given added, each kind's by language code, after the
        words already there, none added twice."""
        added = dict(zip(WORD_KINDS, (stop, wait, repeat, backchannel, no), strict=True))
        lists: dict[str, dict[str, tuple[str, ...]]] = {}
        for kind in WORD_KINDS:
            held: Mapping[str, tuple[str, ...]] = getattr(self, kind)
            lists[kind] = dict(held)
            for code, words in (added[kind] or {}).items():
                if isinstance(words, str):
                    raise ConfigurationError(
                        f"The agent's words take a list for each language in `{kind}`, not "
                        f"one text. {_FIX}",
                        details={"field": kind},
                    )
                known = lists[kind].get(code, ())
                lists[kind][code] = (*known, *(w for w in dict.fromkeys(words) if w not in known))
        try:
            return type(self).model_validate(lists)
        except ValidationError as error:
            first = error.errors(include_input=False, include_url=False)[0]
        kind = str(first["loc"][0])
        raise ConfigurationError(
            f"The agent's words cannot take what was added to `{kind}`. {_FIX}",
            details={"field": kind},
        )

    def words(self, code: LanguageCode) -> Words:
        """The lists of the language whose primary code is `code` (none for a kind it has
        none of)."""
        return Words.model_validate(
            {kind: getattr(self, kind).get(code, ()) for kind in WORD_KINDS}
        )
