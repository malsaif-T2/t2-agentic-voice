"""The lines the runtime speaks for an action, as the talker and the session pass them (the
design's 6.4): a template filled from the draft or the real result, never model text, so the
guard does not check it.

A `SpokenLine` keeps two forms: `text`, the plain words (a number as issued), which the caption
and every test read; and `spoken`, the same with each `{field:id}` said digit by digit, which
only text-to-speech reads. A `ReadBackPlan` is everything the session needs to read one draft
back, and to end the read-back with no yes: `voice` cannot render a template, so the action
runner renders each line it may speak. `ActionLines` are the fixed lines an action may leave to
the library.

Plan 007's Track A fills `default_action_lines`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.settings.tts import LanguageTag


class _Line(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SpokenLine(_Line):
    """One line, as the module says."""

    text: str = Field(min_length=1, repr=False)
    spoken: str = Field(min_length=1, repr=False)


class ReadBackPlan(_Line):
    """One draft to read back: the `action` and the model's id for the call (`tool_call_id`);
    `draft_json`, the parsed draft, which the receipt will hold; the `summary` the receipt
    covers and the closing `question`, rendered apart so each stays its own clause; the line
    `asked_again`, spoken when the answer is unclear; the line `declined`, the action's own or
    the library's, spoken when the read-back ends with no yes and no talker turn answers it: no
    clear answer after `max_attempts`, nothing heard included (after a plain no, as the owner
    rules, plan 007); the reply's `language`; the action's own `send_words`; and
    `max_attempts`, how many times the caller is asked."""

    action: str = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)
    draft_json: str = Field(min_length=2, repr=False)
    summary: SpokenLine
    question: SpokenLine
    asked_again: SpokenLine
    declined: SpokenLine
    language: LanguageTag
    send_words: tuple[str, ...] = ()
    max_attempts: int = Field(ge=1)


class ActionLines(_Line):
    """The library's default text of the lines an action may leave out, in one language."""

    failed: str = Field(min_length=1)
    unknown: str = Field(min_length=1)
    declined: str = Field(min_length=1)
    asked_again: str = Field(min_length=1)


def default_action_lines(tag: LanguageTag) -> ActionLines:
    """The default lines in the language `tag`, in its register."""
    raise NotImplementedError(f"plan 007's Track A fills default_action_lines ({tag})")
