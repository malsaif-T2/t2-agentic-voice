"""How the action runner renders an action's words (the design's 6.4; domain/action_lines.py):
each template filled from the parsed draft or, in `done`, from the real result, never from
model text, in the reply's language: its texts read in the read-back's wording, the tag the
talker gives (`ar`, MSA, for an `ar-SA` reply to an MSA caller: agent/language.py's
`wording`), as domain/action_declaration.py's `read_in` reads a text, or the reply's own tag.

- A value is said as written, its spaces made single; a fixed value (a `Literal` or an enum)
  through its field's `Spoken` label in the language, or as written when it has none; a list
  as its items joined by commas; a number or a flag as JSON writes it; None as nothing.
- `{field:id}` keeps the value as issued in a line's `text`, and in its `spoken` form reads
  each run of digits digit by digit (domain/text/speaking.py's `speak_id`); a run of eight
  digits or more in groups of four, a comma between them, so a 16-digit number is said in
  four groups (plan 007, Q6).
- A line the action leaves out (`sending`, `asked_again`, `declined`, `failed`, `unknown`),
  or gives in no text the language reads, is the library's (`default_action_lines`) in that
  wording, so an MSA caller hears its MSA line, said as it is written.
"""

from __future__ import annotations

import json
import re
import string
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel

from t2_agentic_voice.actions.action import Action
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.action_declaration import Say, Spoken, read_in
from t2_agentic_voice.domain.action_lines import ReadBackPlan, SpokenLine, default_action_lines
from t2_agentic_voice.domain.ports.action_jobs import OutcomeKind
from t2_agentic_voice.domain.text.speaking import DIGIT, speak_id

# The lines the library has a default of (`ActionLines`' fields).
DefaultLine = Literal["sending", "failed", "unknown", "declined", "asked_again"]
# A run of digits as a value may write it: ASCII, Arabic-Indic or Persian.
_DIGITS = re.compile(f"{DIGIT}+")
# A run of digits said in groups from this length, each group this long.
_GROUPED_FROM = 8
_GROUP = 4
# What stands between two groups: a comma, the Arabic comma in Arabic.
_COMMA = {"en": ", ", "ar": "\u060c "}
_DIGIT_BY_DIGIT = "id"


def _text(value: object) -> str:
    """A value of a model's JSON dump as it is said."""
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return ", ".join(text for each in value if (text := _text(each)))
    return json.dumps(value, ensure_ascii=False)


def said_values(model: BaseModel, tag: LanguageTag) -> dict[str, str]:
    """Each field of `model` as it is said in `tag` (the module's docstring)."""
    dumped = model.model_dump(mode="json")
    said: dict[str, str] = {}
    for name, field in type(model).model_fields.items():
        value = dumped.get(name)
        labels = next((each for each in field.metadata if isinstance(each, Spoken)), None)
        label = None
        if labels is not None and isinstance(value, str | int | float):
            label = labels.label(str(value), tag)
        said[name] = label if label is not None else _text(value)
    return said


def _digit_by_digit(value: str, tag: LanguageTag) -> str:
    """`value` with each run of digits read one by one, a long run in groups."""

    def said(found: re.Match[str]) -> str:
        run = found.group()
        groups = [run]
        if len(run) >= _GROUPED_FROM:
            groups = [run[at : at + _GROUP] for at in range(0, len(run), _GROUP)]
        words = _COMMA[primary_code(tag)].join(speak_id(group, language=tag) for group in groups)
        return f" {words} "

    return " ".join(_DIGITS.sub(said, value).split())


def render(template: str, values: Mapping[str, str], tag: LanguageTag) -> SpokenLine:
    """`template` filled from `values`, in its two forms. ValueError when it says nothing."""
    text: list[str] = []
    spoken: list[str] = []
    for literal, name, spec, _ in string.Formatter().parse(template):
        text.append(literal)
        spoken.append(literal)
        if name is None:
            continue
        value = values[name]
        text.append(value)
        spoken.append(_digit_by_digit(value, tag) if spec == _DIGIT_BY_DIGIT else value)
    return SpokenLine(text="".join(text).strip(), spoken="".join(spoken).strip())


def _plain(line: str) -> SpokenLine:
    return SpokenLine(text=line, spoken=line)


def line_of(
    say: Say | None, kind: DefaultLine, values: Mapping[str, str], tag: LanguageTag
) -> SpokenLine:
    """The action's own line `say` read in `tag`, or the library's line of that `kind`."""
    if say is not None and any(key in say.templates for key in read_in(tag)):
        return render(say.for_language(tag), values, tag)
    return _plain(getattr(default_action_lines(tag), kind))


def draft_json(draft: BaseModel) -> str:
    """The parsed draft as the receipt holds it: its JSON, by the keys the talker gives, so the
    action's parameters read it back as they read the talker's arguments."""
    return draft.model_dump_json(by_alias=True)


def read_back_plan(
    action: Action,
    draft: BaseModel,
    *,
    tool_call_id: str,
    tag: LanguageTag,
    wording: LanguageTag | None = None,
) -> ReadBackPlan:
    """What the session needs to read `draft` back in `tag`, its texts read in `wording` (`tag`
    unless given), and to end the read-back with no yes, and to speak while the write runs.
    ValueError when a line would say nothing."""
    read = wording or tag
    values = said_values(draft, read)
    summary, question = action.read_back.for_language(read)
    return ReadBackPlan(
        action=action.name,
        tool_call_id=tool_call_id,
        draft_json=draft_json(draft),
        summary=render(summary, values, read),
        question=render(question, values, read),
        asked_again=line_of(action.read_back.asked_again, "asked_again", values, read),
        declined=line_of(action.declined, "declined", values, read),
        sending=line_of(action.sending, "sending", values, read),
        language=tag,
        wording=read,
        send_words=action.read_back.send_words.get(primary_code(tag), ()),
        max_attempts=action.read_back.max_attempts,
    )


def outcome_line(
    action: Action,
    kind: OutcomeKind,
    *,
    draft: BaseModel | None,
    result: BaseModel | None,
    tag: LanguageTag,
) -> SpokenLine:
    """The line that says how a write ended: `done` filled from the real `result`, else the
    action's `failed` or `unknown` filled from the `draft`, or the library's."""
    if kind == "done" and result is not None:
        return render(action.done.for_language(tag), said_values(result, tag), tag)
    line: DefaultLine = "failed" if kind == "failed" else "unknown"
    if draft is None:
        return line_of(None, line, {}, tag)
    return line_of(getattr(action, line), line, said_values(draft, tag), tag)
