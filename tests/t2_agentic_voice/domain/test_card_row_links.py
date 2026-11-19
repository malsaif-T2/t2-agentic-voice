"""A row's own link (domain/cards.py's `CardRow.link`, D-130): none by default, so a row with
none is as it was (GP-18: its texts the same, its payload but a null `link`); a `CardLink`,
bounded as a card's links are, whose label is among the row's texts, which the output guard
reads, and whose url never is; and `t2v/1`'s `card` carries it with its row."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from t2_agentic_voice import Card, CardLink, CardRow
from t2_agentic_voice.voice.protocol import ShowCard, wire

URL = "https://www.google.com/travel/flights/search?tfs=Gh4SCjIwMjYtMTEtMjYy&hl=en"


def test_a_row_has_no_link_by_default_and_its_texts_are_as_they_were() -> None:
    row = CardRow(title="06:00 to 07:45", detail="nonstop", value="429 SAR")
    assert row.link is None
    assert row.texts() == ("06:00 to 07:45", "nonstop", "429 SAR")
    assert wire(ShowCard.of(Card(title="x", rows=(row,))))["rows"] == [
        {
            "title": "06:00 to 07:45",
            "detail": "nonstop",
            "value": "429 SAR",
            "mark": None,
            "link": None,
        }
    ]


def test_a_rows_link_label_is_among_its_texts_and_its_url_never_is() -> None:
    row = CardRow(title="06:00 to 07:45", value="429 SAR", link=CardLink(label="Book", url=URL))
    card = Card(title="Riyadh to Jeddah", rows=(row,))
    assert row.texts() == ("06:00 to 07:45", "429 SAR", "Book")
    assert card.texts() == ("Riyadh to Jeddah", "06:00 to 07:45", "429 SAR", "Book")
    assert all("https" not in text and "google" not in text for text in card.texts())


def test_the_payload_carries_each_rows_link_as_the_tool_gave_it() -> None:
    rows = (
        CardRow(title="06:00 to 07:45", link=CardLink(label="احجز", url=URL)),
        CardRow(title="Total", value="429 SAR"),
    )
    sent = wire(ShowCard.of(Card(title="x", rows=rows)))
    assert [row["link"] for row in sent["rows"]] == [{"label": "احجز", "url": URL}, None]
    assert ShowCard.model_validate(sent) == ShowCard.of(Card(title="x", rows=rows))


@pytest.mark.parametrize(
    "link",
    [
        {"label": "Book", "url": "javascript:alert(1)"},
        {"label": "Book", "url": "http://www.google.com/"},
        {"label": "Book SV 1020", "url": URL},  # a digit
        {"label": "", "url": URL},
        {"label": "Book"},
        "Book",
    ],
)
def test_a_rows_link_that_is_not_one_is_refused(link: object) -> None:
    with pytest.raises(ValidationError):
        CardRow.model_validate({"title": "06:00 to 07:45", "link": link})
