"""The parts of a declaration the talker reads (the design's 4.3; plan 006), beside the echo's
(domain/declaration.py): the team's `instructions`, one text or one per language tag; its
`tools`; and its `vocabulary`, the product terms that become the Whisper prompt. All optional on
`VoiceAgent`, so an agent declared before the talker loads unchanged; an agent that declares
instructions runs the talker (`session.mode`, core/settings/session.py).

A tool is built in `actions/` (`@tool`, `Tool.from_function`, `knowledge_tool`), which `domain`
may not import (harness.toml [layers]), so the declaration holds each as the smallest shape a
tool has, `DeclaredTool`: its name, its description and the key of its progress line, which the
declaration checks (each name once; each progress line in every language the agent speaks).
The talker (agent/) runs the tools themselves.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Protocol, runtime_checkable

from pydantic import AfterValidator, Field, field_validator

from t2_agentic_voice.core.settings.base import FROZEN, PLAIN
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration_errors import Declared
from t2_agentic_voice.domain.text.invisible import holds_refused_character, provider_text

# A progress line's key: what a tool names its line by, and each language gives a text for
# (`Language.progress`): a lowercase word, with underscores.
PROGRESS_KEY = r"^[a-z][a-z0-9_]{0,31}$"
ProgressKey = Annotated[str, Field(pattern=PROGRESS_KEY)]


@runtime_checkable
class DeclaredTool(Protocol):
    """What the declaration reads of a tool (actions/tools.py's `Tool` has it): its `name`,
    which the talker calls it by; its `description`, in English; and the key of the progress
    line spoken when it runs long (`progress`, None for none)."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def progress(self) -> str | None: ...


def _instruction(value: str) -> str:
    """`value` when it says something; the error never repeats it."""
    if not value.strip():
        raise ValueError("an instructions text says nothing: it is empty, or only spaces")
    return value


def _term(value: str) -> str:
    """`value` as a product term: on one line, with no character a reader cannot see, saying
    something, with no space at either end."""
    if holds_refused_character(value) or not provider_text(value).strip():
        raise ValueError(
            "a term is one line of plain text that says something, with no control or unseen "
            "character"
        )
    if value != value.strip():
        raise ValueError("a term starts or ends with a space")
    return value


_Instruction = Annotated[str, AfterValidator(_instruction)]
# The team's instructions: one text for every language, or one per language tag, read-only.
Instructions = _Instruction | Annotated[Mapping[LanguageTag, _Instruction], FROZEN, PLAIN]
_Term = Annotated[str, Field(max_length=64), AfterValidator(_term)]


class Vocabulary(Declared):
    """The agent's vocabulary (the design's 4.3): the product terms its callers say, as a
    transcript should write them ("VPN", "Outlook"), which become the Whisper prompt with the
    `words.vocabulary` setting's. Frozen; given as any sequence, kept as a tuple."""

    terms: Sequence[_Term] = Field(default=(), max_length=200)

    @field_validator("terms")
    @classmethod
    def _kept(cls, value: Sequence[str]) -> tuple[str, ...]:
        return tuple(value)


def instructions_for(
    value: Instructions | None, tags: Sequence[LanguageTag]
) -> Instructions | None:
    """`value`, checked against the agent's language `tags`: one text, or a text for each of
    them and for no other tag. ValueError, in fixed words, otherwise."""
    if value is None or isinstance(value, str):
        return value
    if set(value) - set(tags):
        raise ValueError("it gives instructions for a language the agent does not speak")
    if set(tags) - set(value):
        raise ValueError("a language the agent speaks has no instructions; give each its own")
    return value


def tools_for(
    tools: Sequence[DeclaredTool], progress: Mapping[LanguageTag, Mapping[str, str]]
) -> tuple[DeclaredTool, ...]:
    """`tools` as a tuple, checked against the progress lines each of the agent's languages
    gives (`progress`, by tag): each tool's name once, and its progress line, if any, in every
    language. ValueError, in fixed words, otherwise."""
    names = [tool.name for tool in tools]
    if len(set(names)) != len(names):
        raise ValueError("two tools share a name; the talker calls each by its own")
    for tool in tools:
        if tool.progress is not None and any(tool.progress not in p for p in progress.values()):
            raise ValueError(
                "a tool names a progress line a language does not give; give each language "
                "its text in Language(progress=...)"
            )
    return tuple(tools)


def a_tool(value: object) -> DeclaredTool:
    """`value` when it is a tool (`@tool`, `Tool.from_function`, `knowledge_tool`)."""
    if not isinstance(value, DeclaredTool):
        raise ValueError("an item is not a tool: build it with @tool or Tool.from_function")
    return value


def a_vocabulary(value: object) -> object:
    """`value` when it may be a `Vocabulary`: one built, or the fields of one."""
    if not isinstance(value, Vocabulary | Mapping):
        raise ValueError("the vocabulary is Vocabulary(terms=[...]), not a list of terms")
    return value
