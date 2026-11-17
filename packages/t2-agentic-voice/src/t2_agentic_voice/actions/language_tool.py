"""The talker's language switch (D-038's amendment): `switch_language`, the library's read tool
the talker calls when the caller asks, in any words, to go on in another of the agent's
languages. The short list of spoken requests is the fast path (domain/language_switch.py's
`asked_language`); the model's judgement takes every other wording.

- **`language_tool`** builds it for an agent's languages. It takes the code of the language
  asked for (`en`, `ar`, or a tag the agent speaks) and gives back the agent's tag of it, as
  `{"language": tag}`; a language the agent does not speak is a `ToolError` naming the codes it
  does. It changes nothing itself: the talker's turn then says the rest of its reply in that
  language (agent/turn.py), and the session moves the call to it (voice/session/call_language.py).
- **`with_language_tool`**: an agent's tools with it added, for an agent of two languages or
  more under `stt.live_language = "detected"`, or `hinted` where it holds (D-115), unless the
  agent declares a tool of that name.
- **`switched_to`**: the tag the switch calls of one model request moved to, the last that
  succeeded; None when none did.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated

from pydantic import Field, TypeAdapter, ValidationError

from t2_agentic_voice.actions.tools import Tool, ToolResult
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ToolError
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.ports.chat_model import ToolCallRequest

# The tool's name as the talker calls it, and what tells the talker when to call it, in English
# (the design's 6.4); the key its result names the language under.
NAME = "switch_language"
DESCRIPTION = (
    "Call this when the caller asks you, in any words, to speak another language "
    "(for example 'can we go on in English?' or 'please talk to me in Arabic'), then answer "
    "them in it. Never call it because a word, a name or a quote in their turn is in "
    "another language: only when they ask."
)
KEY = "language"
_TAG = TypeAdapter(LanguageTag)
Code = Annotated[
    str,
    Field(
        min_length=2,
        max_length=8,
        pattern=r"^[A-Za-z]{2}(-[A-Za-z]{2})?$",
        description="The language the caller asked for: en for English, ar for Arabic.",
    ),
]


def language_tool(languages: Sequence[Language]) -> Tool:
    """The `switch_language` tool for an agent of `languages` (the module's docstring)."""
    spoken = tuple(languages)

    def switch_language(language: Code) -> ToolResult:
        found = language_of(spoken, language)
        if found is None:
            codes = ", ".join(dict.fromkeys(each.primary for each in spoken))
            raise ToolError(f"This agent speaks only these languages: {codes}.")
        return ToolResult(data={KEY: found.tag})

    return Tool.from_function(switch_language, description=DESCRIPTION, name=NAME, timeout_s=1.0)


def language_of(languages: Sequence[Language], code: str) -> Language | None:
    """The first of `languages` whose tag or primary code is `code`, in any case; None for
    none."""
    wanted = code.casefold()
    found = [each for each in languages if wanted in (each.tag.casefold(), each.primary)]
    return found[0] if found else None


def with_language_tool(
    tools: tuple[Tool, ...], languages: Sequence[Language], settings: VoiceSettings
) -> tuple[Tool, ...]:
    """`tools` with the `switch_language` tool added (the module's docstring)."""
    if not settings.stt.language_moves() or len(languages) < 2:
        return tools
    if any(tool.name == NAME for tool in tools):
        return tools
    return (*tools, language_tool(languages))


def switched_to(
    calls: Sequence[ToolCallRequest], results: Mapping[str, ToolResult]
) -> LanguageTag | None:
    """The tag the last `switch_language` call of `calls` that succeeded moved to, read from its
    result in `results` (by the call's id); None when none did."""
    moved: LanguageTag | None = None
    for call in calls:
        result = results.get(call.id)
        if call.name != NAME or result is None or not result.ok:
            continue
        if not isinstance(result.data, dict):
            continue
        try:
            moved = _TAG.validate_python(result.data.get(KEY))
        except ValidationError:
            continue
    return moved
