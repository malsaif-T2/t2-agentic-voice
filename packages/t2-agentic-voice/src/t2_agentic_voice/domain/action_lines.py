"""The lines the runtime speaks for an action, as the talker and the session pass them (the
design's 6.4): a template filled from the draft or the real result, never model text, so the
guard does not check it.

A `SpokenLine` keeps two forms: `text`, the plain words (a number as issued), which the caption
and every test read; and `spoken`, the same with each `{field:id}` said digit by digit, which
only text-to-speech reads. A `ReadBackPlan` is everything the session needs to read one draft
back, to end the read-back with no yes, and to speak while the write runs: `voice` cannot render
a template, so the action runner renders each line it may speak. `ActionLines` are the fixed
lines an action may leave to the library, whose texts are domain/presets.py's (`ACTION_LINES`),
in each preset's register and generic to any action.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.presets import ACTION_LINES


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
    `asked_again`, spoken when the answer is unclear; the lines `declined` and `sending`; the
    reply's `language`, which every line is spoken in; `wording`, the tag its texts were read
    in (`ar`, MSA, for an `ar-SA` reply to an MSA caller; None for the reply's own), which the
    outcome's line is read in too; the action's own `send_words`; and `max_attempts`, how
    many times the caller is asked.

    `declined` is the action's own line or the library's. The session speaks it only where no
    talker turn can answer: nothing usable heard after the last ask-again. After a plain no or
    a correction the talker answers in its own words, and this line is not spoken (the owner's
    ruling, plan 007).

    `sending` is rendered by Track B's `propose` from the action's `sending`, or the library's
    line when it is left out. Track C's session speaks it once the yes rule issues the
    `ConfirmedAction`, before the job's outcome. It is a fixed line, never a claim that the
    action is done."""

    action: str = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)
    draft_json: str = Field(min_length=2, repr=False)
    summary: SpokenLine
    question: SpokenLine
    asked_again: SpokenLine
    declined: SpokenLine
    sending: SpokenLine
    language: LanguageTag
    wording: LanguageTag | None = None
    send_words: tuple[str, ...] = ()
    max_attempts: int = Field(ge=1)


class ActionLines(_Line):
    """The library's default text of the lines an action may leave out, in one language:
    `sending`, said while the write runs, and the outcomes and the ask-again."""

    sending: str = Field(min_length=1)
    failed: str = Field(min_length=1)
    unknown: str = Field(min_length=1)
    declined: str = Field(min_length=1)
    asked_again: str = Field(min_length=1)


def default_action_lines(tag: LanguageTag) -> ActionLines:
    """The default lines in the language `tag`, in its register."""
    return ActionLines.model_validate(ACTION_LINES[tag])
