"""What the caller is shown on screen beside the captions (the design's 3.1, "Browser side";
plan 006): a `Card`, a title, its steps, its option rows and the document they come from. Only
an extra for a client with a screen: the caller may have none, so what they need is always said
(D-075), and the knowledge tool shows none. A tool's result may carry one (actions/tools.py's
`ToolResult`), the talker hands it on, and the session sends it to the client as `t2v/1`'s
`card` (voice/protocol.py's `ShowCard`) once its text passed the output guard, as a clause's
does.

A card is data, never instructions: a page shows its texts as text and does nothing they say.
Its option rows (`CardRow`: a title, a detail and a value, each bounded, and a `mark` from a
closed set, `CARD_MARKS`, which a page maps to a style, never to markup) list what a reply
offered (flights, plans, slots), at most `MAX_ROWS`, so a card stays small on the wire. Every
text of a row is read by the output guard with the card's title and steps (`texts`), so no
number the call has no evidence for reaches the screen.

A card may name its `slot` on the page (D-110): a short closed-shape name, lowercase letters and
`_` only, at most `MAX_SLOT` characters (`outbound`, say), so a page with segments of its own can
put the card in its place. It is no text to show and carries no number, so the output guard does
not read it; a page that knows no slot of that name, or a card with none, shows it where it shows
every card.

A card may carry links (`CardLink`, D-126), at most `MAX_LINKS`, each a `label` the page shows
(1 to 40 characters, no digit, so it holds no number the guard would have to back) and the `url`
it opens, https only and at most `MAX_URL` characters, of any host. The label is one of the
card's texts, read by the guard; the url never is (the guard reads what is said or shown, and
an address is neither: a voice agent never reads one aloud). A page opens a link only from its
`url`, never from text. A card with no links is as it was.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, get_args
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# What a row may be marked as: the best of those listed (the lowest fare, say), the one the
# caller chose, or one that cannot be had (sold out); a closed set, so a page maps it to a style.
CardMark = Literal["best", "chosen", "unavailable"]
CARD_MARKS: Final = get_args(CardMark)
MAX_ROWS: Final = 8
# The longest slot a card may name (above); its shape is checked by the pattern.
MAX_SLOT: Final = 20
CardSlot = Annotated[str, Field(pattern=rf"^[a-z_]{{1,{MAX_SLOT}}}$")]
# The most links a card carries (one a leg of a round trip), and the longest url of one.
MAX_LINKS: Final = 2
MAX_URL: Final = 2048


def _says_something(value: str) -> str:
    """`value` when it holds more than spaces; the error never repeats it."""
    if not value.strip():
        raise ValueError("a card's text says something: it is not only spaces")
    return value


_Text = Annotated[str, Field(min_length=1), AfterValidator(_says_something)]


def _no_digit(value: str) -> str:
    """`value` when it holds no digit of any script; the error never repeats it."""
    if any(c.isdigit() for c in value):
        raise ValueError("a link's label holds no digit")
    return value


def _https(value: str) -> str:
    """`value` when it is an https address with a host, of printable ASCII and no space; the
    error never repeats it."""
    plain = value.isascii() and value.isprintable() and " " not in value
    parts = urlsplit(value) if plain else None
    if parts is None or parts.scheme != "https" or not parts.hostname:
        raise ValueError("a card's link is an https address")
    return value


class CardLink(BaseModel):
    """A link a card carries (the module's docstring): its `label` and its `url`."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    label: Annotated[_Text, Field(max_length=40), AfterValidator(_no_digit)]
    url: Annotated[str, Field(max_length=MAX_URL), AfterValidator(_https)]


class CardRow(BaseModel):
    """One option a card lists: its `title` (up to 80 characters), a `detail` (up to 120) and a
    `value` (up to 40, a price, say), each when it has one, and its `mark`, when it has one."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    title: Annotated[_Text, Field(max_length=80)]
    detail: Annotated[_Text, Field(max_length=120)] | None = None
    value: Annotated[_Text, Field(max_length=40)] | None = None
    mark: CardMark | None = None

    def texts(self) -> tuple[str, ...]:
        """The row's texts: its title, then its detail and its value, each when it has one."""
        return tuple(text for text in (self.title, self.detail, self.value) if text)


class Card(BaseModel):
    """A card: its `title`, its `steps` in order (none when its source lists none), its option
    `rows` in order (at most `MAX_ROWS`; none by default), the `source` they come from, when
    there is one (a passage's document), the `slot` it names on the page, when it names one,
    and its `links` (at most `MAX_LINKS`; none by default)."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    title: _Text
    steps: tuple[_Text, ...] = Field(default=(), max_length=50)
    rows: tuple[CardRow, ...] = Field(default=(), max_length=MAX_ROWS)
    source: _Text | None = None
    slot: CardSlot | None = None
    links: tuple[CardLink, ...] = Field(default=(), max_length=MAX_LINKS)

    def texts(self) -> tuple[str, ...]:
        """The card's texts, as the output guard reads them: its title, its steps, each row's
        texts, its source when it has one, then each link's label (never its url)."""
        rows = (text for row in self.rows for text in row.texts())
        source = (self.source,) if self.source else ()
        return (self.title, *self.steps, *rows, *source, *(link.label for link in self.links))
