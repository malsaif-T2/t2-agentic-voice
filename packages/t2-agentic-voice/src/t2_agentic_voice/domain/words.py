"""The words the interruption rule reads (the design's 3.1 and 4.3; plan 005), for each language
by its primary code (`ar` for both Arabic presets, `en`): the caller's stop words, which stop the
agent at once; the words that ask it to pause, which stop it as a stop word does; its repeat
words, which stop it and have it say its last reply again; its listening sounds (`backchannel`),
after which it goes on; and its no words, which a short output never holds
(domain/interruptions.py).

Each language preset reaches its lists (`Language.words`, from `PRESET_WORDS`); an agent's are
its `phrases` (`VoiceAgent(phrases=...)`), the presets' by default (`Phrases.defaults()`), which
a team extends in its declaration (`Phrases.defaults().extend(stop={"ar": [...]})`) or through
the `words` settings group. A word is matched as whole words of a transcript, both in the form
the rule compares in (`rule_form`): the canonical normalizer's, after the joiners, direction
marks and no-break spaces pasted text often carries. The presets' lists are written in it; a
team's words are brought to it when compared, so one written with harakat, another alef or a
hidden mark still matches, and one that says nothing in it (only spaces or marks) never does.

The presets' lists are the prototype's (its `voice/rules.py`, lines 28-110, read only: D-010),
under the owner's ruling on the words the golden set's items also hold (plan 005, Q1): the
Arabic words in `ar`, the English ones and the Latin spellings Whisper writes for Arabic
commands in an English call in `en`. Left out: its yes, send, thanks and greeting words (the yes
rule's and the talker's); the words a preset's fixed phrase holds, whose echo would stop the
agent (the notices ask the caller to say a thing again); and the spellings only Whisper writes
for the stop word, which the rule reads only as a whole short utterance, since a sentence may
hold them as other words (domain/interruption_words.py, plan 005's review).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.words import LanguageCode, WordLists
from t2_agentic_voice.domain.text.arabic import normalize_arabic
from t2_agentic_voice.domain.text.invisible import provider_text

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


# Whisper's own name of each of the library's languages, as Groq reports a language it detected
# ("Arabic", "English"), in any case (TD-011).
WHISPER_NAMES: dict[str, LanguageCode] = {"arabic": "ar", "english": "en"}


def heard_code(language: str | None) -> LanguageCode | None:
    """The primary code a transcript's language names, exactly: the code itself or with a region
    ("ar", "en-US"), or Whisper's name of it (`WHISPER_NAMES`), in any case; None for another
    language ("Armenian", "fr") or none (TD-011)."""
    named = (language or "").casefold()
    if named in WHISPER_NAMES:
        return WHISPER_NAMES[named]
    primary = named.split("-", 1)[0]
    return next((code for code in get_args(LanguageCode) if primary == code), None)


def rule_form(text: str) -> str:
    """`text` in the form the interruption rule compares words in: each no-break space a space
    and each joiner and direction mark dropped (`provider_text`), then the canonical normalizer
    (`normalize_arabic`): words separated by one space, none at the ends."""
    return normalize_arabic(provider_text(text))


# The kinds of list, in the order `Words` holds them.
WORD_KINDS: tuple[str, ...] = tuple(Words.model_fields)

# The Arabic lists, both Arabic presets', in the rule's form (teh marbuta written heh, every alef
# bare), with `\u` escapes as the library's tables are; each comment gives the word's sound and
# meaning, then its letters. The prototype's spellings of what Whisper wrote for the owner's
# words (its VOICE_LOG.md, CP0 and CP1) are marked "heard as", as is the one plan 005's run O1
# heard (the registration's amendment (10)).
_ARABIC = Words(
    stop=(
        "\u0648\u0642\u0641",  # wagif, stop (Saudi): waw, qaf, feh
        "\u0648\u0642\u0641\u064a",  # wagfi, stop (to a woman): waw, qaf, feh, yeh
        "\u0627\u0648\u0642\u0641",  # oqaf, stop: alef, waw, qaf, feh
        "\u062a\u0648\u0642\u0641",  # tawaqqaf, stop (MSA): teh, waw, qaf, feh
        "\u0642\u0641",  # qif, stop (MSA): qaf, feh
        "\u062e\u0644\u0627\u0635",  # khalas, enough: khah, lam, alef, sad
    ),
    wait=(
        "\u0644\u062d\u0638\u0647",  # lahza, a moment: lam, hah, zah, heh
        "\u0627\u0646\u062a\u0638\u0631",  # intazir, wait (MSA): alef, noon, teh, zah, reh
    ),
    repeat=(
        "\u0639\u064a\u062f",  # 'eed, repeat (Saudi): ain, yeh, dal
        "\u0627\u0639\u062f",  # a'id, repeat (MSA): alef, ain, dal
        "\u0627\u0639\u064a\u062f",  # a'eed, shall I repeat: alef, ain, yeh, dal
        "\u0639\u064a\u062f\u0647\u0627",  # 'eedha, repeat it: ain, yeh, dal, heh, alef
        "\u0639\u064a\u062f\u0647",  # 'eedah, repeat it: ain, yeh, dal, heh
        "\u0627\u0639\u062f\u0647\u0627",  # a'idha, repeat it (MSA): alef, ain, dal, heh, alef
        "\u0643\u0631\u0631",  # karrir, say again: kaf, reh, reh
        "\u0643\u0631\u0631\u0647\u0627",  # karrirha, say it again: kaf, reh, reh, heh, alef
        "\u0631\u064a\u062a",  # 'eed heard as reet: reh, yeh, teh
        "\u0631\u064a\u062f",  # 'eed heard as reed: reh, yeh, dal
        "\u062a\u0639\u064a\u062f",  # t'eed, (will you) repeat: teh, ain, yeh, dal
        "\u062a\u0639\u064a\u062f\u0647",  # t'eedah, repeat it: teh, ain, yeh, dal, heh
        "\u062a\u0639\u064a\u062f\u0647\u0627",  # t'eedha, repeat it: the same, then alef
        # mumkin t'eed, can you repeat (the rehearsal's): meem, meem, kaf, noon; teh, ain, yeh,
        # dal; then the same with heh, and with heh and alef (repeat it)
        "\u0645\u0645\u0643\u0646 \u062a\u0639\u064a\u062f",
        "\u0645\u0645\u0643\u0646 \u062a\u0639\u064a\u062f\u0647",
        "\u0645\u0645\u0643\u0646 \u062a\u0639\u064a\u062f\u0647\u0627",
    ),
    backchannel=(
        "\u0643\u0645\u0644",  # kammil, go on: kaf, meem, lam
        "\u0643\u0645\u0644\u064a",  # kammili, go on (to a woman): kaf, meem, lam, yeh
        "\u0643\u0627\u0645\u0644",  # kammil heard as kaamil (plan 005's O1): kaf, alef, meem, lam
        "\u062a\u0627\u0628\u0639",  # taabi', continue (MSA): teh, alef, beh, ain
        "\u0627\u0633\u062a\u0645\u0631",  # istamirr, carry on: alef, seen, teh, meem, reh
        "\u062a\u0645\u0627\u0645",  # tamaam, all right: teh, meem, alef, meem
        "\u062a\u0627\u0645\u0627\u0645",  # tamaam heard as taamaam: teh, alef, meem, alef, meem
        "\u062a\u0627\u0645\u0627",  # tamaam heard as taama: teh, alef, meem, alef
        "\u0637\u064a\u0628",  # tayyib, okay: tah, yeh, beh
        "\u0627\u0648\u0643\u064a",  # okay: alef, waw, kaf, yeh
        "\u0627\u0648\u0643\u064a\u0647",  # okay: alef, waw, kaf, yeh, heh
        "\u0627\u0648\u0643",  # ok: alef, waw, kaf
        "\u062d\u0633\u0646\u0627",  # hasanan, all right (MSA): hah, seen, noon, alef
        "\u0632\u064a\u0646",  # zain, good: zain, yeh, noon
        "\u0645\u0627\u0634\u064a",  # maashi, fine: meem, alef, sheen, yeh
        "\u0627\u0647\u0627",  # aha: alef, heh, alef
        "\u0627\u0647",  # ah: alef, heh
        "\u0627\u0645\u0645",  # umm: alef, meem, meem
        "\u0645\u0645",  # mm: meem, meem
        "\u0645\u0645\u0645",  # mmm: meem, meem, meem
        "\u0647\u0645\u0645\u0645",  # hmmm: heh, meem, meem, meem
    ),
    no=(
        "\u0644\u0627",  # la, no: lam, alef
        "\u0644\u0627\u0621",  # laa', no: lam, alef, hamza
        "\u0645\u0648",  # mu, not (Saudi): meem, waw
        "\u0645\u0627",  # ma, not: meem, alef
        "\u0628\u0644\u0627\u0634",  # balaash, never mind: beh, lam, alef, sheen
        "\u0627\u0644\u063a",  # alghi, cancel (MSA): alef, lam, ghain
        "\u0627\u0644\u063a\u0647\u0627",  # alghiha, cancel it: alef, lam, ghain, heh, alef
        "\u0627\u0644\u063a\u064a",  # alghi, cancel (Saudi): alef, lam, ghain, yeh
    ),
)

# The English lists, with the Latin spellings Whisper wrote for the owner's Arabic commands in
# an English call (the prototype's, as above).
_ENGLISH = Words(
    stop=(
        "stop",
        "stopp",
        # wagif (stop), as Whisper wrote it in Latin letters
        "wagif",
        "waagif",
    ),
    # lahza (a moment), as Whisper heard it, among them
    wait=("wait", "lahza", "lahzah", "lhzah", "one moment", "hold on", "a moment"),
    repeat=(
        "repeat",
        "repeat that",
        "repeat it",
        "can you repeat",
        "can you repeat that",
        "can you repeat it",
        "could you repeat",
        "could you repeat that",
        "could you repeat it",
        "can you say that again",
        "come again",
        "read",
        # 'eed (repeat), as Whisper heard it
        "reid",
        "rit",
        "heit",
    ),
    backchannel=(
        "go on",
        "continue",
        "carry on",
        "ok",
        "okay",
        "okey",
        "alright",
        "all right",
        "mhm",
        "mhmm",
        "mm hmm",
        "uh huh",
        "hmm",
        "hm",
        "umm",
        "um",
        # tamaam (all right), as Whisper heard it
        "tama",
        "tamam",
    ),
    no=("no", "not", "don", "dont", "don t", "never", "cancel", "la"),
)

# Each language preset's lists, by its primary code (`Language.words`).
PRESET_WORDS: Mapping[LanguageCode, Words] = {"ar": _ARABIC, "en": _ENGLISH}


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
