"""The `guard` group: the output guard's ID rule (the design's 8.2, rule B; plan 006): which
tokens of a clause are ID-shaped, and what a blocked clause drops; the phrases added to the
claim rule's default list (rule A; plan 007); whether a script none of the agent's languages
writes is taken out of what the talker writes before the guard reads it (agent/stray_script.py);
how many questions one reply may ask the caller (agent/question_limit.py, D-085), and whether a
stop there drops its request's tool calls; whether stage notes and tags count as the
model's reasoning (agent/leaked_reasoning.py, D-089); and whether only plain speech is said, a
request whose text is not speech tried once more (agent/plain_speech.py, D-111). Every clause
the talker writes is checked before text-to-speech, and so is a card's text; the runtime's own
templates are not.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator

from t2_agentic_voice.core.settings.base import Group, compiled
from t2_agentic_voice.core.settings.words import WordLists

# What a blocked clause drops: it and the rest of the reply, or only it.
OnBlock = Literal["drop_rest", "drop_clause"]
# One declared ID pattern, a regular expression as Python's `re` reads it.
_Pattern = Annotated[str, Field(min_length=1, max_length=200)]


class GuardSettings(Group):
    """The output guard: what counts as an ID, and what a clause that speaks one with no
    evidence drops."""

    id_patterns: tuple[_Pattern, ...] = Field(
        default=(),
        description=(
            "More ID shapes, beside runs of min_id_digits digits, as a JSON list of regular "
            'expressions, such as ["LT-\\\\d{5}"]. A pattern that matches no text at all '
            "(the empty text) is refused. Unset: none."
        ),
    )
    min_id_digits: int = Field(
        default=3,
        ge=1,
        le=32,
        description=(
            "The fewest digits in a row, after digit words and Arabic-Indic digits are made "
            "digits, that count as an ID, which passes only with evidence from this call."
        ),
    )
    on_block: OnBlock = Field(
        default="drop_rest",
        description=(
            "What a blocked clause drops: drop_rest, it and the rest of the reply, or "
            "drop_clause, only it. A fixed phrase is spoken in its place either way."
        ),
    )

    claims: WordLists = Field(
        default_factory=dict,
        validate_default=True,
        description=(
            "Phrases added to each language's default list of what claims any action, as a "
            'JSON object from a language\'s code to a list: {"ar": ["..."]}. A value replaces '
            "the map."
        ),
    )
    remove_stray_script: bool = Field(
        default=True,
        description=(
            "Whether each character of a script none of the agent's languages writes (a "
            "Chinese character in an Arabic reply), and each pictograph, is taken out of what "
            "the talker writes, its tool calls' arguments included, before the guard reads it, "
            "and a digit of another script written as its ASCII digit; the voice, the "
            "captions, the history, the trace and the events then hold the text without it. "
            "Off: kept as written."
        ),
    )
    questions_per_reply: int | None = Field(
        default=1,
        ge=1,
        description=(
            "The most questions one spoken reply of the talker's may ask the caller: the reply "
            "stops before the next one, which is not said, nor anything after it. A question is "
            "a clause that ends with a question mark. None, given in code: no limit."
        ),
    )
    question_stop_drops_calls: bool = Field(
        default=False,
        description=(
            "Whether a reply the question limit stopped also drops the tool calls of the "
            "request it stopped in: on, none of them runs, so the question the caller heard "
            "ends the turn; off, they run and are kept, as before."
        ),
    )
    drop_stage_notes: bool = Field(
        default=False,
        description=(
            "Whether a stage note or a tag the model writes into its answer counts as its "
            "reasoning, so nothing of that request is said from it on and none of its tools "
            "runs: in a reply in Arabic script, a parenthesis or bracket glued to a sentence's "
            "end with a capital Latin letter after it; in any language, one that opens a stage "
            'word ("(Waiting", "[No output"); and a "<" that opens a tag ("<action", "<data", '
            "or a tool's or an action's name). Arabic in parentheses never counts. In a reply in "
            'Arabic script, a sentence that opens as the reasoning does ("We need", "The user") '
            "after text written in Arabic script counts after a space too, not only glued; an "
            "English reply keeps the glued rule alone. Off: none counts."
        ),
    )
    plain_speech: bool = Field(
        default=False,
        description=(
            "Whether only plain speech is said (D-111): a run of dots after a sentence's mark "
            "is taken out, and one after a word made one ellipsis; a clause whose characters, "
            "spaces aside, are less than half letters or digits, or that holds a bracket, a "
            "brace or a tag's opening, is not said, nor anything after it of its request, and "
            "none of that request's tools runs; a request that said nothing so is sent once "
            "more while the turn has a request left; and zero-width spaces, word joiners, byte "
            "order marks, asterisks and backticks are taken out of every clause. Off: "
            "said as written."
        ),
    )

    @field_validator("id_patterns")
    @classmethod
    def _patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, pattern in enumerate(value):
            regex = compiled(pattern)
            if regex is None:
                raise ValueError(f"pattern {index} is not a regular expression Python reads")
            if regex.fullmatch(""):
                raise ValueError(f"pattern {index} matches the empty text, so every clause")
        return value
