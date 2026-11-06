"""What the caller is shown on screen beside the captions (the design's 3.1, "Browser side";
plan 006, "What voice-first means here", item 5): a `Card`, short to the ear and whole on the
screen. A reply says one to three short sentences aloud, and the card holds the whole: a
knowledge passage's title and its steps, with the document they come from. A tool's result may
carry one (actions/tools.py's `ToolResult`), the talker hands it on, and the session sends it to
the client as `t2v/1`'s `card` (voice/protocol.py's `ShowCard`) once its text passed the output
guard, as a clause's does.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _says_something(value: str) -> str:
    """`value` when it holds more than spaces; the error never repeats it."""
    if not value.strip():
        raise ValueError("a card's text says something: it is not only spaces")
    return value


_Text = Annotated[str, Field(min_length=1), AfterValidator(_says_something)]


class Card(BaseModel):
    """A card: its `title`, its `steps` in order (none when its source lists none), and the
    `source` they come from, when there is one (a passage's document)."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    title: _Text
    steps: tuple[_Text, ...] = Field(default=(), max_length=50)
    source: _Text | None = None
