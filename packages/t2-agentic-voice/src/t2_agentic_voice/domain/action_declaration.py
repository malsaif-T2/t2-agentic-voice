"""What a team writes for the words of an action (the design's 4.4 and 6.4): `Say`, the template
of a sentence in each language; `ReadBack`, the read-back and how it is confirmed; `Claims`, the
past-tense phrases that claim the action; and `Spoken`, how each fixed value is said.

**A template's keys.** A text is keyed by a language tag, `ar-SA`, `ar` or `en`. A language
is covered by a text of its own tag or of its primary code: an `ar` text covers both Arabic
presets unless `ar-SA` has its own, and an `ar-SA` text never covers `ar`. The declaration
refuses an agent with a language none of an action's texts covers, and never one with a text
of a tag it does not speak. A text is read in its own tag first, then the other Arabic one
(`read_in`): so an `ar-SA` agent's action may give an `ar` text, MSA, beside its `ar-SA` one,
which a reply to a caller who speaks MSA reads (agent/language.py's `wording`), and its
`ar-SA` text when it has none. Word lists (`send_words`) key by the primary code, as the
presets' do.

**A placeholder** is `{field}`, or `{field:id}` to say it digit by digit, and names a field of
the draft or, in `done`, of the result. A fixed value is said through its `Spoken` label.

**A read-back** is a pair for each language, a summary and a closing question, written apart
because the receipt covers only the summary. `show_draft` is False by default: the caller only
hears the agent (D-075).

Each class is frozen in practice and checks itself as it is built: anything it cannot run with
is a ConfigurationError naming the field, with a FIX line, and never the value it refused.
"""

from __future__ import annotations

import string
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast, final, get_args

from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import LanguageCode
from t2_agentic_voice.domain.text.invisible import holds_refused_character, provider_text

_TAGS: frozenset[str] = frozenset(get_args(LanguageTag))
_CODES: frozenset[str] = frozenset(get_args(LanguageCode))
# The format a placeholder may ask for: none, or said digit by digit.
_DIGIT_BY_DIGIT = "id"
_KEYS_FIX = 'key each text by a language tag, as {"ar-SA": "...", "en": "..."}'
_LINE_FIX = "give each one on one line of plain text, with no unseen character"
_BRACES_FIX = 'write each placeholder as {field} or {field:id}, and a brace itself as "{{"'
_CLAIMS_FIX = 'give each language a list, as {"ar-SA": ["..."], "en": ["..."]}'


def refused(field: str, what: str, fix: str) -> ConfigurationError:
    """The ConfigurationError for an action's `field`, naming no value it refused."""
    return ConfigurationError(
        f"An action cannot take its `{field}`: {what}. FIX: {fix}.", details={"field": field}
    )


def _primary(tag: LanguageTag) -> LanguageCode:
    return "en" if tag == "en" else "ar"


def _covers(keys: Collection[str], tag: LanguageTag) -> bool:
    return tag in keys or _primary(tag) in keys


def read_in(tag: LanguageTag) -> tuple[LanguageTag, ...]:
    """The keys a text is read by in `tag`, in order: its own, then the other Arabic tag."""
    return ("en",) if tag == "en" else (tag, "ar" if tag == "ar-SA" else "ar-SA")


def _text_for[T](texts: Mapping[LanguageTag, T], tag: LanguageTag) -> T:
    """The text `tag` reads (the module's docstring); KeyError for a language none is read
    in."""
    return texts[next((key for key in read_in(tag) if key in texts), tag)]


def _tag(field: str, key: object) -> LanguageTag:
    if key not in _TAGS:
        raise refused(field, "a text is keyed by something other than a language tag", _KEYS_FIX)
    return cast(LanguageTag, key)


def _line(field: str, value: object) -> str:
    """`value` when it is a text a call can say: one line, nothing unseen, saying something."""
    if (
        not isinstance(value, str)
        or holds_refused_character(value)
        or not provider_text(value).strip()
    ):
        raise refused(field, "a text in it is not one line of plain words", _LINE_FIX)
    return value


def _placeholders(field: str, template: str) -> frozenset[str]:
    """The fields `template` names, refusing a placeholder this library cannot fill."""
    try:
        parts = list(string.Formatter().parse(template))
    except ValueError:
        raise refused(
            field, "a template has a brace that opens or closes nothing", _BRACES_FIX
        ) from None
    named: set[str] = set()
    for _, name, spec, conversion in parts:
        if name is None:
            continue
        if not name.isidentifier() or conversion or spec not in ("", _DIGIT_BY_DIGIT):
            raise refused(field, "a placeholder is not a field name alone", _BRACES_FIX)
        named.add(name)
    return frozenset(named)


@final
@dataclass(frozen=True, init=False, eq=False)
class Say:
    """A sentence in each language: `Say({"ar-SA": ..., "en": ...})`, or the keyword form,
    `Say(ar=..., ar_SA=..., en=...)`, for the same mapping."""

    templates: Mapping[LanguageTag, str]

    def __init__(
        self,
        templates: Mapping[str, str] | None = None,
        /,
        *,
        ar: str | None = None,
        ar_SA: str | None = None,  # noqa: N803 - the tag's own spelling
        en: str | None = None,
    ) -> None:
        given = {"ar": ar, "ar-SA": ar_SA, "en": en}
        if templates is not None and not isinstance(templates, Mapping):
            raise refused("Say", "it is not a map of texts by language", _KEYS_FIX)
        merged = {
            **(templates or {}),
            **{key: text for key, text in given.items() if text is not None},
        }
        if not merged:
            raise refused("Say", "it holds no text", _KEYS_FIX)
        kept = {_tag("Say", key): _line("Say", text) for key, text in merged.items()}
        for text in kept.values():
            _placeholders("Say", text)
        object.__setattr__(self, "templates", MappingProxyType(kept))

    def covers(self, tag: LanguageTag) -> bool:
        """Whether a language `tag` has a text here."""
        return _covers(self.templates, tag)

    def for_language(self, tag: LanguageTag) -> str:
        """The template `tag` reads; KeyError for a language none covers."""
        return _text_for(self.templates, tag)

    @property
    def placeholders(self) -> frozenset[str]:
        """Every field any of its texts names."""
        return frozenset().union(*(_placeholders("Say", t) for t in self.templates.values()))


@final
@dataclass(frozen=True, init=False, eq=False)
class ReadBack:
    """How an action is read back: for each language a pair, the summary and the closing
    question; the action's own `send_words`, added to the preset's for the yes rule, by primary
    code; `max_attempts`, how many times an unclear answer is asked; `show_draft`, whether a
    card of the draft is shown, off by default (D-075); and `asked_again`, the line for that,
    the library's own unless given."""

    templates: Mapping[LanguageTag, tuple[str, str]]
    send_words: Mapping[LanguageCode, tuple[str, ...]]
    max_attempts: int
    show_draft: bool
    asked_again: Say | None

    def __init__(
        self,
        templates: Mapping[str, tuple[str, str] | Sequence[str]],
        /,
        *,
        send_words: Mapping[str, Sequence[str]] | None = None,
        max_attempts: int = 2,
        show_draft: bool = False,
        asked_again: Say | None = None,
    ) -> None:
        if not isinstance(templates, Mapping):
            raise refused("read_back", "it is not a map of texts by language", _KEYS_FIX)
        pairs: dict[LanguageTag, tuple[str, str]] = {}
        for key, pair in templates.items():
            if isinstance(pair, str) or len(pair) != 2:
                raise refused(
                    "read_back",
                    "a language's text is not a pair of a summary and a closing question",
                    'give each language ("the summary", "the closing question")',
                )
            summary, question = _line("read_back", pair[0]), _line("read_back", pair[1])
            _placeholders("read_back", summary)
            _placeholders("read_back", question)
            pairs[_tag("read_back", key)] = (summary, question)
        if not pairs:
            raise refused("read_back", "it holds no text", _KEYS_FIX)
        if type(max_attempts) is not int or max_attempts < 1:
            raise refused("max_attempts", "it is not a whole number of 1 or more", "give it one")
        words: dict[LanguageCode, tuple[str, ...]] = {}
        for code, listed in (send_words or {}).items():
            if code not in _CODES or isinstance(listed, str):
                raise refused(
                    "send_words",
                    "it is not a list of words for each language by its code",
                    'give it as {"ar": ["..."], "en": ["..."]}',
                )
            words[cast(LanguageCode, code)] = tuple(_line("send_words", word) for word in listed)
        object.__setattr__(self, "templates", MappingProxyType(pairs))
        object.__setattr__(self, "send_words", MappingProxyType(words))
        object.__setattr__(self, "max_attempts", max_attempts)
        object.__setattr__(self, "show_draft", show_draft)
        object.__setattr__(self, "asked_again", asked_again)

    def covers(self, tag: LanguageTag) -> bool:
        """Whether a language `tag` has a pair here."""
        return _covers(self.templates, tag)

    def for_language(self, tag: LanguageTag) -> tuple[str, str]:
        """The summary and the closing question `tag` reads; KeyError for one none covers."""
        return _text_for(self.templates, tag)

    @property
    def placeholders(self) -> frozenset[str]:
        """Every field its summaries and closing questions name."""
        named = [_placeholders("read_back", text) for p in self.templates.values() for text in p]
        return frozenset().union(*named)


@final
@dataclass(frozen=True, init=False, eq=False)
class Claims:
    """The past-tense phrases that claim an action, for each language: `Claims({"ar-SA":
    ["..."], "en": ["..."]})`. The output guard blocks each unless the record holds the action
    or a `reports_on` tool returned it."""

    phrases: Mapping[LanguageTag, tuple[str, ...]]

    def __init__(self, phrases: Mapping[str, Sequence[str]], /) -> None:
        if not isinstance(phrases, Mapping):
            raise refused("claims", "it is not a map of phrases by language", _CLAIMS_FIX)
        kept: dict[LanguageTag, tuple[str, ...]] = {}
        for key, listed in phrases.items():
            if isinstance(listed, str) or not listed:
                raise refused("claims", "a language's phrases are not a list of them", _CLAIMS_FIX)
            kept[_tag("claims", key)] = tuple(_line("claims", phrase) for phrase in listed)
        if not kept:
            raise refused("claims", "it holds no phrase", _CLAIMS_FIX)
        object.__setattr__(self, "phrases", MappingProxyType(kept))

    def covers(self, tag: LanguageTag) -> bool:
        """Whether a language `tag` has phrases here."""
        return _covers(self.phrases, tag)

    def for_language(self, tag: LanguageTag) -> tuple[str, ...]:
        """The phrases `tag` reads; KeyError for a language none covers."""
        return _text_for(self.phrases, tag)


@final
@dataclass(frozen=True, init=False, eq=False)
class Spoken:
    """How each fixed value of a draft's field is said, put on the field's type:
    `Annotated[Literal["hardware"], Spoken({"hardware": {"ar": "..."}})]`, a label read as a
    text is (`read_in`). A language with no label says the value as it is written."""

    labels: Mapping[str, Mapping[LanguageTag, str]]

    def __init__(self, labels: Mapping[str, Mapping[str, str]], /) -> None:
        if not isinstance(labels, Mapping) or not labels:
            raise refused("Spoken", "it holds no value's label", _KEYS_FIX)
        kept: dict[str, Mapping[LanguageTag, str]] = {}
        for value, said in labels.items():
            if not isinstance(said, Mapping):
                raise refused("Spoken", "a value's labels are not by language", _KEYS_FIX)
            kept[value] = MappingProxyType(
                {_tag("Spoken", key): _line("Spoken", text) for key, text in said.items()}
            )
        object.__setattr__(self, "labels", MappingProxyType(kept))

    def label(self, value: str, tag: LanguageTag) -> str | None:
        """How `tag` says `value`; None when it has no label for it."""
        said = self.labels.get(value, {})
        return next((said[key] for key in read_in(tag) if key in said), None)
