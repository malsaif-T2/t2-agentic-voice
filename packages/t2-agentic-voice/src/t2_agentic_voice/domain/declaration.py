"""The declaration of a use case: the agent a team declares and the languages its calls are held
in (the design's 4.3 and 5.2), frozen, with no IO.

An agent has a name, its languages, its pronunciation map and the words its interruption rule
reads (`phrases`, domain/words.py). With no instructions, the voice session answers in echo mode
(`session.mode`): each turn is said back, after a fixed frame in the turn's language,
«سمعتك تقول: …» or "I heard: …" (plan 003, Q3), so an echo agent stays a team's first audio
check. The talker's parts, all optional (domain/talker_declaration.py), are its instructions,
its tools, its vocabulary and its version; an agent that declares instructions runs the talker
(plan 006). Each language is built from its preset, which gives it its tag, its frame and a text
for each notice the caller may be told; the team gives its greeting, the phrase that opens a
call, and may give its own notices and the progress lines its tools name. The phrases a call
speaks as written (domain/fixed_phrases.py) are synthesized once, at the runtime's start, and
played from the phrase cache.

A phrase (a greeting, the frame, a notice, a spoken form) says something, on one line, and holds
no character a reader cannot see but the no-break spaces, the joiners and the direction marks
that pasted text often carries (domain/text/invisible.py). A declaration the library cannot run
with is a ConfigurationError naming the field, with a FIX line (the design's 4.2), and never the
value it refused, however it is built: through a preset, the constructor, `model_validate` or
`model_validate_json` (a text that is not JSON included), and on a subclass of `Language` too;
only assigning to a built agent or language raises pydantic's ValidationError, as for every
frozen model. How it fails, and each field's FIX, is declaration_errors.py's.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Literal, Self, final, get_args

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    PlainValidator,
    ValidationInfo,
    field_validator,
)

from t2_agentic_voice.core.settings.base import FROZEN, PLAIN
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration_errors import FROM_PRESET, Declared
from t2_agentic_voice.domain.presets import ECHO_FRAMES, NOTICES
from t2_agentic_voice.domain.talker_declaration import (
    DeclaredTool,
    Instructions,
    ProgressKey,
    Vocabulary,
    a_tool,
    a_vocabulary,
    instructions_for,
    tools_for,
)
from t2_agentic_voice.domain.text.invisible import holds_refused_character, provider_text
from t2_agentic_voice.domain.words import PRESET_WORDS, Phrases, Words

# A notice's kind (the design's 5.5), each told in the call's language: `busy`, a call that
# cannot be taken, which admission control answers at join, before a call has audio (the
# design's 10.5); `error`, a turn or an echo that failed; `ended`, a call the session ends
# itself, at a limit (plan 003, Q4); `cut_off`, a reply that failed after the caller heard some
# of it (D-077). The session sends all but `busy` as `t2v/1`'s `notice`, whose text the client
# shows, and speaks each as a reply (voice/session/call.py).
NoticeKind = Literal["busy", "error", "cut_off", "ended"]
NOTICE_KINDS: tuple[NoticeKind, ...] = get_args(NoticeKind)
# The notices a call speaks, so the phrase cache holds them: `busy` comes before any call.
SPOKEN_NOTICES: tuple[NoticeKind, ...] = ("error", "cut_off", "ended")

# An agent's name: it names the agent's folder under `storage.var_dir` and its traces, so it is
# a lowercase word, with hyphens.
AGENT_NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")
# The names Windows keeps for its devices, which no folder can take (CPython 3.12's `pathlib`
# lists the same, `_WIN_RESERVED_NAMES`); the owner develops on Windows (plan 003's review).
_DEVICES = frozenset(
    {"con", "prn", "aux", "nul", *(f"{port}{n}" for port in ("com", "lpt") for n in range(1, 10))}
)
# A pronunciation names a language by its primary code, which both Arabic tags share.
_CODES = ("ar", "en")

# What a phrase may not hold, said whole, since the team cannot see the character it means.
_UNSEEN = (
    "a text in it holds a control or format character, a line or paragraph separator, a lone "
    "surrogate or a space other than U+0020; of these, a phrase may hold only the no-break "
    "spaces U+00A0 and U+202F, the joiners U+200C and U+200D and the direction marks U+200E, "
    "U+200F and U+061C"
)


def _phrase(value: str) -> str:
    """`value`, when it holds no character a spoken phrase may not (domain/text/invisible.py)
    and says something once a provider's text is made of it; the error never repeats the
    value."""
    if holds_refused_character(value):
        raise ValueError(_UNSEEN)
    if not provider_text(value).strip():
        raise ValueError("a text in it says nothing: it is empty, or only spaces and marks")
    return value


def _form(value: str) -> str:
    """`value` as a written form to look for: a phrase with no space at either end, which would
    keep it from ever standing as whole words."""
    _phrase(value)
    if value != value.strip():
        raise ValueError(
            "a written form starts or ends with a space, so it never stands as whole words"
        )
    return value


def _code(value: str) -> str:
    """`value` when it is a primary language code a pronunciation is keyed by."""
    if value not in _CODES:
        raise ValueError("a pronunciation names its language `ar` (both Arabic presets) or `en`")
    return value


def _every_kind[T](value: Mapping[NoticeKind, T]) -> Mapping[NoticeKind, T]:
    """`value` when it has a text for every kind of notice."""
    missing = [kind for kind in NOTICE_KINDS if kind not in value]
    if missing:
        *rest, last = missing
        listed = f"{', '.join(rest)} or {last}" if rest else last
        raise ValueError(
            f"it has no text for {listed}; each of busy, error, cut_off and ended needs one"
        )
    return value


def _a_language(value: object) -> object:
    """`value` when it may be a `Language`: one built, or the fields of one."""
    if not isinstance(value, Language | Mapping):
        raise ValueError("an item is not a language")
    return value


_Phrase = Annotated[str, AfterValidator(_phrase)]
# A pronunciation: how each language says one written form.
_Said = Annotated[
    Mapping[Annotated[str, AfterValidator(_code)], _Phrase], Field(min_length=1), FROZEN, PLAIN
]
# A pronunciation map as `VoiceAgent.pronounce` holds it: the languages facade's
# `Pronunciations`, each entry checked and kept read-only.
_Pronunciations = Annotated[Mapping[Annotated[str, AfterValidator(_form)], _Said], FROZEN, PLAIN]


class Language(Declared):
    """One language a call can be held in: its `tag` (`ar-SA` Saudi Arabic, `ar` Modern Standard
    Arabic, `en` English), the `greeting` the agent opens a call with in it, the `echo_frame`
    the echo says before the words it heard, its `notices`, the text of each kind of notice
    (`NoticeKind`) the caller is told in it, and its `progress` lines, the text of each line a
    tool names by its key (`Tool(progress=...)`), spoken when the tool runs long (none by
    default). Build one with its preset: `Language.saudi_arabic(greeting=...)`,
    `Language.arabic(...)` or `Language.english(...)`, which gives the tag, the frame and each
    notice's text in the language's register (plan 003, Q5: Saudi for `ar-SA`, Modern Standard
    Arabic for `ar`); a team's own `notices` replace the kinds they name. Each tag is spoken in
    the model and voice `tts.languages` gives it."""

    tag: LanguageTag
    greeting: _Phrase
    echo_frame: _Phrase
    notices: Annotated[Mapping[NoticeKind, _Phrase], AfterValidator(_every_kind), FROZEN, PLAIN]
    progress: Annotated[Mapping[ProgressKey, _Phrase], FROZEN, PLAIN] = Field(
        default_factory=dict, validate_default=True
    )

    @classmethod
    def saudi_arabic(
        cls,
        *,
        greeting: str,
        notices: Mapping[NoticeKind, str] | None = None,
        progress: Mapping[str, str] | None = None,
    ) -> Self:
        """Saudi Arabic (`ar-SA`), opening each call with `greeting`; `notices` replaces the
        preset's text of each kind it names; `progress` gives the tools' progress lines."""
        return cls._preset("ar-SA", greeting, notices, progress)

    @classmethod
    def arabic(
        cls,
        *,
        greeting: str,
        notices: Mapping[NoticeKind, str] | None = None,
        progress: Mapping[str, str] | None = None,
    ) -> Self:
        """Modern Standard Arabic (`ar`), opening each call with `greeting`; `notices` replaces
        the preset's text of each kind it names; `progress` gives the tools' progress lines."""
        return cls._preset("ar", greeting, notices, progress)

    @classmethod
    def english(
        cls,
        *,
        greeting: str,
        notices: Mapping[NoticeKind, str] | None = None,
        progress: Mapping[str, str] | None = None,
    ) -> Self:
        """English (`en`), opening each call with `greeting`; `notices` replaces the preset's
        text of each kind it names; `progress` gives the tools' progress lines."""
        return cls._preset("en", greeting, notices, progress)

    @classmethod
    def _preset(cls, tag: LanguageTag, greeting: str, notices: object, progress: object) -> Self:
        texts: object = notices if notices is not None else NOTICES[tag]
        if isinstance(notices, Mapping):
            texts = {**NOTICES[tag], **notices}
        fields: dict[str, object] = {"tag": tag, "greeting": greeting}
        fields |= {"echo_frame": ECHO_FRAMES[tag], "notices": texts, "progress": progress or {}}
        return cls.model_validate(fields, context=FROM_PRESET)

    @property
    def primary(self) -> Literal["ar", "en"]:
        """The tag's primary language, the code a speech-to-text provider is told (`ar` for
        both Arabic presets)."""
        return "en" if self.tag == "en" else "ar"

    @property
    def words(self) -> Words:
        """The preset's word lists for its primary language (domain/words.py): what the agent's
        `phrases` start from, before a team's additions."""
        return PRESET_WORDS[self.primary]


@final
class VoiceAgent(Declared):
    """A use case, as a team declares it: its `name`; the `languages` its calls are held in, the
    first a call's when nothing picks another (`call_language`); and `pronounce`, its
    pronunciation map (the design's 4.3): each written form, as a text holds it, to how each
    language says it, keyed by the language's primary code (`ar` for both Arabic presets, `en`),
    as `pronounce={"LT-": {"ar": ..., "en": "L T"}}`, which the `languages` facade's
    `pronounce` applies; and `phrases`, the words its interruption rule reads
    (domain/words.py), the presets' unless the team extends them. The talker's parts, each
    optional (domain/talker_declaration.py): `instructions`, one text, or one per language tag
    for every language it speaks; `tools`, each name once, each progress line in every
    language, an action's texts in every language too; `vocabulary`, the product terms for the
    Whisper prompt; `version`, stamped on its traces; and `ask_on_uncertain_overlaps`, whether a
    chat model decides the short overlaps of two or more words the rule would let go on (D-069;
    False, so an agent that does not ask for it, and any test script, sees no new request). It
    runs the talker when it declares
    instructions (`instructed`). Frozen, with no IO; built once and handed to the runtime."""

    name: str
    # Given as any sequence (a list, as the design writes it), kept as a tuple.
    languages: Sequence[Annotated[Language, BeforeValidator(_a_language)]]
    pronounce: _Pronunciations = Field(default_factory=dict, validate_default=True)
    phrases: Phrases = Field(default_factory=Phrases.defaults)
    instructions: Instructions | None = None
    tools: Sequence[Annotated[DeclaredTool, PlainValidator(a_tool)]] = ()
    vocabulary: Annotated[Vocabulary, BeforeValidator(a_vocabulary)] = Vocabulary()
    version: str | None = Field(default=None, pattern=r"^[\x21-\x7e]{1,64}$")
    ask_on_uncertain_overlaps: bool = False

    @field_validator("name")
    @classmethod
    def _named(cls, value: str) -> str:
        if not AGENT_NAME.fullmatch(value):
            raise ValueError(
                "the name names the agent's folder and its traces, so it is a lowercase word of "
                "up to 64 characters"
            )
        if value in _DEVICES:
            raise ValueError(
                "the name is one Windows keeps for a device (con, prn, aux, nul, com1 to com9, "
                "lpt1 to lpt9), so no folder can take it"
            )
        return value

    @field_validator("languages")
    @classmethod
    def _spoken(cls, value: Sequence[Language]) -> tuple[Language, ...]:
        tags = [language.tag for language in value]
        if not tags or len(set(tags)) != len(tags):
            raise ValueError("an agent speaks at least one language, each once")
        return tuple(value)

    @field_validator("instructions")
    @classmethod
    def _instructed(cls, value: Instructions | None, info: ValidationInfo) -> Instructions | None:
        return instructions_for(value, [each.tag for each in info.data.get("languages", ())])

    @field_validator("tools")
    @classmethod
    def _tooled(cls, value: Sequence[DeclaredTool], info: ValidationInfo) -> Sequence[DeclaredTool]:
        lines = {each.tag: each.progress for each in info.data.get("languages", ())}
        return tools_for(value, lines)

    @property
    def instructed(self) -> bool:
        """Whether it declares instructions: its calls run the talker (`session.mode`)."""
        return self.instructions is not None

    def call_language(self, requested: LanguageTag | None, *, locale: str | None) -> Language:
        """The language a call is held in, fixed when it joins and kept to its end (the echo
        has no other; the talker will pick each reply's): the `requested` tag (the caller's
        pick in the client) when the agent speaks it; else the caller's `locale` (a BCP 47 tag,
        as the join token carries it), matched in any case, its exact tag first, then the first
        of the agent's languages whose primary language is the locale's primary subtag (`ar`
        for both Arabic presets); else the agent's first language."""
        for language in self.languages:
            if language.tag == requested:
                return language
        wanted = (locale or "").casefold()
        primary = wanted.partition("-")[0]
        found = [language for language in self.languages if language.tag.casefold() == wanted]
        found += [language for language in self.languages if language.primary == primary]
        return (found or list(self.languages))[0]
